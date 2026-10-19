"""
dedup.py - Freshness + duplicate control shared by every news section.

- History: docs/history.json keeps normalized titles + links of items published in
  the last HISTORY_DAYS days, so stories never repeat across days.
- Registry: within one run, items picked by an earlier section (main news) block
  near-duplicates in later sections (Đà Nẵng, policy, viral).
- Near-duplicate = same canonical link OR token-set Jaccard >= threshold on
  accent-stripped titles ("same event, different outlet").
"""

import calendar
import datetime
import json
import os
import re
import unicodedata

DOCS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "docs")
HISTORY_PATH = os.path.join(DOCS_DIR, "history.json")
HISTORY_DAYS = 14
JACCARD = 0.5

_STOP = {"va", "cua", "la", "co", "cho", "voi", "trong", "tai", "da", "se", "duoc", "nhung",
         "cac", "mot", "nay", "khi", "tu", "den", "ve", "o", "thi", "hon", "nguoi", "nam",
         "ngay", "hom", "moi", "the", "a", "an", "of", "to", "in", "on"}


def strip_accents(s):
    s = unicodedata.normalize("NFD", s or "").replace("đ", "d").replace("Đ", "D")
    return "".join(c for c in s if unicodedata.category(c) != "Mn")


def tokens(title):
    words = re.findall(r"[a-z0-9]+", strip_accents(title).lower())
    return {w for w in words if len(w) > 1 and w not in _STOP}


def canon_link(link):
    link = (link or "").split("#")[0].split("?")[0].rstrip("/")
    return re.sub(r"^https?://(www\.|m\.)?", "", link).lower()


def jaccard(a, b):
    return len(a & b) / len(a | b) if a and b else 0.0


def age_hours(entry, now=None):
    """Hours since a feedparser entry (or dict with pub_dt) was published; None if unknown."""
    now = now or datetime.datetime.now(datetime.timezone.utc)
    pub = None
    if isinstance(entry, dict) and entry.get("pub_dt"):
        pub = entry["pub_dt"]
        if pub.tzinfo is None:  # baomoi timestamps are local (GMT+7) naive datetimes
            pub = pub.replace(tzinfo=datetime.timezone(datetime.timedelta(hours=7)))
    else:
        st = entry.get("published_parsed") or entry.get("updated_parsed")
        if st:
            pub = datetime.datetime.fromtimestamp(calendar.timegm(st), datetime.timezone.utc)
    if pub is None:
        return None
    return (now - pub).total_seconds() / 3600


class Dedup:
    def __init__(self, today_iso, history_path=HISTORY_PATH):
        self.today = today_iso
        self.path = history_path
        self.history = self._load()
        self._past_links = set()
        self._past_tokens = []
        for day, items in self.history.items():
            if day >= today_iso:  # re-running a day must not block its own stories
                continue
            for it in items:
                self._past_links.add(it["l"])
                self._past_tokens.append(set(it["k"]))
        self.picked = []  # (canon_link, tokens, title) chosen in this run

    def _load(self):
        try:
            with open(self.path, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}

    def is_dup(self, title, link=""):
        cl, tk = canon_link(link), tokens(title)
        if cl and cl in self._past_links:
            return True
        for _, ptk, _ in self.picked:
            if jaccard(tk, ptk) >= JACCARD:
                return True
        if cl and any(cl == pl for pl, _, _ in self.picked):
            return True
        return any(jaccard(tk, ptk) >= JACCARD for ptk in self._past_tokens)

    def add(self, title, link=""):
        self.picked.append((canon_link(link), tokens(title), title))

    def take(self, title, link=""):
        """Return True and register the item if it is fresh; False if duplicate."""
        if self.is_dup(title, link):
            return False
        self.add(title, link)
        return True

    def save(self):
        cutoff = (datetime.date.fromisoformat(self.today)
                  - datetime.timedelta(days=HISTORY_DAYS)).isoformat()
        hist = {d: v for d, v in self.history.items() if d > cutoff and d != self.today}
        hist[self.today] = [{"l": cl, "k": sorted(tk), "t": t[:120]} for cl, tk, t in self.picked]
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(dict(sorted(hist.items())), f, ensure_ascii=False, separators=(",", ":"))


def bootstrap_from_html(today_iso, days=7, history_path=HISTORY_PATH):
    """One-off seed of history.json from the last `days` newsletter HTML files."""
    import html as _html
    if os.path.exists(history_path):
        return
    dated = sorted(f[:-5] for f in os.listdir(DOCS_DIR)
                   if re.match(r"\d{4}-\d{2}-\d{2}\.html$", f) and f[:-5] < today_iso)[-days:]
    hist = {}
    for d in dated:
        content = open(os.path.join(DOCS_DIR, d + ".html"), encoding="utf-8").read()
        items = []
        # Article cards: bold title <p> followed by the "Đọc thêm" source link.
        for title, link in re.findall(
                r'font-weight:bold;color:#[0-9A-Fa-f]{6}[^>]*>([^<]{8,})</p>.*?href="(https?://[^"]+)"',
                content, re.S):
            t = _html.unescape(title).strip()
            if "Heo Xinh" in t:  # masthead, not an article
                continue
            items.append({"l": canon_link(link), "k": sorted(tokens(t)), "t": t[:120]})
        hist[d] = items
    os.makedirs(os.path.dirname(history_path), exist_ok=True)
    with open(history_path, "w", encoding="utf-8") as f:
        json.dump(hist, f, ensure_ascii=False, separators=(",", ":"))
