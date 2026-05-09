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

GEMINI_URL   = "https://generativelanguage.googleapis.com/v1beta/models"
GEMINI_MODEL = "gemini-2.5-flash"
GROQ_URL     = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODEL   = "llama-3.3-70b-versatile"

# 9 feeds × 1 bài/feed = 9 tin trải đều 9 chủ đề
RSS_FEEDS = [
    # 1. Chính trị - Thời sự - Xã hội
    ("https://tuoitre.vn/rss/chinh-tri-xa-hoi.rss",           "Tuổi Trẻ - Chính trị XH"),
    # 2. Kinh tế - Kinh doanh
    ("https://vnexpress.net/rss/kinh-doanh.rss",              "VnExpress - Kinh doanh"),
    # 3. Tài chính - Ngân hàng - NHNN - Bộ Tài chính (ưu tiên chính sách)
    ("https://tinnhanhchungkhoan.vn/rss/home.rss",            "Tin Nhanh Chứng Khoán"),
    # 4. Pháp luật - Dân sự
    ("https://tuoitre.vn/rss/phap-luat.rss",                  "Tuổi Trẻ - Pháp luật"),
    # 5. Thế giới - Quốc tế
    ("https://tuoitre.vn/rss/the-gioi.rss",                   "Tuổi Trẻ - Thế giới"),
    # 6. Văn hóa - Nghệ thuật - Lịch sử
    ("https://vnexpress.net/rss/van-hoa.rss",                 "VnExpress - Văn hóa"),
    # 7. Giải trí - Showbiz
    ("https://tuoitre.vn/rss/giai-tri.rss",                   "Tuổi Trẻ - Giải trí"),
    # 8. Sức khỏe - Y tế
    ("https://vnexpress.net/rss/suc-khoe.rss",                "VnExpress - Sức khỏe"),
    # 9. Công nghệ - Khoa học
    ("https://vnexpress.net/rss/khoa-hoc-cong-nghe.rss",      "VnExpress - Công nghệ"),
]

DANANG_FEEDS = [
    ("https://tuoitre.vn/rss/da-nang.rss",                    "Tuổi Trẻ - Đà Nẵng"),
    ("https://tuoitre.vn/rss/mien-trung.rss",                 "Tuổi Trẻ - Miền Trung"),
]

try:
    import sys as _sys, os as _os
    _sys.path.insert(0, _os.path.dirname(__file__))
    from handsome_guys import GUYS as _GUYS
except Exception:
    _GUYS = []


def get_daily_guy(override_date=None):
    if not _GUYS:
        return None
    d = override_date or datetime.datetime.now()
    idx = (d.timetuple().tm_yday - 1) % len(_GUYS)
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


def _gemini_call(prompt, max_tokens=600, temperature=0.7):
    gemini_key = os.environ.get("GEMINI_API_KEY", "")
    if not gemini_key:
        return ""
    url = f"{GEMINI_URL}/{GEMINI_MODEL}:generateContent?key={gemini_key}"
    payload = json.dumps({
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "maxOutputTokens": max_tokens,
            "temperature": temperature,
        },
    }).encode()
    req = urllib.request.Request(
        url,
        data=payload,
        headers={
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0 (compatible; TTXHXDBot/1.0)",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=45) as r:
            data = json.loads(r.read().decode())
        return data["candidates"][0]["content"]["parts"][0]["text"].strip()
    except urllib.error.HTTPError as e:
        print(f"Gemini HTTP {e.code}: {e.read().decode()[:300]}", file=sys.stderr)
        return ""
    except Exception as e:
        print(f"Gemini error: {e}", file=sys.stderr)
        return ""


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


def _llm_call(prompt, max_tokens=600, temperature=0.7):
    result = _gemini_call(prompt, max_tokens, temperature)
    if not result:
        print("Gemini returned empty — falling back to Groq", file=sys.stderr)
        result = _groq_call(prompt, max_tokens, temperature)
    return result


def _groq_summarize_vi(title, raw_text):
    clean = (raw_text or "").strip()
    if len(clean) < 80:
        prompt = (
            "Bạn là biên tập viên tin tức Việt Nam, viết cho nữ nhân viên văn phòng. "
            f"Viết tóm tắt khoảng 250 từ, tiếng Việt, dí dỏm, thân thiện về bài báo:\n\n"
            f"Tiêu đề: {title}\n\n"
            "Phân tích bối cảnh, ý nghĩa, tác động thực tế của sự kiện này. "
            "Viết tự nhiên như kể chuyện cho bạn nghe, không khô khan."
        )
    else:
        prompt = (
            "Bạn là biên tập viên tin tức Việt Nam, viết cho nữ nhân viên văn phòng. "
            "Dựa vào nội dung bên dưới, viết tóm tắt khoảng 250 từ, tiếng Việt, dí dỏm, thân thiện.\n"
            "QUAN TRỌNG: tóm tắt phải bám sát tiêu đề. "
            "Nếu nội dung không khớp tiêu đề, ưu tiên diễn giải theo tiêu đề.\n"
            "Viết tự nhiên như kể chuyện — nêu bối cảnh, diễn biến, ý nghĩa thực tế.\n\n"
            f"Tiêu đề: {title}\n\nNội dung: {clean[:4000]}"
        )
    return _llm_call(prompt, max_tokens=450, temperature=0.4)


def _groq_viral_content(date_str):
    prompt = (
        f"Hôm nay là {date_str}. Bạn là người nghiện MXH Việt Nam, theo dõi sát Facebook, TikTok, Threads.\n\n"
        "Viết ĐÚNG 3 nội dung viral/trending đang hot trên MXH Việt Nam gần đây.\n\n"
        "Format mỗi item:\n"
        "### 🔥 [Tên trend / sự kiện / câu nói hot]\n"
        "📍 *Nguồn: [nền tảng + kênh/fanpage/hashtag cụ thể, ví dụ: TikTok @..., Facebook group '...', Threads #...]*\n"
        "[2-3 câu: tại sao hot, ví dụ câu nói/tình huống cụ thể, phản ứng cộng đồng]\n\n"
        "Yêu cầu:\n"
        "- Ưu tiên: câu nói/slang đang viral (kiểu 'thôi kệ', 'đỉnh của chóp', nhưng phải là trend MỚI NHẤT hiện tại)\n"
        "- Có thể là: meme đang lan, clip triệu view, sự kiện gây tranh cãi, challenge TikTok\n"
        "- Phải dẫn nguồn cụ thể (tên kênh, fanpage, hashtag thật)\n"
        "- Tiếng Việt sinh động, chêm tiếng lóng tự nhiên\n"
        "- 3 item liền nhau, không thêm gì khác"
    )
    return _llm_call(prompt, max_tokens=600, temperature=0.9)


def _groq_music_fashion_trend(date_str):
    prompt = (
        f"Hôm nay là {date_str}. Bạn là người theo dõi âm nhạc Việt Nam và thời trang châu Á hàng ngày.\n\n"
        "Viết 2 item trending:\n\n"
        "**ÂM NHẠC 🎵**\n"
        "### 🎵 [Tên bài hát / MV / album Việt Nam đang hot nhất]\n"
        "📍 *Ca sĩ — [Số view/stream nếu biết] — [YouTube/TikTok/Spotify]*\n"
        "[2-3 câu: lý do đang được yêu thích, lyrics/câu hook đáng nhớ, vibe của bài]\n\n"
        "**THỜI TRANG 👗**\n"
        "### 👗 [Trend thời trang đang hot ở VN hoặc châu Á]\n"
        "📍 *[Instagram/TikTok/Shopee/Lazada — thương hiệu hoặc kênh nổi bật]*\n"
        "[2-3 câu: mô tả trend trông như thế nào, ai đang mặc, gợi ý mix đơn giản cho nữ văn phòng]\n\n"
        "Yêu cầu:\n"
        "- Âm nhạc: ưu tiên V-pop, nhạc Việt mới nhất — hit thật, MV thật, không bịa\n"
        "- Thời trang: trend thực tế đang bán chạy/được chia sẻ nhiều tại VN\n"
        "- Có nguồn/tên cụ thể"
    )
    return _llm_call(prompt, max_tokens=500, temperature=0.85)


def _groq_motivational_quote(date_str):
    prompt = (
        f"Hôm nay là {date_str}. Chọn 1 câu danh ngôn CÓ THẬT, đã được xác minh, "
        "truyền cảm hứng và tạo động lực cho phụ nữ Việt Nam đi làm hàng ngày.\n\n"
        "Nguồn hợp lệ — luân phiên đa dạng chủ đề, không lặp lại:\n"
        "- Triết học / nhân sinh: Marcus Aurelius, Epictetus, Seneca, Khổng Tử, Lão Tử\n"
        "- Lãnh đạo / sự nghiệp: Steve Jobs, Winston Churchill, Nelson Mandela, Hồ Chí Minh\n"
        "- Phụ nữ truyền cảm hứng: Maya Angelou, Michelle Obama, Coco Chanel, Marie Curie, Oprah Winfrey\n"
        "- Văn học / nghệ thuật: Nam Quốc Sơn Hà, Nguyễn Du, Antoine de Saint-Exupéry, Paulo Coelho\n"
        "- Ca dao tục ngữ Việt Nam truyền thống\n"
        "- Khoa học / đổi mới: Einstein, Stephen Hawking, Richard Feynman\n\n"
        "TUYỆT ĐỐI không bịa đặt hoặc gán câu nói cho người không nói câu đó.\n\n"
        "Format CHÍNH XÁC:\n"
        "💬 **\"[Câu gốc — nếu tiếng nước ngoài thì để nguyên bản ở đây]\"**\n"
        "*[Dịch tiếng Việt tự nhiên, nếu câu gốc không phải tiếng Việt]*\n"
        "— [Tên tác giả / nguồn]\n\n"
        "**Giải nghĩa:** [2-3 câu: ý nghĩa sâu xa của câu này là gì, áp dụng vào cuộc sống hàng ngày như thế nào, tại sao nó truyền cảm hứng]\n\n"
        "Chỉ output đúng format trên, không thêm gì khác."
    )
    return _llm_call(prompt, max_tokens=300, temperature=0.5)


def _groq_food_of_day(date_str):
    prompt = (
        f"Hôm nay là {date_str}. Bạn là food blogger Việt Nam, mê ăn vặt và đặc sản vùng miền.\n\n"
        "Giới thiệu 1 MÓN ĂN NGON HÔM NAY — ưu tiên:\n"
        "- Ăn vặt đường phố Đà Nẵng / miền Trung\n"
        "- Đặc sản vùng miền Việt Nam (3 miền luân phiên)\n"
        "- Món local food bình dân, ngon, dễ tìm\n\n"
        "Format:\n"
        "🍽️ **[Tên món]** — [Vùng miền / xuất xứ]\n\n"
        "[3-4 câu sinh động: mô tả hương vị, cách ăn, ăn kèm gì, tại sao ngon đến 'không thể dừng được']\n\n"
        "💡 **Ăn ở đâu ngon?** [1-2 gợi ý cụ thể: tên quán/khu chợ/con đường nổi tiếng]\n\n"
        "💰 **Giá tham khảo:** [khoảng giá thực tế]\n\n"
        "Yêu cầu: món thật, địa điểm thật (không bịa tên quán), giá thực tế. Tone vui vẻ, thèm ăn."
    )
    return _llm_call(prompt, max_tokens=350, temperature=0.85)


def _groq_tip_beauty(date_str):
    prompt = (
        f"Hôm nay là {date_str}. Bạn là beauty blogger và chuyên gia skincare Việt Nam.\n\n"
        "Viết 1 tip làm đẹp & chăm sóc da dành cho phụ nữ văn phòng. "
        "Chọn ngẫu nhiên 1 trong các chủ đề: skincare routine, chăm sóc da mặt/body, "
        "makeup tiết kiệm thời gian, chăm sóc tóc, móng tay, hoặc bí kíp tự tin tỏa sáng.\n\n"
        "Yêu cầu:\n"
        "- ~130-150 từ, tiếng Việt sinh động có emoji 💄\n"
        "- Sản phẩm/nguyên liệu dễ tìm, giá hợp lý\n"
        "- Tone vui tươi như người bạn thân share bí kíp\n"
        "- Bắt đầu bằng emoji + tên tip ngắn gọn in đậm"
    )
    return _llm_call(prompt, max_tokens=350, temperature=0.8)


def _groq_tip_exercise(date_str):
    prompt = (
        f"Hôm nay là {date_str}. Bạn là huấn luyện viên thể dục và chuyên gia dinh dưỡng.\n\n"
        "Viết 1 tip về tập thể dục, giảm cân hoặc giữ dáng cho phụ nữ văn phòng. "
        "Chọn ngẫu nhiên: bài tập tại nhà/văn phòng không cần dụng cụ, "
        "cardio đơn giản, mẹo ăn uống để giảm cân, kiểm soát calo, "
        "hoặc thói quen vận động nhỏ tích lũy cả ngày.\n\n"
        "Yêu cầu:\n"
        "- ~130-150 từ, tiếng Việt sinh động có emoji 🏃‍♀️\n"
        "- Thực tế, làm được ngay không cần gym hay dụng cụ đắt tiền\n"
        "- Có con số cụ thể (số lần, phút, calo) để dễ thực hiện\n"
        "- Bắt đầu bằng emoji + tên tip ngắn gọn in đậm"
    )
    return _llm_call(prompt, max_tokens=350, temperature=0.8)


def _groq_tip_health(date_str):
    prompt = (
        f"Hôm nay là {date_str}. Bạn là bác sĩ nội khoa và chuyên gia sức khỏe phụ nữ.\n\n"
        "Viết 1 tip sức khỏe thực tế cho phụ nữ văn phòng. "
        "Xoay vòng trong các chủ đề: huyết áp (đo, kiểm soát, thực phẩm tốt/xấu), "
        "cột sống (tư thế ngồi, bài tập phòng thoái hóa), đau vai gáy (nguyên nhân, bài tập giảm đau nhanh), "
        "đau đầu, mỏi mắt do màn hình, hoặc sức đề kháng.\n\n"
        "Yêu cầu:\n"
        "- ~130-150 từ, tiếng Việt sinh động có emoji 🩺\n"
        "- Có dẫn chứng khoa học ngắn hoặc con số cụ thể\n"
        "- Thực tế, áp dụng ngay tại chỗ ngồi văn phòng\n"
        "- Bắt đầu bằng emoji + tên tip ngắn gọn in đậm"
    )
    return _llm_call(prompt, max_tokens=350, temperature=0.75)


def _groq_food_tip(date_str):
    prompt = (
        f"Hôm nay là {date_str}. Bạn là đầu bếp và food blogger Việt Nam.\n\n"
        "Viết 1 tip ẩm thực hữu ích: công thức nhanh, mẹo nấu ăn, "
        "hoặc mẹo chọn nguyên liệu tươi ngon.\n\n"
        "Yêu cầu:\n"
        "- ~120-150 từ, tiếng Việt sinh động có emoji\n"
        "- Thực tế, áp dụng được ngay, không cầu kỳ\n"
        "- Tone vui vẻ như người bạn chia sẻ bí kíp nấu ăn\n"
        "- Bắt đầu bằng emoji và tên tip ngắn gọn"
    )
    return _llm_call(prompt, max_tokens=350, temperature=0.8)


def _fetch_rss_articles(target=6, feeds=None, seed=None):
    import random as _random
    socket.setdefaulttimeout(12)
    headers = {"User-Agent": "Mozilla/5.0 (compatible; TTXHXDBot/1.0)"}
    raw = []
    feed_list = feeds if feeds is not None else RSS_FEEDS

    # With a seed we fetch more entries per feed so shuffle gives real variety.
    per_feed = (5 if seed is not None else 1) if feeds is None else 8
    for feed_url, publisher in feed_list:
        try:
            feed = feedparser.parse(feed_url, request_headers=headers)
            for entry in feed.entries[:per_feed]:
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

    if seed is not None:
        _random.seed(seed)
        _random.shuffle(raw)

    # Deduplicate by title similarity
    seen, deduped = set(), []
    for item in raw:
        key = item["title"][:40].lower()
        if key not in seen:
            seen.add(key)
            deduped.append(item)

    return deduped[:target]


def fetch_content():
    gemini_key = os.environ.get("GEMINI_API_KEY", "")
    groq_key   = os.environ.get("GROQ_API_KEY", "")
    ai_key     = gemini_key or groq_key
    _override = os.environ.get("DATE_OVERRIDE")
    today = datetime.datetime.strptime(_override, "%Y-%m-%d") if _override else datetime.datetime.now()
    date_str = today.strftime("%d/%m/%Y")
    date_iso = today.strftime("%Y-%m-%d")
    day_num = today.timetuple().tm_yday

    # seed: unique integer per date so each day picks a different article subset
    date_seed = int(today.strftime("%Y%m%d")) if _override else None

    # ── Phase 1: Fetch main VN RSS articles ───────────────────────────────────
    print("Fetching VN RSS feeds...", file=sys.stderr)
    raw_articles = _fetch_rss_articles(target=9, seed=date_seed)

    # ── Phase 2: Groq summarize main articles ─────────────────────────────────
    articles = []
    for i, art in enumerate(raw_articles):
        print(f"  Summarizing {i+1}/{len(raw_articles)}: {art['title'][:50]}", file=sys.stderr)
        summary = _groq_summarize_vi(art["title"], art["desc"]) if ai_key else art["desc"]
        time.sleep(2)
        articles.append({
            "title": art["title"],
            "publisher": art["publisher"],
            "link": art["link"],
            "summary": summary or art["desc"][:300],
        })

    # ── Phase 3: Đà Nẵng dedicated news ──────────────────────────────────────
    print("Fetching Đà Nẵng RSS feeds...", file=sys.stderr)
    raw_danang = _fetch_rss_articles(target=3, feeds=DANANG_FEEDS, seed=date_seed)
    danang_articles = []
    for i, art in enumerate(raw_danang):
        print(f"  DaNang {i+1}/{len(raw_danang)}: {art['title'][:50]}...", file=sys.stderr)
        summary = _groq_summarize_vi(art["title"], art["desc"]) if ai_key else art["desc"]
        time.sleep(2)
        danang_articles.append({
            "title": art["title"],
            "publisher": art["publisher"],
            "link": art["link"],
            "summary": summary or art["desc"][:300],
        })

    # ── Phase 4: Viral MXH content ────────────────────────────────────────────
    print("Generating viral content...", file=sys.stderr)
    viral = _groq_viral_content(date_iso) if ai_key else ""
    time.sleep(2)

    # ── Phase 4b: Music + Fashion trending ───────────────────────────────────
    print("Generating music/fashion trend...", file=sys.stderr)
    music_fashion = _groq_music_fashion_trend(date_iso) if ai_key else ""
    time.sleep(2)

    # ── Phase 4c: Food of the day ─────────────────────────────────────────────
    print("Generating food of day...", file=sys.stderr)
    food_of_day = _groq_food_of_day(date_iso) if ai_key else ""
    time.sleep(2)

    # ── Phase 5: 3 mandatory tip sub-sections ────────────────────────────────
    print("Generating beauty tip...", file=sys.stderr)
    tip_beauty = _groq_tip_beauty(date_iso) if ai_key else ""
    time.sleep(2)
    print("Generating exercise tip...", file=sys.stderr)
    tip_exercise = _groq_tip_exercise(date_iso) if ai_key else ""
    time.sleep(2)
    print("Generating health tip...", file=sys.stderr)
    tip_health = _groq_tip_health(date_iso) if ai_key else ""
    time.sleep(2)

    # ── Phase 6: Motivational quote ───────────────────────────────────────────
    print("Generating motivational quote...", file=sys.stderr)
    quote = _groq_motivational_quote(date_iso) if ai_key else ""
    time.sleep(2)

    # ── Phase 7: Handsome guy of the day ─────────────────────────────────────
    guy = get_daily_guy(today)

    return {
        "date": date_str,
        "articles": articles,
        "danang_articles": danang_articles,
        "viral": viral,
        "music_fashion": music_fashion,
        "food_of_day": food_of_day,
        "tip_beauty": tip_beauty,
        "tip_exercise": tip_exercise,
        "tip_health": tip_health,
        "quote": quote,
        "guy": guy,
        "gemini": bool(gemini_key),
    }


if __name__ == "__main__":
    import pprint
    pprint.pprint(fetch_content())
