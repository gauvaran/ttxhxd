"""
sources.py - Grounding data sources (no API keys needed).

  weather_danang()      Open-Meteo daily forecast for Đà Nẵng
  google_trends_vn()    Google Trends daily trending searches (VN) + linked news
  apple_music_top_vn()  Apple Music most-played songs in Vietnam
  google_news(query)    Google News RSS search (Vietnamese edition)
  article_text(url)     Plain paragraph text of an article page (for summaries)
"""

import json
import sys
import urllib.parse
import urllib.request
from html.parser import HTMLParser

import feedparser

UA = "Mozilla/5.0 (compatible; TTXHXDBot/1.0)"
BROWSER_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")


def _log(msg):
    print(msg, file=sys.stderr)


def _get_json(url, timeout=15):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


# WMO weather codes → Vietnamese label + emoji
_WMO = {0: ("Trời quang", "☀️"), 1: ("Ít mây", "🌤️"), 2: ("Có mây", "⛅"), 3: ("Nhiều mây", "☁️"),
        45: ("Sương mù", "🌫️"), 48: ("Sương mù", "🌫️"), 51: ("Mưa phùn", "🌦️"), 53: ("Mưa phùn", "🌦️"),
        55: ("Mưa phùn dày", "🌧️"), 61: ("Mưa nhỏ", "🌧️"), 63: ("Mưa vừa", "🌧️"), 65: ("Mưa to", "🌧️"),
        80: ("Mưa rào", "🌦️"), 81: ("Mưa rào", "🌧️"), 82: ("Mưa rào rất to", "⛈️"),
        95: ("Dông", "⛈️"), 96: ("Dông kèm mưa đá", "⛈️"), 99: ("Dông kèm mưa đá", "⛈️")}


def weather_danang():
    url = ("https://api.open-meteo.com/v1/forecast?latitude=16.0544&longitude=108.2022"
           "&daily=weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max,uv_index_max"
           "&timezone=Asia%2FHo_Chi_Minh&forecast_days=1")
    try:
        d = _get_json(url)["daily"]
        code = d["weather_code"][0]
        label, emoji = _WMO.get(code, ("Thời tiết thay đổi", "🌈"))
        rain = d.get("precipitation_probability_max", [None])[0]
        uv = d.get("uv_index_max", [None])[0]
        tip = ("Nhớ mang ô/áo mưa nha ☔" if (rain or 0) >= 60 else
               "Kem chống nắng là chân ái hôm nay 🧴" if (uv or 0) >= 7 else
               "Thời tiết dễ chịu, diện đồ xinh đi làm thôi 💃")
        return {"label": label, "emoji": emoji,
                "tmin": round(d["temperature_2m_min"][0]), "tmax": round(d["temperature_2m_max"][0]),
                "rain": rain, "uv": uv, "tip": tip, "source": "Open-Meteo"}
    except Exception as e:
        _log(f"weather error: {e}")
        return {}


def google_trends_vn(n=10):
    """Trending searches in Vietnam today, each with its top linked news article."""
    try:
        feed = feedparser.parse("https://trends.google.com/trending/rss?geo=VN",
                                request_headers={"User-Agent": UA})
    except Exception as e:
        _log(f"trends error: {e}")
        return []
    out = []
    for e in feed.entries[:n]:
        out.append({"keyword": e.get("title", ""),
                    "traffic": e.get("ht_approx_traffic", ""),
                    "news_title": e.get("ht_news_item_title", ""),
                    "news_url": e.get("ht_news_item_url", ""),
                    "news_source": e.get("ht_news_item_source", "")})
    return [t for t in out if t["keyword"]]


def apple_music_top_vn(n=10):
    try:
        res = _get_json(f"https://rss.applemarketingtools.com/api/v2/vn/music/most-played/{n}/songs.json")
        return [{"rank": i + 1, "title": s["name"], "artist": s["artistName"], "url": s.get("url", "")}
                for i, s in enumerate(res["feed"]["results"])]
    except Exception as e:
        _log(f"apple music error: {e}")
        return []


def google_news(query, when="2d", n=20):
    """Google News RSS search. Links are news.google.com redirects (fine for readers)."""
    q = urllib.parse.quote_plus(f"{query} when:{when}")
    url = f"https://news.google.com/rss/search?q={q}&hl=vi&gl=VN&ceid=VN:vi"
    try:
        feed = feedparser.parse(url, request_headers={"User-Agent": UA})
    except Exception as e:
        _log(f"google news error ({query}): {e}")
        return []
    out = []
    for e in feed.entries[:n]:
        src = (e.get("source") or {}).get("title", "Google News")
        title = e.get("title", "")
        if src and title.endswith(" - " + src):
            title = title[: -len(src) - 3]
        out.append({"title": title.strip(), "publisher": src, "link": e.get("link", ""),
                    "desc": "", "published_parsed": e.get("published_parsed")})
    return out


class _Paragraphs(HTMLParser):
    _SKIP = {"script", "style", "nav", "header", "footer", "aside", "figcaption", "form"}

    def __init__(self):
        super().__init__()
        self.in_p = 0
        self.skip = 0
        self.buf, self.paras = [], []

    def handle_starttag(self, tag, attrs):
        if tag in self._SKIP:
            self.skip += 1
        elif tag == "p":
            self.in_p += 1
            self.buf = []

    def handle_endtag(self, tag):
        if tag in self._SKIP and self.skip:
            self.skip -= 1
        elif tag == "p" and self.in_p:
            self.in_p -= 1
            text = " ".join("".join(self.buf).split())
            if len(text) >= 60:
                self.paras.append(text)

    def handle_data(self, data):
        if self.in_p and not self.skip:
            self.buf.append(data)


def article_text(url, max_chars=3500):
    """Best-effort article body text; '' on failure. Skips Google News redirect links."""
    if not url or "news.google.com" in url:
        return ""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": BROWSER_UA})
        with urllib.request.urlopen(req, timeout=12) as r:
            html = r.read(1_500_000).decode("utf-8", errors="ignore")
        p = _Paragraphs()
        p.feed(html)
        return " ".join(p.paras)[:max_chars]
    except Exception as e:
        _log(f"article_text error ({url[:60]}): {e}")
        return ""
