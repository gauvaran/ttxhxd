#!/usr/bin/env python3
"""
fetch_content.py - Fetch VN news from RSS feeds, generate viral/tip content via Groq
"""

import feedparser
import datetime
import re
import sys
import os
import socket
import urllib.request
import urllib.error
import json
import time
from html.parser import HTMLParser

GROQ_URL   = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODEL = "llama-3.3-70b-versatile"

RSS_FEEDS = [
    ("https://vnexpress.net/rss/tin-muc-moi-nhat.rss",        "VnExpress"),
    ("https://tuoitre.vn/rss/tin-moi-nhat.rss",               "Tuổi Trẻ"),
    ("https://thanhnien.vn/rss/home.rss",                      "Thanh Niên"),
    ("https://dantri.com.vn/rss/home.rss",                     "Dân Trí"),
    ("https://cafef.vn/rss/home.rss",                          "CafeF"),
    ("https://vneconomy.vn/rss/home.rss",                      "VnEconomy"),
    ("https://www.bbc.com/vietnamese/index.xml",               "BBC Tiếng Việt"),
    ("https://baodanang.vn/rss/home.rss",                      "Báo Đà Nẵng"),
    ("https://suckhoedoisong.vn/rss/home.rss",                 "Sức Khỏe & Đời Sống"),
    ("https://vnexpress.net/rss/am-thuc.rss",                  "Ẩm Thực VnExpress"),
]

try:
    import sys as _sys, os as _os
    _sys.path.insert(0, _os.path.dirname(__file__))
    from handsome_guys import GUYS as _GUYS
except Exception:
    _GUYS = []


def get_daily_guy():
    if not _GUYS:
        return None
    idx = (datetime.datetime.now().timetuple().tm_yday - 1) % len(_GUYS)
    return _GUYS[idx]


class _StripHTML(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []

    def handle_data(self, d):
        self.parts.append(d)

    def get_text(self):
        return " ".join(self.parts).strip()


def _strip_html(text):
    p = _StripHTML()
    p.feed(text)
    return p.get_text()


def _groq_call(prompt, max_tokens=600, temperature=0.7):
    groq_key = os.environ.get("GROQ_API_KEY", "")
    if not groq_key:
        return ""
    payload = json.dumps({
        "model": GROQ_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
        "temperature": temperature,
    }).encode()
    req = urllib.request.Request(
        GROQ_URL,
        data=payload,
        headers={
            "Authorization": f"Bearer {groq_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "Mozilla/5.0 (compatible; TTXHXDBot/1.0)",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            data = json.loads(r.read().decode())
        return data["choices"][0]["message"]["content"].strip()
    except urllib.error.HTTPError as e:
        print(f"Groq HTTP {e.code}: {e.read().decode()[:200]}", file=sys.stderr)
        return ""
    except Exception as e:
        print(f"Groq error: {e}", file=sys.stderr)
        return ""


def _groq_summarize_vi(title, raw_text):
    if not raw_text:
        return ""
    prompt = (
        "Bạn là biên tập viên tin tức cho một tờ báo điện tử Việt Nam. "
        "Dựa HOÀN TOÀN vào nội dung được cung cấp bên dưới, "
        "hãy viết tóm tắt 3-5 câu bằng tiếng Việt, rõ ràng, dễ hiểu, súc tích. "
        "Tone dí dỏm, thân thiện — không khô khan như báo cáo. "
        "TUYỆT ĐỐI không thêm thông tin ngoài bài.\n\n"
        f"Tiêu đề: {title}\n\nNội dung: {raw_text[:3000]}"
    )
    return _groq_call(prompt, max_tokens=300, temperature=0.3)


def _groq_viral_content(date_str):
    prompt = (
        f"Hôm nay là {date_str}. Bạn là người nghiện mạng xã hội Việt Nam, "
        "theo dõi sát Facebook, TikTok, Threads mỗi ngày.\n\n"
        "Viết ĐÚNG 3 trend/câu nói/sự kiện viral đang hot trên MXH Việt Nam gần đây.\n\n"
        "Format mỗi item:\n"
        "### 🔥 [Tên trend hoặc câu nói hot]\n"
        "[2-3 câu: tại sao nó hot, ví dụ câu nói hoặc tình huống cụ thể, phản ứng cộng đồng]\n\n"
        "Yêu cầu:\n"
        "- Bắt kịp văn hóa internet VN thực tế (câu cửa miệng, meme, sự kiện gây tranh cãi, clip viral)\n"
        "- Hài hước tự nhiên, tiếng Việt sinh động, có thể chêm tiếng lóng\n"
        "- 3 item liền nhau, không giải thích thêm"
    )
    return _groq_call(prompt, max_tokens=500, temperature=0.9)


def _groq_food_tip(date_str):
    prompt = (
        f"Hôm nay là {date_str}. Bạn là đầu bếp và food blogger Việt Nam.\n\n"
        "Viết 1 tip ẩm thực hữu ích: có thể là công thức nhanh, mẹo nấu ăn, "
        "giới thiệu món ngon Đà Nẵng/Việt Nam hoặc mẹo chọn nguyên liệu.\n\n"
        "Yêu cầu:\n"
        "- ~120-150 từ, tiếng Việt sinh động có emoji\n"
        "- Thực tế, áp dụng được ngay, không cầu kỳ\n"
        "- Tone vui vẻ như người bạn chia sẻ bí kíp nấu ăn\n"
        "- Bắt đầu bằng emoji và tên tip ngắn gọn"
    )
    return _groq_call(prompt, max_tokens=400, temperature=0.8)


def _groq_health_tip(date_str):
    prompt = (
        f"Hôm nay là {date_str}. Bạn là chuyên gia dinh dưỡng và sức khỏe.\n\n"
        "Viết 1 tip sức khỏe/làm đẹp hữu ích cho phụ nữ văn phòng: thói quen tốt, "
        "dinh dưỡng, skincare đơn giản, hoặc cách giảm stress khi ngồi bàn.\n\n"
        "Yêu cầu:\n"
        "- ~120-150 từ, tiếng Việt sinh động có emoji\n"
        "- Thực tế, dễ áp dụng ngay tại văn phòng hoặc nhà\n"
        "- Tone ân cần như người bạn chăm sóc nhau\n"
        "- Bắt đầu bằng emoji và tên tip ngắn gọn"
    )
    return _groq_call(prompt, max_tokens=400, temperature=0.8)


def _fetch_rss_articles(target=6):
    socket.setdefaulttimeout(12)
    headers = {"User-Agent": "Mozilla/5.0 (compatible; TTXHXDBot/1.0)"}
    raw = []

    for feed_url, publisher in RSS_FEEDS:
        if len(raw) >= target + 3:
            break
        try:
            feed = feedparser.parse(feed_url, request_headers=headers)
            for entry in feed.entries[:3]:
                title = entry.get("title", "").strip()
                if not title:
                    continue
                link = entry.get("link", "")
                desc = _strip_html(entry.get("summary", entry.get("description", "")))
                raw.append({
                    "title": title,
                    "publisher": publisher,
                    "link": link,
                    "desc": desc,
                })
            print(f"OK: {publisher} ({len(feed.entries)} entries)", file=sys.stderr)
        except Exception as e:
            print(f"Feed error ({publisher}): {e}", file=sys.stderr)

    # Deduplicate by title similarity
    seen, deduped = set(), []
    for item in raw:
        key = item["title"][:40].lower()
        if key not in seen:
            seen.add(key)
            deduped.append(item)

    return deduped[:target]


def fetch_content():
    groq_key = os.environ.get("GROQ_API_KEY", "")
    today = datetime.datetime.now()
    date_str = today.strftime("%d/%m/%Y")
    date_iso = today.strftime("%Y-%m-%d")
    day_num = today.timetuple().tm_yday

    # ── Phase 1: Fetch RSS articles ───────────────────────────────────────────
    print("Fetching VN RSS feeds...", file=sys.stderr)
    raw_articles = _fetch_rss_articles(target=6)

    # ── Phase 2: Groq summarize each article ──────────────────────────────────
    articles = []
    for i, art in enumerate(raw_articles):
        print(f"  Summarizing {i+1}/{len(raw_articles)}: {art['title'][:50]}...", file=sys.stderr)
        summary = _groq_summarize_vi(art["title"], art["desc"]) if groq_key else art["desc"]
        time.sleep(5)
        articles.append({
            "title": art["title"],
            "publisher": art["publisher"],
            "link": art["link"],
            "summary": summary or art["desc"][:300],
        })

    # ── Phase 3: Viral MXH content ────────────────────────────────────────────
    print("Generating viral content...", file=sys.stderr)
    viral = _groq_viral_content(date_iso) if groq_key else ""
    time.sleep(4)

    # ── Phase 4: Tip (odd day = food, even day = health) ─────────────────────
    tip_type = "food" if day_num % 2 == 1 else "health"
    print(f"Generating {tip_type} tip...", file=sys.stderr)
    if groq_key:
        tip = _groq_food_tip(date_iso) if tip_type == "food" else _groq_health_tip(date_iso)
        time.sleep(4)
    else:
        tip = ""

    # ── Phase 5: Handsome guy of the day ─────────────────────────────────────
    guy = get_daily_guy()

    return {
        "date": date_str,
        "articles": articles,
        "viral": viral,
        "tip": tip,
        "tip_type": tip_type,
        "guy": guy,
        "groq": bool(groq_key),
    }


if __name__ == "__main__":
    import pprint
    pprint.pprint(fetch_content())
