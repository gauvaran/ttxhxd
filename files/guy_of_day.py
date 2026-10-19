"""
guy_of_day.py - Pick and enrich the "Crush Hôm Nay" entry.

Selection: a guy whose birthday is today wins; otherwise a per-year seeded
shuffle (no repeats until the whole list has been shown, order changes yearly).
Enrichment (all derived from verified fields in handsome_guys.py):
  age, zodiac        — computed from birthday
  hot_news           — a Google News headline about him from the last 7 days
  intro              — playful LLM text constrained to the verified facts;
                       falls back to the Wikipedia summary
"""

import datetime
import random
import re

import llm
import sources

_ZODIAC = [((1, 20), "Ma Kết ♑"), ((2, 19), "Bảo Bình ♒"), ((3, 21), "Song Ngư ♓"),
           ((4, 20), "Bạch Dương ♈"), ((5, 21), "Kim Ngưu ♉"), ((6, 22), "Song Tử ♊"),
           ((7, 23), "Cự Giải ♋"), ((8, 23), "Sư Tử ♌"), ((9, 23), "Xử Nữ ♍"),
           ((10, 24), "Thiên Bình ♎"), ((11, 23), "Bọ Cạp ♏"), ((12, 22), "Nhân Mã ♐"),
           ((12, 32), "Ma Kết ♑")]


def parse_birthday(s):
    try:
        return datetime.datetime.strptime(s, "%d/%m/%Y").date()
    except (TypeError, ValueError):
        return None


def zodiac(bd):
    for (m, d), name in _ZODIAC:
        if (bd.month, bd.day) < (m, d):
            return name
    return "Ma Kết ♑"


def age_on(bd, day):
    return day.year - bd.year - ((day.month, day.day) < (bd.month, bd.day))


def pick(guys, day):
    if not guys:
        return None, False
    born_today = [g for g in guys
                  if (bd := parse_birthday(g.get("birthday"))) and (bd.day, bd.month) == (day.day, day.month)]
    if born_today:
        return born_today[day.year % len(born_today)], True
    order = list(range(len(guys)))
    random.Random(f"ttxhxd-{day.year}").shuffle(order)
    return guys[order[(day.timetuple().tm_yday - 1) % len(guys)]], False


def _search_names(guy):
    """'RM (Kim Namjoon)' → ['RM', 'Kim Namjoon']"""
    name = guy.get("name", "")
    parts = [name.split("(")[0].strip()] + re.findall(r"\(([^)]+)\)", name)
    return [p for p in parts if len(p) >= 2]


def _mentions(name, title):
    """Exact, case-sensitive, accent-sensitive name match on word boundaries —
    'Lý Hiện' must not match '...quản lý hiện đại'."""
    return re.search(rf"(?<!\w){re.escape(name)}(?!\w)", title) is not None


def hot_news(guy, picker=None):
    for name in _search_names(guy):
        if len(name) < 3:  # 'V', 'RM' alone return noise
            continue
        for item in sources.google_news(f'"{name}"', when="7d", n=10):
            if _mentions(name, item["title"]):
                if picker is None or picker.take(item["title"], item["link"]):
                    return item
    return None


def _intro(guy, facts, hot):
    hot_line = f"- Tin mới (7 ngày qua): {hot['title']} ({hot['publisher']})\n" if hot else ""
    prompt = (
        "Bạn viết mục 'Crush Hôm Nay' cho bản tin của chị em văn phòng: dí dỏm, ngọt, chêm chút tiếng lóng.\n"
        "Viết 1 đoạn 60–90 từ tiếng Việt về nhân vật dưới đây.\n"
        "RÀNG BUỘC: CHỈ dùng dữ kiện được cung cấp. KHÔNG thêm số liệu, tên tác phẩm, giải thưởng, "
        "chiều cao, cân nặng, chuyện tình cảm hay bất kỳ chi tiết nào không có bên dưới. "
        "Thiếu dữ kiện thì khen visual/vibe chung chung.\n\n"
        f"{facts}\n{hot_line}\n"
        "Chỉ trả về đoạn văn, không tiêu đề."
    )
    return llm.call(prompt, max_tokens=300, temperature=0.8)


def build(guys, day, picker=None):
    guy, birthday_today = pick(guys, day)
    if not guy:
        return None
    g = dict(guy)
    bd = parse_birthday(g.get("birthday"))
    if bd:
        g["zodiac"] = zodiac(bd)
        g["age"] = age_on(bd, day)
    g["birthday_today"] = birthday_today
    try:
        g["hot_news"] = hot_news(g, picker)
    except Exception:
        g["hot_news"] = None
    facts = "\n".join(f"- {k}: {v}" for k, v in [
        ("Tên", g.get("name")), ("Quốc gia", g.get("origin")), ("Nghề", g.get("job")),
        ("Ngày sinh", g.get("birthday")), ("Tuổi", g.get("age")), ("Chiều cao", g.get("height")),
        ("Cung hoàng đạo", g.get("zodiac")), ("Tóm tắt Wikipedia", g.get("summary")),
        ("Hôm nay là sinh nhật", "Có 🎂" if birthday_today else None)] if v)
    g["intro"] = (_intro(g, facts, g["hot_news"]) if llm.available() else "") or g.get("summary", "")
    return g
