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

# Đà Nẵng-specific sources (no national papers)
# baodanang.vn uses Google News sitemap (no RSS); 1022.vn has RSS
BAODANANG_SITEMAP = "https://baodanang.vn/sitemap-news.xml"
DANANG_RSS_FEEDS  = [
    ("https://1022.vn/rss", "1022.vn - Cổng TTĐT Đà Nẵng"),
]

# Keywords to filter 1022.vn articles that are not Đà Nẵng-specific
_DANANG_KW = {"đà nẵng", "da nang", "danang"}

# Entertainment/showbiz feeds — grounded sources for viral section
VIRAL_FEEDS = [
    ("https://vnexpress.net/rss/giai-tri.rss",   "VnExpress Giải trí"),
    ("https://soha.vn/rss/giai-tri.rss",         "Soha Giải trí"),
    ("https://nld.com.vn/rss/giai-tri.rss",      "NLĐ Giải trí"),
]

# Music + fashion feeds — grounded sources for music/fashion section
MUSIC_FEEDS   = [("https://tuoitre.vn/rss/am-nhac.rss",    "Tuổi Trẻ Âm nhạc")]
FASHION_FEEDS = [("https://tuoitre.vn/rss/thoi-trang.rss", "Tuổi Trẻ Thời trang")]

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
    total_tokens = max_tokens + 512  # thinking budget + response
    payload = json.dumps({
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "maxOutputTokens": total_tokens,
            "temperature": temperature,
            "thinkingConfig": {"thinkingBudget": 512},
        },
    }).encode()
    req = urllib.request.Request(
        url, data=payload,
        headers={"Content-Type": "application/json",
                 "User-Agent": "Mozilla/5.0 (compatible; TTXHXDBot/1.0)"},
    )
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=45) as r:
                data = json.loads(r.read().decode())
            return data["candidates"][0]["content"]["parts"][0]["text"].strip()
        except urllib.error.HTTPError as e:
            body = e.read().decode()[:200]
            if e.code == 429:
                wait = 15 * (attempt + 1)
                print(f"Gemini 429 (attempt {attempt+1}) — wait {wait}s", file=sys.stderr)
                time.sleep(wait)
            else:
                print(f"Gemini HTTP {e.code}: {body}", file=sys.stderr)
                return ""
        except Exception as e:
            print(f"Gemini error: {e}", file=sys.stderr)
            return ""
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
        GROQ_URL, data=payload,
        headers={"Authorization": f"Bearer {groq_key}",
                 "Content-Type": "application/json",
                 "User-Agent": "Mozilla/5.0 (compatible; TTXHXDBot/1.0)"},
    )
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                data = json.loads(r.read().decode())
            return data["choices"][0]["message"]["content"].strip()
        except urllib.error.HTTPError as e:
            body = e.read().decode()[:200]
            if e.code == 429:
                wait = 15 * (attempt + 1)
                print(f"Groq 429 (attempt {attempt+1}) — wait {wait}s", file=sys.stderr)
                time.sleep(wait)
            else:
                print(f"Groq HTTP {e.code}: {body}", file=sys.stderr)
                return ""
        except Exception as e:
            print(f"Groq error: {e}", file=sys.stderr)
            return ""
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
            "Bạn là biên tập viên tin tức. Viết tóm tắt khoảng 250 từ, tiếng Việt, "
            "rõ ràng và sinh động về bài báo sau:\n\n"
            f"Tiêu đề: {title}\n\n"
            "Nêu bối cảnh, diễn biến chính và ý nghĩa thực tế của sự kiện. "
            "Viết liền mạch, không dùng gạch đầu dòng. "
            "Không xưng hô với độc giả, không dùng câu chào mở đầu."
        )
    else:
        prompt = (
            "Bạn là biên tập viên tin tức. Dựa vào nội dung bên dưới, "
            "viết tóm tắt khoảng 250 từ, tiếng Việt, rõ ràng và sinh động.\n"
            "Tóm tắt phải bám sát tiêu đề — nếu nội dung lạc đề, ưu tiên diễn giải theo tiêu đề.\n"
            "Nêu bối cảnh, diễn biến, ý nghĩa thực tế. Viết liền mạch, không gạch đầu dòng.\n"
            "Không xưng hô với độc giả, không dùng câu chào mở đầu, không lặp lại cùng kiểu mở đầu.\n\n"
            f"Tiêu đề: {title}\n\nNội dung: {clean[:4000]}"
        )
    return _llm_call(prompt, max_tokens=800, temperature=0.4)


def _fetch_baomoi(slug, n=10):
    """Scrape a baomoi.com page (tag or listing) via Next.js __NEXT_DATA__ JSON.
    slug examples: 'tag/da-nang', 'tin-moi'
    Returns list of dicts: title, publisher, link, desc, date (datetime)."""
    import json as _json
    url = f"https://baomoi.com/{slug}.epi"
    try:
        req = urllib.request.Request(
            url, headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"}
        )
        with urllib.request.urlopen(req, timeout=12) as r:
            html = r.read().decode("utf-8", errors="ignore")
        m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.DOTALL)
        if not m:
            return []
        data = _json.loads(m.group(1))
        items = data["props"]["pageProps"]["resp"]["data"]["content"]["items"]
    except Exception as e:
        print(f"baomoi fetch error ({slug}): {e}", file=sys.stderr)
        return []
    out = []
    for it in items:
        title = it.get("title", "").strip()
        raw_url = it.get("url", "")
        link = "https://baomoi.com" + raw_url.split("#")[0]
        desc  = it.get("description", "")
        pub   = (it.get("publisher") or {}).get("name", "Báo Mới")
        ts    = it.get("date")
        pub_dt = datetime.datetime.fromtimestamp(ts) if ts else None
        if not title or not link:
            continue
        out.append({"title": title, "publisher": pub, "link": link,
                    "desc": desc, "pub_dt": pub_dt})
        if len(out) >= n:
            break
    return out


def _fetch_danang_articles(n=3):
    """Fetch Đà Nẵng-specific articles.
    Source 1: baodanang.vn Google News sitemap — the city's official newspaper, 100% local.
    Source 2: 1022.vn RSS — Đà Nẵng city portal, filtered by keyword.
    No shuffle, no national papers."""
    import re as _re
    out, seen = [], set()

    # ── Source 1: baodanang.vn news sitemap ──────────────────────────────────
    try:
        req = urllib.request.Request(
            BAODANANG_SITEMAP,
            headers={"User-Agent": "Mozilla/5.0 (compatible; TTXHXDBot/1.0)"}
        )
        with urllib.request.urlopen(req, timeout=12) as r:
            xml = r.read().decode("utf-8", errors="ignore")
        # Parse <url> blocks: extract loc + title
        for block in _re.findall(r'<url>(.*?)</url>', xml, _re.DOTALL):
            loc   = (_re.search(r'<loc>(.*?)</loc>', block) or type('', (), {'group': lambda s, x: ''})()).group(1).strip()
            raw_t = (_re.search(r'<news:title>(.*?)</news:title>', block, _re.DOTALL) or type('', (), {'group': lambda s, x: ''})()).group(1).strip()
            # Entities may wrap CDATA: &lt;![CDATA[title]]&gt; — decode then strip
            title = raw_t.replace('&lt;', '<').replace('&gt;', '>').replace('&amp;', '&')
            title = _re.sub(r'<!\[CDATA\[(.*?)\]\]>', r'\1', title).strip()
            if not title or not loc:
                continue
            key = title[:40].lower()
            if key in seen:
                continue
            seen.add(key)
            out.append({"title": title, "publisher": "Báo Đà Nẵng", "link": loc, "desc": ""})
            if len(out) >= n:
                return out
    except Exception as e:
        print(f"baodanang.vn sitemap error: {e}", file=sys.stderr)

    # ── Source 2: baomoi.com tag/da-nang ─────────────────────────────────
    if len(out) < n:
        for it in _fetch_baomoi("tag/da-nang", n=10):
            key = it["title"][:40].lower()
            if key in seen:
                continue
            seen.add(key)
            out.append({"title": it["title"], "publisher": it["publisher"],
                        "link": it["link"], "desc": it["desc"]})
            if len(out) >= n:
                return out

    # ── Source 3: 1022.vn RSS (final fallback) ────────────────────────────
    for url, publisher in DANANG_RSS_FEEDS:
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries[:20]:
                title = _strip_html(entry.get("title", "")).strip()
                link  = entry.get("link", "")
                desc  = _strip_html(entry.get("summary", entry.get("description", ""))).strip()
                if not title or not link:
                    continue
                key = title[:40].lower()
                if key in seen:
                    continue
                text = (title + " " + desc).lower()
                if not any(kw in text for kw in _DANANG_KW):
                    continue
                seen.add(key)
                out.append({"title": title, "publisher": publisher, "link": link, "desc": desc})
                if len(out) >= n:
                    return out
        except Exception as e:
            print(f"Đà Nẵng RSS error ({publisher}): {e}", file=sys.stderr)

    return out


def _fetch_viral_articles(n=8):
    """Fetch recent entertainment/showbiz articles from proven RSS sources."""
    raw = []
    for url, publisher in VIRAL_FEEDS:
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries[:6]:
                title = _strip_html(entry.get("title", "")).strip()
                desc  = _strip_html(entry.get("summary", entry.get("description", ""))).strip()
                link  = entry.get("link", "")
                if title and link:
                    raw.append({"title": title, "desc": desc[:300], "link": link, "publisher": publisher})
        except Exception as e:
            print(f"Viral feed error ({publisher}): {e}", file=sys.stderr)
    # deduplicate by title prefix
    seen, out = set(), []
    for item in raw:
        key = item["title"][:40].lower()
        if key not in seen:
            seen.add(key)
            out.append(item)
    return out[:n]


def _groq_viral_content(date_str, articles):
    if not articles:
        return ""
    context = "\n".join(
        f"[{i+1}] [{a['publisher']}] {a['title']}\n    Mô tả: {a['desc']}"
        for i, a in enumerate(articles)
    )
    # Build a lookup: ref number → markdown link for post-processing
    ref_map = {
        str(i + 1): f"[{a['publisher']}]({a['link']})"
        for i, a in enumerate(articles)
    }
    prompt = (
        f"Hôm nay là {date_str}. Dưới đây là {len(articles)} tin giải trí/showbiz thật vừa đăng hôm nay:\n\n"
        f"{context}\n\n"
        "Từ danh sách trên, chọn ĐÚNG 3 tin hot nhất/dễ gây xôn xao MXH nhất và viết theo format:\n\n"
        "### 🔥 [Tiêu đề hấp dẫn, ngắn gọn]\n"
        "📍 *Nguồn: REF[N]* (N là số thứ tự bài trong danh sách)\n"
        "[2-3 câu: viết lại sinh động, dí dỏm, nêu bật điều gây tò mò/tranh cãi, góc nhìn cộng đồng]\n\n"
        "Yêu cầu:\n"
        "- Chỉ dùng thông tin từ các bài có sẵn — KHÔNG bịa thêm chi tiết, số liệu, hoặc tên người\n"
        "- Dùng đúng REF[N] để tham chiếu, ví dụ REF[3] cho bài số 3\n"
        "- Tiếng Việt sinh động, chêm tiếng lóng tự nhiên, có thể thêm emoji\n"
        "- 3 item liền nhau, không thêm gì khác"
    )
    raw = _llm_call(prompt, max_tokens=700, temperature=0.8)
    # Replace REF[N] with actual markdown links
    import re as _re
    def _replace_ref(m):
        return ref_map.get(m.group(1), m.group(0))
    return _re.sub(r"REF\[(\d+)\]", _replace_ref, raw)


def _fetch_music_fashion_articles():
    """Fetch recent music and fashion articles from proven RSS sources."""
    music, fashion = [], []
    for feeds, bucket in [(MUSIC_FEEDS, music), (FASHION_FEEDS, fashion)]:
        for url, publisher in feeds:
            try:
                feed = feedparser.parse(url)
                for entry in feed.entries[:6]:
                    title = _strip_html(entry.get("title", "")).strip()
                    desc  = _strip_html(entry.get("summary", entry.get("description", ""))).strip()
                    link  = entry.get("link", "")
                    if title and link:
                        bucket.append({"title": title, "desc": desc[:300],
                                       "link": link, "publisher": publisher})
            except Exception as e:
                print(f"Music/fashion feed error ({publisher}): {e}", file=sys.stderr)
    # deduplicate each bucket by title prefix
    def _dedup(lst):
        seen, out = set(), []
        for item in lst:
            key = item["title"][:40].lower()
            if key not in seen:
                seen.add(key)
                out.append(item)
        return out
    return _dedup(music)[:5], _dedup(fashion)[:5]


def _groq_music_fashion_trend(date_str, music_articles, fashion_articles):
    if not music_articles and not fashion_articles:
        return ""
    import re as _re

    def _build_context(arts):
        return "\n".join(
            f"[{i+1}] {a['title']}\n    Mô tả: {a['desc']}"
            for i, a in enumerate(arts)
        )

    def _build_ref_map(arts):
        return {str(i + 1): f"[{a['publisher']}]({a['link']})" for i, a in enumerate(arts)}

    music_ctx   = _build_context(music_articles)
    fashion_ctx = _build_context(fashion_articles)
    music_refs  = _build_ref_map(music_articles)
    # fashion refs offset by len(music) so they don't clash
    offset = len(music_articles)
    fashion_refs = {str(i + 1): f"[{a['publisher']}]({a['link']})" for i, a in enumerate(fashion_articles)}

    prompt = (
        f"Hôm nay là {date_str}. Dưới đây là các tin tức thật về âm nhạc và thời trang:\n\n"
        f"ÂM NHẠC ({len(music_articles)} bài):\n{music_ctx}\n\n"
        f"THỜI TRANG ({len(fashion_articles)} bài):\n{fashion_ctx}\n\n"
        "Chọn 1 tin âm nhạc hay nhất và 1 tin thời trang hay nhất, viết theo format:\n\n"
        "**ÂM NHẠC 🎵**\n"
        "### 🎵 [Tiêu đề hấp dẫn]\n"
        "📍 *Nguồn: MREF[N]* (N là số thứ tự trong danh sách ÂM NHẠC)\n"
        "[2-3 câu: viết sinh động, nêu bật điểm thú vị, cảm xúc, lý do đáng nghe/xem]\n\n"
        "**THỜI TRANG 👗**\n"
        "### 👗 [Tiêu đề hấp dẫn]\n"
        "📍 *Nguồn: FREF[N]* (N là số thứ tự trong danh sách THỜI TRANG)\n"
        "[2-3 câu: mô tả trend, ai đang mặc, gợi ý mix cho nữ văn phòng]\n\n"
        "Yêu cầu:\n"
        "- Chỉ dùng thông tin từ các bài có sẵn — KHÔNG bịa thêm chi tiết, số liệu, view\n"
        "- Dùng MREF[N] cho âm nhạc, FREF[N] cho thời trang\n"
        "- Tiếng Việt sinh động, có thể thêm emoji\n"
        "- Chỉ 2 item, không thêm gì khác"
    )
    raw = _llm_call(prompt, max_tokens=600, temperature=0.8)

    def _replace_mref(m):
        return music_refs.get(m.group(1), m.group(0))

    def _replace_fref(m):
        return fashion_refs.get(m.group(1), m.group(0))

    raw = _re.sub(r"MREF\[(\d+)\]", _replace_mref, raw)
    raw = _re.sub(r"FREF\[(\d+)\]", _replace_fref, raw)
    return raw


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


def _fetch_vietcombank_rates():
    """Fetch exchange rates from Vietcombank XML API. Returns (rates_list, updated_str)."""
    TARGET = ["USD", "EUR", "JPY", "CNY", "GBP", "AUD", "SGD", "KRW"]
    LABELS = {
        "USD": "🇺🇸 USD", "EUR": "🇪🇺 EUR", "JPY": "🇯🇵 JPY", "CNY": "🇨🇳 CNY",
        "GBP": "🇬🇧 GBP", "AUD": "🇦🇺 AUD", "SGD": "🇸🇬 SGD", "KRW": "🇰🇷 KRW",
    }
    url = "https://portal.vietcombank.com.vn/Usercontrols/TVPortal.TyGia/pXML.aspx?b=10"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=12) as r:
            xml = r.read().decode("utf-8", errors="ignore")
        dt_m    = re.search(r'<DateTime>(.*?)</DateTime>', xml)
        updated = dt_m.group(1).strip() if dt_m else ""
        rates   = []
        _safe = lambda m, g: m.group(g) if m else ""
        for code in TARGET:
            m = re.search(rf'CurrencyCode="{code}"[^/]*/>', xml)
            if not m:
                continue
            exrate = m.group(0)
            buy  = _safe(re.search(r'Buy="([^"]+)"',  exrate), 1)
            sell = _safe(re.search(r'Sell="([^"]+)"', exrate), 1)
            if buy and sell and buy != "-":
                rates.append({"code": LABELS.get(code, code), "buy": buy, "sell": sell})
        return rates, updated
    except Exception as e:
        print(f"Vietcombank rate error: {e}", file=sys.stderr)
        return [], ""


def _scrape_giavang(brand, max_rows=6):
    """Scrape price table from giavang.org. Returns list of {name, buy, sell}."""
    url = f"https://giavang.org/trong-nuoc/{brand}/"
    try:
        req = urllib.request.Request(
            url, headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"}
        )
        with urllib.request.urlopen(req, timeout=12) as r:
            html = r.read().decode("utf-8", errors="ignore")
        _price_re = re.compile(r'^[0-9]{1,3}[.,][0-9]{3}')
        rows = re.findall(r'<tr[^>]*>(.*?)</tr>', html, re.DOTALL)
        out, seen = [], set()
        for row in rows:
            cells = re.findall(r'<t[dh][^>]*>(.*?)</t[dh]>', row, re.DOTALL)
            cells = [re.sub(r'<[^>]+>', '', c).strip() for c in cells]
            cells = [c for c in cells if c]
            prices = [c for c in cells if _price_re.match(c)]
            names  = [c for c in cells if not _price_re.match(c)]
            if len(prices) < 2 or not names:
                continue
            name = names[-1]   # last non-price cell is the product name
            key  = name[:30].lower()
            if key in seen:
                continue
            seen.add(key)
            out.append({"name": name, "buy": prices[0], "sell": prices[-1]})
            if len(out) >= max_rows:
                break
        return out
    except Exception as e:
        print(f"giavang.org ({brand}) error: {e}", file=sys.stderr)
        return []


def _fetch_finance_data():
    """Fetch financial data: exchange rates, gold and silver prices."""
    def _find(rows, kws, fallback_idx=0):
        for kw in kws:
            for r in rows:
                if kw.lower() in r["name"].lower():
                    return r
        return rows[fallback_idx] if rows else None

    print("Fetching exchange rates (Vietcombank)...", file=sys.stderr)
    rates, rates_updated = _fetch_vietcombank_rates()

    print("Fetching SJC gold prices (giavang.org)...", file=sys.stderr)
    sjc_all = _scrape_giavang("sjc")

    print("Fetching Doji gold prices (giavang.org)...", file=sys.stderr)
    doji_all = _scrape_giavang("doji")

    print("Fetching Phú Quý prices (giavang.org)...", file=sys.stderr)
    phuquy_all = _scrape_giavang("phu-quy", max_rows=10)

    return {
        "exchange_rates":  rates,
        "rates_updated":   rates_updated,
        "sjc_luong":   _find(sjc_all,    ["1L, 10L", "1L,10L", "1 lượng"], 0),
        "sjc_nhan":    _find(sjc_all,    ["nhẫn", "99,99%"]),
        "doji_sjc":    _find(doji_all,   ["SJC"], 0),
        "doji_nhan":   _find(doji_all,   ["nhẫn", "hưng thịnh"]),
        "pq_nhan":     _find(phuquy_all, ["nhẫn tròn phú quý"]),
        "silver_pq":   _find(phuquy_all, ["bạc"]),
        "source_note": "Tỷ giá: Vietcombank · Vàng/Bạc: giavang.org",
    }


def _load_prev_seen():
    """Extract article titles and links from the most recent previous newsletter HTML."""
    docs_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "docs")
    if not os.path.isdir(docs_dir):
        return set()
    override = os.environ.get("DATE_OVERRIDE")
    ref_date = override or datetime.datetime.now().strftime("%Y-%m-%d")
    dated = sorted(
        f[:-5] for f in os.listdir(docs_dir)
        if re.match(r'\d{4}-\d{2}-\d{2}\.html$', f) and f[:-5] < ref_date
    )
    if not dated:
        return set()
    try:
        content = open(os.path.join(docs_dir, dated[-1] + ".html"), encoding="utf-8").read()
    except Exception:
        return set()
    seen = set()
    # Article titles: <p style="...font-weight:bold;color:#8B6508...">TITLE</p>
    for raw_title in re.findall(r'font-weight:bold;color:#8B6508[^>]*>([^<]{5,})</p>', content):
        clean = re.sub(r'&[^;]+;', ' ', raw_title).strip()
        if len(clean) > 5:
            seen.add(clean[:50].lower())
    # Article source links (not local .html/.pdf)
    for link in re.findall(r'href="(https?://[^\s"]+)"', content):
        if not any(s in link for s in ('.html', '.pdf', 'ttxhxd', 'pages.dev')):
            seen.add(link.split('?')[0])
    return seen


def _fetch_rss_articles(target=6, feeds=None, seed=None):
    import random as _random
    socket.setdefaulttimeout(12)
    headers = {"User-Agent": "Mozilla/5.0 (compatible; TTXHXDBot/1.0)"}
    raw = []
    feed_list = feeds if feeds is not None else RSS_FEEDS

    # Always fetch 5 entries per feed to have alternatives for cross-day dedup.
    per_feed = 8 if feeds is not None else 5
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

    # Load yesterday's seen articles for cross-day deduplication (daily runs only).
    prev_seen = _load_prev_seen() if seed is None else set()

    # Two-pass dedup: fresh articles first, stale as fallback.
    seen_titles = set()
    fresh, stale = [], []
    for item in raw:
        key = item["title"][:50].lower()
        if key in seen_titles:
            continue
        seen_titles.add(key)
        link_base = item["link"].split('?')[0] if item.get("link") else ""
        if key in prev_seen or link_base in prev_seen:
            stale.append(item)
        else:
            fresh.append(item)

    result = fresh[:target]
    if len(result) < target:
        result += stale[:target - len(result)]
    return result


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

    # ── Phase 1: Fetch main VN articles (7 RSS by topic + 2 baomoi unique) ──
    print("Fetching VN RSS feeds...", file=sys.stderr)
    raw_rss = _fetch_rss_articles(target=7, seed=date_seed)
    print("Fetching baomoi tin-moi...", file=sys.stderr)
    raw_baomoi = _fetch_baomoi("tin-moi", n=20)
    # Add 2 unique baomoi articles not already in RSS pool
    rss_keys = {a["title"][:40].lower() for a in raw_rss}
    baomoi_unique = [b for b in raw_baomoi if b["title"][:40].lower() not in rss_keys]
    raw_articles = raw_rss + baomoi_unique[:2]

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
    raw_danang = _fetch_danang_articles(n=3)
    print(f"  Got {len(raw_danang)} Đà Nẵng articles", file=sys.stderr)
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

    # ── Phase 4: Viral MXH content (grounded in real articles) ──────────────
    print("Fetching viral/entertainment articles...", file=sys.stderr)
    viral_articles = _fetch_viral_articles(n=8)
    print(f"  Got {len(viral_articles)} viral articles", file=sys.stderr)
    print("Generating viral content...", file=sys.stderr)
    viral = _groq_viral_content(date_iso, viral_articles) if ai_key else ""
    time.sleep(2)

    # ── Phase 4b: Music + Fashion trending (grounded in real articles) ───────
    print("Fetching music/fashion articles...", file=sys.stderr)
    music_arts, fashion_arts = _fetch_music_fashion_articles()
    print(f"  Got {len(music_arts)} music, {len(fashion_arts)} fashion articles", file=sys.stderr)
    print("Generating music/fashion trend...", file=sys.stderr)
    music_fashion = _groq_music_fashion_trend(date_iso, music_arts, fashion_arts) if ai_key else ""
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

    # ── Phase 8: Financial data ───────────────────────────────────────────────
    finance = _fetch_finance_data()

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
        "finance": finance,
        "gemini": bool(gemini_key),
    }


if __name__ == "__main__":
    import pprint
    pprint.pprint(fetch_content())
