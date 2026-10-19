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

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dedup as _dedup      # noqa: E402
import guy_of_day as _guy   # noqa: E402
import llm as _llm          # noqa: E402
import sources as _src      # noqa: E402

MAX_AGE_H        = 36   # main/policy/viral news must be newer than this
DANANG_MAX_AGE_H = 72   # local news is sparser

# One story per feed per round (round-robin) → topic diversity is guaranteed.
RSS_FEEDS = [
    ("https://vnexpress.net/rss/thoi-su.rss",                 "VnExpress - Thời sự"),
    ("https://vnexpress.net/rss/kinh-doanh.rss",              "VnExpress - Kinh doanh"),
    ("https://cafef.vn/tai-chinh-ngan-hang.rss",              "CafeF - Tài chính ngân hàng"),
    ("https://tuoitre.vn/rss/the-gioi.rss",                   "Tuổi Trẻ - Thế giới"),
    ("https://tuoitre.vn/rss/phap-luat.rss",                  "Tuổi Trẻ - Pháp luật"),
    ("https://tuoitre.vn/rss/giai-tri.rss",                   "Tuổi Trẻ - Giải trí"),
    ("https://vnexpress.net/rss/suc-khoe.rss",                "VnExpress - Sức khỏe"),
    ("https://vnexpress.net/rss/khoa-hoc-cong-nghe.rss",      "VnExpress - Công nghệ"),
]

# Đà Nẵng sources, in priority order (baodanang.vn sitemap returns 403 since 2026-09)
DANANG_RSS_FEEDS  = [
    ("https://1022.vn/rss", "1022.vn - Cổng TTĐT Đà Nẵng"),
]
_DANANG_KW = {"đà nẵng", "da nang", "danang"}

# Entertainment/showbiz feeds — grounded sources for viral section
# Cross-source scoring: story in 3 feeds = viral signal, story in 1 feed = noise
VIRAL_FEEDS = [
    ("https://vnexpress.net/rss/giai-tri.rss",   "VnExpress Giải trí"),
    ("https://soha.vn/rss/giai-tri.rss",         "Soha Giải trí"),
    ("https://nld.com.vn/rss/giai-tri.rss",      "NLĐ Giải trí"),
    ("https://kenh14.vn/rss/home.rss",           "Kenh14"),
]

# Music + fashion feeds — grounded sources for music/fashion section
MUSIC_FEEDS   = [("https://tuoitre.vn/rss/am-nhac.rss",    "Tuổi Trẻ Âm nhạc")]
FASHION_FEEDS = [("https://tuoitre.vn/rss/thoi-trang.rss", "Tuổi Trẻ Thời trang")]

# Policy/legal RSS feeds — financial & regulatory focus
POLICY_FEEDS = [
    ("https://tinnhanhchungkhoan.vn/rss/home.rss", "Tin Nhanh Chứng Khoán"),
    ("https://vnexpress.net/rss/kinh-doanh.rss",   "VnExpress Kinh doanh"),
    ("https://cafebiz.vn/rss/home.rss",            "CafeBiz"),
    ("https://tuoitre.vn/rss/phap-luat.rss",       "Tuổi Trẻ Pháp luật"),
]

_POLICY_KW = {
    "nghị định", "thông tư", "quyết định", "có hiệu lực", "ban hành",
    "lãi suất", "thuế", "ngân hàng", "chứng khoán", "bất động sản",
    "nhnn", "bộ tài chính", "tài chính", "ngân sách", "pháp luật",
    "quy định", "điều chỉnh", "chính sách", "hiệu lực",
}

try:
    import sys as _sys, os as _os
    _sys.path.insert(0, _os.path.dirname(__file__))
    from handsome_guys import GUYS as _GUYS
except Exception:
    _GUYS = []


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


def _llm_call(prompt, max_tokens=600, temperature=0.7):
    return _llm.call(prompt, max_tokens, temperature)


def _groq_summarize_vi(title, raw_text, link=""):
    """3–5 sentence Vietnamese summary grounded in the article body.
    With too little source text we do NOT ask the LLM to invent — return ''."""
    body = _src.article_text(link) if link else ""
    clean = body if len(body) > len(raw_text or "") else (raw_text or "").strip()
    if len(clean) < 150:
        return ""
    prompt = (
        "Bạn là biên tập viên tin tức. Tóm tắt bài báo dưới đây trong 3–5 câu tiếng Việt, "
        "đủ để hiểu sự việc mà không cần đọc bài gốc: ai, làm gì, ở đâu, khi nào, con số chính, "
        "ảnh hưởng thực tế.\n"
        "RÀNG BUỘC: chỉ dùng thông tin có trong nội dung; không thêm số liệu, tên, ngày tháng ngoài bài. "
        "Bỏ qua phần quảng cáo, tin liên quan, chú thích ảnh. Viết liền mạch, không gạch đầu dòng, "
        "không xưng hô với độc giả, không câu chào.\n\n"
        f"Tiêu đề: {title}\n\nNội dung: {clean[:3500]}"
    )
    return _llm_call(prompt, max_tokens=400, temperature=0.3)


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


def _fetch_danang_articles(dd, n=3):
    """Fresh (<= DANANG_MAX_AGE_H), keyword-verified, de-duplicated Đà Nẵng stories.
    Sources: 1022.vn (city portal) → baomoi tag/da-nang → Google News 'Đà Nẵng'."""
    out = []

    def _consider(title, link, desc, publisher, entry):
        if len(out) >= n or not title or not link:
            return
        if not any(kw in (title + " " + desc).lower() for kw in _DANANG_KW):
            return
        age = _dedup.age_hours(entry)
        if age is None or age > DANANG_MAX_AGE_H:
            return
        if dd.take(title, link):
            out.append({"title": title, "publisher": publisher, "link": link, "desc": desc})

    for url, publisher in DANANG_RSS_FEEDS:
        try:
            for e in feedparser.parse(url).entries[:30]:
                _consider(_strip_html(e.get("title", "")).strip(), e.get("link", ""),
                          _strip_html(e.get("summary", e.get("description", ""))).strip(), publisher, e)
        except Exception as ex:
            print(f"Đà Nẵng RSS error ({publisher}): {ex}", file=sys.stderr)
    if len(out) < n:
        for it in _fetch_baomoi("tag/da-nang", n=30):
            _consider(it["title"], it["link"], it["desc"], it["publisher"], it)
    if len(out) < n:
        for it in _src.google_news("Đà Nẵng", when="2d", n=40):
            # Google News has no snippet: require the city name in the title itself
            _consider(it["title"], it["link"], it["title"], it["publisher"], it)
    return out


def _fetch_viral_articles(dd, n=12):
    """Fetch entertainment articles with cross-source virality scoring.
    Articles covered by multiple feeds are ranked higher — reliable viral signal.
    Returns top-n sorted by source count desc (multi-source stories first)."""
    from collections import defaultdict

    def _norm_key(title):
        # Normalize title to match the same story across different outlets
        return re.sub(r'\W+', '', title[:28].lower())

    raw = []
    for url, publisher in VIRAL_FEEDS:
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries[:15]:  # wider window per feed
                age = _dedup.age_hours(entry)
                if age is not None and age > MAX_AGE_H:
                    continue
                title = _strip_html(entry.get("title", "")).strip()
                desc  = _strip_html(entry.get("summary", entry.get("description", ""))).strip()
                link  = entry.get("link", "")
                if title and link:
                    raw.append({"title": title, "desc": desc[:300],
                                "link": link, "publisher": publisher,
                                "_nk": _norm_key(title)})
        except Exception as e:
            print(f"Viral feed error ({publisher}): {e}", file=sys.stderr)

    # Count how many distinct sources cover each story (by normalized title key)
    key_sources = defaultdict(set)
    for item in raw:
        key_sources[item["_nk"]].add(item["publisher"])

    # Sort by source count desc → dedup → return top n
    out = []
    for item in sorted(raw, key=lambda x: -len(key_sources[x["_nk"]])):
        if dd.is_dup(item["title"], item["link"]):
            continue
        src_count = len(key_sources[item["_nk"]])
        out.append({k: v for k, v in item.items() if not k.startswith("_")} |
                   {"_sources": src_count})
    return out[:n]


def _fetch_policy_articles(dd, n=5):
    """Fresh policy/legal articles from financial RSS feeds, filtered by keywords."""
    raw = []
    for url, publisher in POLICY_FEEDS:
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries[:15]:
                title = _strip_html(entry.get("title", "")).strip()
                desc  = _strip_html(entry.get("summary", entry.get("description", ""))).strip()
                link  = entry.get("link", "")
                age = _dedup.age_hours(entry)
                if not title or not link or (age is not None and age > MAX_AGE_H):
                    continue
                text = (title + " " + desc).lower()
                if any(kw in text for kw in _POLICY_KW) and not dd.is_dup(title, link):
                    raw.append({"title": title, "desc": desc[:300],
                                "link": link, "publisher": publisher})
        except Exception as e:
            print(f"Policy feed error ({publisher}): {e}", file=sys.stderr)
    return raw[:n]


USED_SOURCES = []  # articles actually cited by LLM sections in this run


def _cite(articles, idx_str, label_fmt="[{publisher}]({link})"):
    i = int(idx_str) - 1
    if 0 <= i < len(articles):
        USED_SOURCES.append(articles[i])
        return label_fmt.format(**articles[i])
    return None


def _groq_policy_summary(date_str, articles):
    if not articles:
        return ""
    context = "\n".join(
        f"[{i+1}] [{a['publisher']}] {a['title']}\n    Mô tả: {a['desc']}"
        for i, a in enumerate(articles)
    )
    prompt = (
        f"Hôm nay là {date_str}. Dưới đây là {len(articles)} tin tức về chính sách, pháp luật tài chính vừa đăng:\n\n"
        f"{context}\n\n"
        "Từ danh sách trên, chọn TỐI ĐA 3 tin quan trọng nhất ảnh hưởng đến người dân/doanh nghiệp và viết theo format:\n\n"
        "### 📋 [Tiêu đề ngắn gọn]\n"
        "📍 *Nguồn: PREF[N]*\n"
        "💡 **Tác động:** [1-2 câu: ảnh hưởng thực tế đến người dân, nhân viên ngân hàng, doanh nghiệp]\n\n"
        "Yêu cầu:\n"
        "- Chỉ dùng thông tin từ các bài có sẵn — KHÔNG bịa thêm số văn bản, ngày tháng\n"
        "- Dùng đúng PREF[N] (N là số thứ tự bài trong danh sách)\n"
        "- Tiếng Việt rõ ràng, ngắn gọn, dễ hiểu với người không chuyên pháp luật\n"
        "- Ưu tiên tin có từ khóa: Nghị định, Thông tư, lãi suất, thuế, có hiệu lực\n"
        "- Nếu không có tin chính sách thực sự, chỉ viết 1-2 item\n"
        "- Chỉ output đúng format, không thêm lời mở đầu hay kết luận"
    )
    raw = _llm_call(prompt, max_tokens=600, temperature=0.3)
    def _replace_pref(m):
        return _cite(articles, m.group(1)) or ""
    return re.sub(r"PREF\[(\d+)\]", _replace_pref, raw)


def _groq_viral_content(date_str, articles, trends=None):
    if not articles:
        return ""
    trend_ctx = ""
    if trends:
        trend_ctx = ("\nTỪ KHÓA ĐANG ĐƯỢC TÌM NHIỀU NHẤT VN HÔM NAY (Google Trends — tín hiệu thật):\n" +
                     "\n".join(f"- {t['keyword']} ({t['traffic']} lượt) — {t['news_title']}" for t in trends) +
                     "\nƯu tiên tin trùng với các từ khóa này.\n")

    def _src_label(a):
        s = a.get("_sources", 1)
        return f"🔴 {s} nguồn đưa tin" if s >= 3 else (f"🟠 {s} nguồn" if s == 2 else "")

    context = "\n".join(
        f"[{i+1}] {_src_label(a)} [{a['publisher']}] {a['title']}\n    Mô tả: {a['desc']}"
        for i, a in enumerate(articles)
    )
    prompt = (
        f"Hôm nay là {date_str}. Dưới đây là {len(articles)} tin giải trí/showbiz VN được {len(VIRAL_FEEDS)} nguồn thu thập:\n\n"
        f"{context}\n{trend_ctx}\n"
        "🔴 = nhiều nguồn cùng đưa tin → khả năng cao đang hot trên MXH\n\n"
        "Từ danh sách trên, chọn ĐÚNG 3 tin gây xôn xao MXH nhất và viết theo format:\n\n"
        "### 🔥 [Tiêu đề hấp dẫn, ngắn gọn]\n"
        "📍 *Nguồn: REF[N]*\n"
        "[2-3 câu: viết lại sinh động, dí dỏm, nêu bật điều gây tò mò/tranh cãi/sốc, góc nhìn cộng đồng]\n\n"
        "Ưu tiên chọn: scandal, tin sốc, bắt giữ, drama, viral clip, kết hôn/chia tay bất ngờ — "
        "đặc biệt ưu tiên bài có nhiều nguồn đưa tin (🔴/🟠)\n"
        "Yêu cầu:\n"
        "- Chỉ dùng thông tin từ các bài có sẵn — KHÔNG bịa thêm chi tiết, số liệu, tên người\n"
        "- Dùng đúng REF[N] (N là số thứ tự bài trong danh sách)\n"
        "- Tiếng Việt sinh động, chêm tiếng lóng tự nhiên, có thể thêm emoji\n"
        "- 3 item liền nhau, không thêm gì khác"
    )
    raw = _llm_call(prompt, max_tokens=700, temperature=0.8)
    def _replace_ref(m):
        return _cite(articles, m.group(1)) or ""
    return re.sub(r"REF\[(\d+)\]", _replace_ref, raw)


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


def _groq_music_fashion_trend(date_str, music_articles, fashion_articles, chart=None):
    if not music_articles and not fashion_articles:
        return ""
    chart_ctx = ""
    if chart:
        chart_ctx = ("BẢNG XẾP HẠNG APPLE MUSIC VIỆT NAM HÔM NAY (dữ liệu thật):\n" +
                     "\n".join(f"#{c['rank']} {c['title']} — {c['artist']}" for c in chart) + "\n\n")
    import re as _re

    def _build_context(arts):
        return "\n".join(
            f"[{i+1}] {a['title']}\n    Mô tả: {a['desc']}"
            for i, a in enumerate(arts)
        )

    music_ctx   = _build_context(music_articles)
    fashion_ctx = _build_context(fashion_articles)

    prompt = (
        f"Hôm nay là {date_str}. Dưới đây là các tin tức thật về âm nhạc và thời trang:\n\n"
        f"{chart_ctx}ÂM NHẠC ({len(music_articles)} bài):\n{music_ctx}\n\n"
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
        "- Chỉ 2 item, không thêm gì khác\n"
        + ("- Sau 2 item, thêm 1 dòng: '🎧 **Top 3 Apple Music VN:** ' + 3 bài đầu bảng xếp hạng (tên — ca sĩ), "
           "chép đúng như dữ liệu" if chart else "")
    )
    raw = _llm_call(prompt, max_tokens=700, temperature=0.8)

    def _replace_mref(m):
        return _cite(music_articles, m.group(1)) or ""

    def _replace_fref(m):
        return _cite(fashion_articles, m.group(1)) or ""

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


# Deterministic topic rotation: the LLM never "picks randomly" (it always picks the
# same favourite), so each day gets an explicit topic and cycles through the list.
DISHES = [
    "Mì Quảng", "Bún chả cá Đà Nẵng", "Bánh tráng cuốn thịt heo", "Bánh xèo miền Trung", "Bún mắm nêm",
    "Bánh bèo chén", "Bánh nậm", "Bánh bột lọc", "Gỏi cá Nam Ô", "Bê thui Cầu Mống", "Cao lầu Hội An",
    "Cơm gà Hội An", "Bánh mì Phượng Hội An", "Chè xoa xoa hạt lựu", "Bún bò Huế", "Cơm hến",
    "Bánh canh cua", "Ốc hút", "Nem lụi", "Bánh căn", "Bún riêu cua", "Phở bò Hà Nội", "Bún chả Hà Nội",
    "Chả cá Lã Vọng", "Bánh cuốn Thanh Trì", "Cốm làng Vòng", "Bánh mì Sài Gòn", "Cơm tấm sườn",
    "Hủ tiếu Nam Vang", "Bánh xèo miền Tây", "Lẩu mắm", "Bánh pía Sóc Trăng", "Chè Thái",
    "Bột chiên", "Bánh khọt Vũng Tàu", "Bún thịt nướng", "Gỏi cuốn", "Bánh tráng trộn", "Chè bưởi",
    "Sữa chua nếp cẩm", "Xôi xéo", "Bánh đúc nóng", "Nộm bò khô", "Bún đậu mắm tôm", "Bánh căn Phan Rang",
]
TOPICS_BEAUTY = ["skincare buổi sáng 5 phút", "tẩy trang & làm sạch đúng cách", "chống nắng khi ngồi văn phòng",
                 "dưỡng ẩm da trong phòng máy lạnh", "makeup tự nhiên 10 phút", "chăm sóc tóc khô xơ",
                 "chăm sóc móng tay tại nhà", "giảm quầng thâm mắt", "chăm sóc môi khô nứt",
                 "dưỡng da tay khi làm việc nhiều", "chọn nước hoa văn phòng", "ngủ đủ giấc để da đẹp",
                 "mặt nạ tự làm từ nguyên liệu bếp", "chăm sóc da body", "trị mụn nội tiết nhẹ"]
TOPICS_EXERCISE = ["giãn cơ cổ vai gáy tại bàn", "bài tập mông đùi không dụng cụ", "đi bộ 10.000 bước",
                   "plank & bài tập core", "yoga trước khi ngủ", "cardio 15 phút tại nhà",
                   "leo cầu thang thay thang máy", "kiểm soát calo bữa trưa văn phòng", "uống đủ nước",
                   "bài tập cho người ngồi lâu", "ăn vặt lành mạnh", "giữ dáng sau 30 tuổi",
                   "nhảy dây", "tập thở sâu giảm stress", "thói quen vận động nhỏ cả ngày"]
TOPICS_HEALTH = ["huyết áp: đo và kiểm soát", "tư thế ngồi bảo vệ cột sống", "đau vai gáy",
                 "mỏi mắt do màn hình (quy tắc 20-20-20)", "đau đầu căng thẳng", "tăng sức đề kháng",
                 "giấc ngủ chất lượng", "uống cà phê đúng cách", "dạ dày & bữa sáng", "thiếu máu, thiếu sắt",
                 "sức khỏe tuyến giáp", "stress công việc", "khám sức khỏe định kỳ cho nữ",
                 "hội chứng ống cổ tay", "giữ ấm khi trời chuyển mùa"]


def _rotate(options, day_num, salt=0):
    return options[(day_num + salt) % len(options)]


def _groq_food_of_day(date_str, day_num=0):
    prompt = (
        f"Hôm nay là {date_str}. Bạn là food blogger Việt Nam, mê ăn vặt và đặc sản vùng miền.\n\n"
        f"Giới thiệu MÓN ĂN NGON HÔM NAY: **{_rotate(DISHES, day_num)}**.\n\n"
        "Format:\n"
        "🍽️ **[Tên món]** — [Vùng miền / xuất xứ]\n\n"
        "[3-4 câu sinh động: mô tả hương vị, cách ăn, ăn kèm gì, tại sao ngon đến 'không thể dừng được']\n\n"
        "💡 **Ăn ở đâu?** [khu chợ / phố ẩm thực nổi tiếng nơi món này phổ biến — KHÔNG nêu tên quán cụ thể]\n\n"
        "💰 **Giá tham khảo:** [khoảng giá thực tế]\n\n"
        "Yêu cầu: không bịa tên quán, giá là khoảng phổ biến. Tone vui vẻ, thèm ăn."
    )
    return _llm_call(prompt, max_tokens=350, temperature=0.85)


def _groq_tip_beauty(date_str, day_num=0):
    prompt = (
        f"Hôm nay là {date_str}. Bạn là beauty blogger và chuyên gia skincare Việt Nam.\n\n"
        f"Viết 1 tip làm đẹp cho phụ nữ văn phòng. Chủ đề hôm nay: **{_rotate(TOPICS_BEAUTY, day_num)}**.\n\n"
        "Yêu cầu:\n"
        "- ~130-150 từ, tiếng Việt sinh động có emoji 💄\n"
        "- Sản phẩm/nguyên liệu dễ tìm, giá hợp lý\n"
        "- Tone vui tươi như người bạn thân share bí kíp\n"
        "- Bắt đầu bằng emoji + tên tip ngắn gọn in đậm"
    )
    return _llm_call(prompt, max_tokens=350, temperature=0.8)


def _groq_tip_exercise(date_str, day_num=0):
    prompt = (
        f"Hôm nay là {date_str}. Bạn là huấn luyện viên thể dục và chuyên gia dinh dưỡng.\n\n"
        f"Viết 1 tip vận động/giữ dáng cho phụ nữ văn phòng. Chủ đề hôm nay: **{_rotate(TOPICS_EXERCISE, day_num, 5)}**.\n\n"
        "Yêu cầu:\n"
        "- ~130-150 từ, tiếng Việt sinh động có emoji 🏃‍♀️\n"
        "- Thực tế, làm được ngay không cần gym hay dụng cụ đắt tiền\n"
        "- Có con số cụ thể (số lần, phút, calo) để dễ thực hiện\n"
        "- Bắt đầu bằng emoji + tên tip ngắn gọn in đậm"
    )
    return _llm_call(prompt, max_tokens=350, temperature=0.8)


def _groq_tip_health(date_str, day_num=0):
    prompt = (
        f"Hôm nay là {date_str}. Bạn là bác sĩ nội khoa và chuyên gia sức khỏe phụ nữ.\n\n"
        f"Viết 1 tip sức khỏe thực tế cho phụ nữ văn phòng. Chủ đề hôm nay: **{_rotate(TOPICS_HEALTH, day_num, 10)}**.\n\n"
        "Yêu cầu:\n"
        "- ~130-150 từ, tiếng Việt sinh động có emoji 🩺\n"
        "- Chỉ nêu khuyến nghị y khoa phổ biến, đã được công nhận (WHO, Bộ Y tế); không bịa nghiên cứu/con số\n"
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


def _fetch_vangtodaygold():
    """Fetch gold prices from vang.today free JSON API.
    Returns list of {label, buy, sell, change, currency}."""
    KEYS = {
        "SJL1L10":   "🥇 SJC 1 lượng",
        "SJ9999":    "💍 SJC nhẫn tròn",
        "DOJINHTV":  "💛 DOJI nhẫn tròn",
        "PQHN24NTT": "✨ PNJ nhẫn tròn 24K",
        "XAUUSD":    "🌍 Vàng thế giới",
    }
    url = "https://www.vang.today/api/prices"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as r:
            data = json.loads(r.read().decode())
        if not data.get("success"):
            return [], ""
        prices_raw = data.get("prices", {})
        updated = data.get("time", "") + " " + data.get("date", "")

        def _fmt_vnd(val):
            # 164000000 → "164.00 triệu"
            return f"{val / 1_000_000:.2f} triệu"

        def _fmt_delta(d):
            if not d:
                return ""
            arrow = "↑" if d > 0 else "↓"
            return f"{abs(d)/1_000_000:.2f} {arrow}"

        out = []
        for key, label in KEYS.items():
            item = prices_raw.get(key)
            if not item:
                continue
            currency = item.get("currency", "VND")
            if currency == "VND":
                buy  = _fmt_vnd(item["buy"])  if item.get("buy")  else "-"
                sell = _fmt_vnd(item["sell"]) if item.get("sell", 0) > 0 else "-"
                chg  = _fmt_delta(item.get("change_buy", 0))
                unit = "triệu đ/lượng"
            else:
                buy  = f"{item['buy']:,}"   if item.get("buy")  else "-"
                sell = f"{item['sell']:,}"  if item.get("sell") else "-"
                chg  = ""
                unit = currency
            out.append({"label": label, "buy": buy, "sell": sell,
                        "change": chg, "unit": unit})
        return out, updated
    except Exception as e:
        print(f"vang.today error: {e}", file=sys.stderr)
        return [], ""


def _fetch_crypto():
    """Fetch BTC, ETH, USDT prices from CoinGecko (free, no auth).
    Returns dict {btc_usd, eth_usd, usdt_vnd, btc_vnd}."""
    url = ("https://api.coingecko.com/api/v3/simple/price"
           "?ids=bitcoin,ethereum,tether&vs_currencies=usd,vnd")
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as r:
            data = json.loads(r.read().decode())

        def _fmt_usd(val):
            return f"{val:,.0f}"

        def _fmt_vnd_b(val):
            return f"{val/1_000_000_000:.3f} tỷ"

        btc = data.get("bitcoin", {})
        eth = data.get("ethereum", {})
        usdt = data.get("tether", {})
        return {
            "btc_usd":  _fmt_usd(btc.get("usd", 0)),
            "btc_vnd":  _fmt_vnd_b(btc.get("vnd", 0)),
            "eth_usd":  _fmt_usd(eth.get("usd", 0)),
            "usdt_vnd": f"{usdt.get('vnd', 0):,}",
        }
    except Exception as e:
        print(f"CoinGecko error: {e}", file=sys.stderr)
        return {}


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
    """Fetch financial data: exchange rates, gold/silver prices, crypto."""
    def _find(rows, kws, fallback_idx=0):
        for kw in kws:
            for r in rows:
                if kw.lower() in r["name"].lower():
                    return r
        return rows[fallback_idx] if rows else None

    print("Fetching exchange rates (Vietcombank)...", file=sys.stderr)
    rates, rates_updated = _fetch_vietcombank_rates()

    print("Fetching gold prices (vang.today)...", file=sys.stderr)
    gold_list, gold_updated = _fetch_vangtodaygold()

    print("Fetching silver prices (giavang.org/phu-quy)...", file=sys.stderr)
    phuquy_all = _scrape_giavang("phu-quy", max_rows=10)
    silver_pq  = _find(phuquy_all, ["bạc"])

    print("Fetching crypto prices (CoinGecko)...", file=sys.stderr)
    crypto = _fetch_crypto()

    return {
        "exchange_rates":  rates,
        "rates_updated":   rates_updated,
        "gold_list":       gold_list,
        "gold_updated":    gold_updated,
        "silver_pq":       silver_pq,
        "crypto":          crypto,
        "source_note": "Tỷ giá: Vietcombank · Vàng: vang.today · Crypto: CoinGecko",
    }


def _fetch_rss_articles(dd, target=8, feeds=None, max_age_h=MAX_AGE_H):
    """Round-robin across feeds (one fresh, non-duplicate story per feed per round),
    so every topic is represented before any feed contributes a second story."""
    socket.setdefaulttimeout(12)
    headers = {"User-Agent": "Mozilla/5.0 (compatible; TTXHXDBot/1.0)"}
    per_feed = []
    for feed_url, publisher in (feeds or RSS_FEEDS):
        items = []
        try:
            feed = feedparser.parse(feed_url, request_headers=headers)
            for entry in feed.entries[:25]:
                title = _strip_html(entry.get("title", "")).strip()
                link = entry.get("link", "")
                age = _dedup.age_hours(entry)
                if not title or not link or (age is not None and age > max_age_h):
                    continue
                items.append({"title": title, "publisher": publisher, "link": link,
                              "desc": _strip_html(entry.get("summary", entry.get("description", "")))})
            print(f"OK: {publisher} ({len(feed.entries)} entries, {len(items)} fresh)", file=sys.stderr)
        except Exception as e:
            print(f"Feed error ({publisher}): {e}", file=sys.stderr)
        per_feed.append(items)

    result = []
    while len(result) < target and any(per_feed):
        for items in per_feed:
            while items:
                it = items.pop(0)
                if dd.take(it["title"], it["link"]):
                    result.append(it)
                    break
            if len(result) >= target:
                break
    return result


def _summarize_all(raw, label):
    out = []
    for i, art in enumerate(raw):
        print(f"  {label} {i+1}/{len(raw)}: {art['title'][:60]}", file=sys.stderr)
        summary = _groq_summarize_vi(art["title"], art["desc"], art["link"]) if _llm.available() else ""
        out.append({"title": art["title"], "publisher": art["publisher"], "link": art["link"],
                    "summary": summary or art["desc"][:300],
                    "ai_summary": bool(summary)})
        time.sleep(1)
    return out


def fetch_content():
    _override = os.environ.get("DATE_OVERRIDE")
    today = datetime.datetime.strptime(_override, "%Y-%m-%d") if _override else datetime.datetime.now()
    date_str = today.strftime("%d/%m/%Y")
    date_iso = today.strftime("%Y-%m-%d")
    day_num = today.timetuple().tm_yday
    USED_SOURCES.clear()

    _dedup.bootstrap_from_html(date_iso)
    dd = _dedup.Dedup(date_iso)

    # ── Phase 1–2: main news (round-robin by topic) + summaries ──────────────
    print("Fetching VN RSS feeds...", file=sys.stderr)
    articles = _summarize_all(_fetch_rss_articles(dd, target=8), "Summarizing")

    # ── Phase 3: Đà Nẵng ─────────────────────────────────────────────────────
    print("Fetching Đà Nẵng news...", file=sys.stderr)
    danang_articles = _summarize_all(_fetch_danang_articles(dd, n=3), "DaNang")
    weather = _src.weather_danang()

    # ── Phase 4: Viral MXH (RSS cross-source + Google Trends) ────────────────
    print("Fetching viral/entertainment articles + Google Trends...", file=sys.stderr)
    viral_articles = _fetch_viral_articles(dd, n=12)
    trends = _src.google_trends_vn(n=10)
    print(f"  Got {len(viral_articles)} viral articles, {len(trends)} trends", file=sys.stderr)
    viral = _groq_viral_content(date_iso, viral_articles, trends) if _llm.available() else ""

    # ── Phase 4b: Music (Apple Music VN chart) + fashion ─────────────────────
    music_arts, fashion_arts = _fetch_music_fashion_articles()
    music_arts = [a for a in music_arts if not dd.is_dup(a["title"], a["link"])]
    fashion_arts = [a for a in fashion_arts if not dd.is_dup(a["title"], a["link"])]
    chart = _src.apple_music_top_vn(n=10)
    music_fashion = (_groq_music_fashion_trend(date_iso, music_arts, fashion_arts, chart)
                     if _llm.available() else "")

    # ── Phase 4c–6: food, 3 tips, quote (topic rotation by day) ──────────────
    print("Generating food / tips / quote...", file=sys.stderr)
    ai = _llm.available
    food_of_day  = _groq_food_of_day(date_iso, day_num) if ai() else ""
    tip_beauty   = _groq_tip_beauty(date_iso, day_num) if ai() else ""
    tip_exercise = _groq_tip_exercise(date_iso, day_num) if ai() else ""
    tip_health   = _groq_tip_health(date_iso, day_num) if ai() else ""
    quote        = _groq_motivational_quote(date_iso) if ai() else ""

    # ── Phase 7: Crush hôm nay (verified data + live news) ───────────────────
    print("Building guy of the day...", file=sys.stderr)
    try:
        from handsome_guys import GUYS
    except Exception as e:
        print(f"handsome_guys import failed: {e}", file=sys.stderr)
        GUYS = []
    guy = _guy.build(GUYS, today.date(), dd)

    # ── Phase 8: Financial data ───────────────────────────────────────────────
    finance = _fetch_finance_data()

    # ── Phase 9: Policy & Legal digest ───────────────────────────────────────
    print("Fetching policy/legal articles...", file=sys.stderr)
    policy_articles = _fetch_policy_articles(dd, n=5)
    policy = _groq_policy_summary(date_iso, policy_articles) if ai() else ""

    for a in USED_SOURCES:
        dd.add(a["title"], a["link"])

    return {
        "date": date_str,
        "date_iso": date_iso,
        "articles": articles,
        "danang_articles": danang_articles,
        "weather": weather,
        "viral": viral,
        "music_fashion": music_fashion,
        "food_of_day": food_of_day,
        "tip_beauty": tip_beauty,
        "tip_exercise": tip_exercise,
        "tip_health": tip_health,
        "quote": quote,
        "guy": guy,
        "finance": finance,
        "policy": policy,
        "llm_stats": dict(_llm.STATS),
        "_dedup": dd,
    }


if __name__ == "__main__":
    import pprint
    _d = fetch_content()
    _d.pop("_dedup", None)
    pprint.pprint(_d)
