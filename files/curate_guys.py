#!/usr/bin/env python3
"""curate_guys.py - build files/handsome_guys.py from files/guys_seed.json.

Every fact in the output comes from Wikidata / Wikipedia / Wikimedia Commons:
  birthday  <- Wikidata P569 (day precision only)
  height    <- Wikidata P2048 ("" if absent)
  summary   <- Wikipedia REST summary (vi preferred, else en), first 2-3 sentences
  wiki_url  <- the same Wikipedia page
  image     <- Wikidata P18 -> Commons thumbnail (API-provided thumburl), saved
               under docs/assets/guys/v2/<slug>.<ext>; credit from extmetadata

Gates (an entry failing any is dropped and listed in the report):
  P31=human, P21=male, birth date with day precision, born >= MIN_BIRTH_YEAR,
  at least one entertainment occupation, a downloadable image, a Wikipedia summary.

Usage:  python3 files/curate_guys.py [--refresh]
  --refresh  re-download images even if the local file already exists.
Stdlib only. Re-runnable; existing images are reused unless --refresh.
"""

import html
import json
import os
import re
import sys
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SEED = os.path.join(ROOT, "files", "guys_seed.json")
OUT_PY = os.path.join(ROOT, "files", "handsome_guys.py")
OUT_HTML = os.path.join(ROOT, "docs", "all_handsome_guys.html")
DOCS = os.path.join(ROOT, "docs")
IMG_REL = "assets/guys/v2"
IMG_DIR = os.path.join(DOCS, IMG_REL)

UA = "TTXHXD-curator/1.0 (https://github.com/gauvaran/ttxhxd)"
WD_API = "https://www.wikidata.org/w/api.php"
COMMONS_API = "https://commons.wikimedia.org/w/api.php"
MIN_BIRTH_YEAR = 1985
MAX_IMG_BYTES = 1_500_000
THUMB_W, THUMB_W_SMALL = 500, 330
DELAY = 1.0  # seconds between Wikimedia requests (they 429 on bursts)

Q_HUMAN, Q_MALE = "Q5", "Q6581097"
Q_CM, Q_M = "Q174728", "Q11573"
# origin flag -> acceptable P27 (citizenship) values, for the consistency warning
FLAG_COUNTRY = {"🇻🇳": {"Q881"}, "🇰🇷": {"Q884"}, "🇨🇳": {"Q148"}, "🇭🇰": {"Q8646", "Q148"},
                "🇹🇼": {"Q865"}, "🇯🇵": {"Q17"}, "🇹🇭": {"Q869"}, "🇦🇺": {"Q408"},
                "🇨🇦": {"Q16"}, "🇺🇸": {"Q30"}}
ENTERTAINMENT = re.compile(
    r"actor|actress|singer|rapper|model|dancer|musician|idol|songwriter|"
    r"presenter|host|record producer|entertainer|composer|streamer|youtuber|"
    r"performer|vocalist|artist|television personality", re.I)

_last = [0.0]


def http(url, params=None, binary=False):
    """GET with UA, global throttle and retry on 429/5xx."""
    if params:
        url += "?" + urllib.parse.urlencode(params)
    for attempt in range(6):
        wait = _last[0] + DELAY - time.time()
        if wait > 0:
            time.sleep(wait)
        _last[0] = time.time()
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                data = r.read()
                return (data, r.headers.get("Content-Type", "")) if binary else json.loads(data)
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return (None, "") if binary else None
            if e.code in (429, 500, 502, 503, 504):
                time.sleep(int(e.headers.get("Retry-After") or 0) or 5 * (attempt + 1))
                continue
            raise
        except (urllib.error.URLError, TimeoutError):
            time.sleep(5 * (attempt + 1))
    raise RuntimeError(f"giving up on {url}")


def chunks(seq, n):
    for i in range(0, len(seq), n):
        yield seq[i:i + n]


# ---------- Wikidata ----------

def best_claims(claims, pid):
    """Non-deprecated claims; preferred-rank ones only, if any exist."""
    cs = [c for c in claims.get(pid, []) if c.get("rank") != "deprecated"
          and c["mainsnak"].get("snaktype") == "value"]
    pref = [c for c in cs if c.get("rank") == "preferred"]
    return pref or cs


def item_ids(claims, pid):
    return [c["mainsnak"]["datavalue"]["value"]["id"] for c in best_claims(claims, pid)]


def birth_date(claims):
    """(YYYY, MM, DD) or error string."""
    days = set()
    for c in best_claims(claims, "P569"):
        v = c["mainsnak"]["datavalue"]["value"]
        if v.get("precision") != 11:
            continue
        m = re.match(r"\+(\d{4})-(\d{2})-(\d{2})", v["time"])
        if m:
            days.add(tuple(int(x) for x in m.groups()))
    if not days:
        return "no day-precision birth date"
    if len(days) > 1:
        return f"conflicting birth dates {sorted(days)}"
    return days.pop()


def height(claims):
    for c in best_claims(claims, "P2048"):
        v = c["mainsnak"]["datavalue"]["value"]
        amt, unit = float(v["amount"]), v.get("unit", "").rsplit("/", 1)[-1]
        cm = amt if unit == Q_CM else amt * 100 if unit == Q_M else None
        if cm and 150 <= cm <= 200:
            cm = round(cm)
            return f"{cm // 100}m{cm % 100:02d}"
    return ""


def fetch_entities(qids, props, langs=None):
    out = {}
    for batch in chunks(qids, 50):
        p = {"action": "wbgetentities", "ids": "|".join(batch), "props": props, "format": "json"}
        if langs:
            p["languages"] = langs
        out.update(http(WD_API, p)["entities"])
    return out


# ---------- Commons ----------

def strip_html(s):
    s = re.sub(r"<[^>]+>", " ", s or "")
    return re.sub(r"\s+", " ", html.unescape(s)).strip()


def imageinfo(files, width):
    """{P18 filename: info dict} via batched imageinfo queries."""
    out = {}
    for batch in chunks(files, 50):
        r = http(COMMONS_API, {"action": "query", "format": "json", "prop": "imageinfo",
                               "iiprop": "url|extmetadata|mime|size", "iiurlwidth": width,
                               "titles": "|".join("File:" + f for f in batch)})
        q = r.get("query", {})
        norm = {n["to"]: n["from"] for n in q.get("normalized", [])}
        for page in q.get("pages", {}).values():
            if "imageinfo" not in page:
                continue
            orig = norm.get(page["title"], page["title"])
            out[orig[5:] if orig.startswith("File:") else orig] = page["imageinfo"][0]
            out[page["title"][5:]] = page["imageinfo"][0]
    return out


def credit(info):
    md = info.get("extmetadata", {})
    artist = strip_html(md.get("Artist", {}).get("value", ""))
    lic = strip_html(md.get("LicenseShortName", {}).get("value", ""))
    if len(artist) > 60:
        artist = artist[:57].rstrip() + "..."
    return ", ".join(x for x in (artist, lic) if x)


def sniff(data):
    if data[:3] == b"\xff\xd8\xff":
        return "jpg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return "gif"
    return None


def slugify(name):
    s = name.replace("đ", "d").replace("Đ", "D")
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "_", s.lower()).strip("_")


def existing_image(slug):
    for ext in ("jpg", "png", "webp", "gif"):
        p = os.path.join(IMG_DIR, f"{slug}.{ext}")
        if os.path.exists(p):
            with open(p, "rb") as f:
                if sniff(f.read(16)) == ext:
                    return p
    return None


def download(url):
    data, _ = http(url, binary=True)
    if not data:
        return None, None
    return data, sniff(data)


# ---------- Wikipedia ----------

def summary(sitelinks):
    for lang in ("vi", "en"):
        sl = sitelinks.get(f"{lang}wiki")
        if not sl:
            continue
        title = urllib.parse.quote(sl["title"].replace(" ", "_"), safe="")
        r = http(f"https://{lang}.wikipedia.org/api/rest_v1/page/summary/{title}")
        if not r or r.get("type") != "standard" or not r.get("extract"):
            continue
        text = re.sub(r"\s+", " ", r["extract"]).strip()
        sents = re.split(r"(?<=[.!?])\s+(?=[A-ZÀ-Ỹ\"“(])", text)
        out = ""
        for s in sents[:3]:
            if out and len(out) + len(s) > 450:
                break
            out = f"{out} {s}".strip()
        url = r.get("content_urls", {}).get("desktop", {}).get("page") or \
            f"https://{lang}.wikipedia.org/wiki/{title}"
        return out, url
    return None, None


# ---------- main ----------

def main():
    refresh = "--refresh" in sys.argv
    seed = json.load(open(SEED, encoding="utf-8"))
    os.makedirs(IMG_DIR, exist_ok=True)
    dropped = []  # (name, reason)
    warnings = []

    slugs = {}
    for s in seed:
        slug = slugify(s["name"])
        assert slug and slug not in slugs, f"slug collision: {s['name']} vs {slugs.get(slug)}"
        slugs[slug] = s["name"]
        s["_slug"] = slug

    print(f"Fetching {len(seed)} Wikidata entities...", file=sys.stderr)
    ents = fetch_entities([s["qid"] for s in seed], "claims|sitelinks|descriptions", "en")
    occ_ids = sorted({o for e in ents.values() for o in item_ids(e.get("claims", {}), "P106")})
    occ = {q: (e.get("labels", {}).get("en") or {}).get("value", "")
           for q, e in fetch_entities(occ_ids, "labels", "en").items()}

    cands = []
    for s in seed:
        e = ents.get(s["qid"], {})
        cl = e.get("claims", {})
        if "missing" in e or not cl:
            dropped.append((s["name"], "Wikidata entity missing")); continue
        if Q_HUMAN not in item_ids(cl, "P31"):
            dropped.append((s["name"], "not a human (P31)")); continue
        if Q_MALE not in item_ids(cl, "P21"):
            dropped.append((s["name"], "not male (P21)")); continue
        bd = birth_date(cl)
        if isinstance(bd, str):
            dropped.append((s["name"], bd)); continue
        if bd[0] < MIN_BIRTH_YEAR:
            dropped.append((s["name"], f"born {bd[0]} (< {MIN_BIRTH_YEAR})")); continue
        jobs = [occ.get(o, "") for o in item_ids(cl, "P106")]
        if not jobs:  # no P106 at all: fall back to the Wikidata description
            jobs = [(e.get("descriptions", {}).get("en") or {}).get("value", "")]
        if not any(ENTERTAINMENT.search(j) for j in jobs):
            dropped.append((s["name"], f"no entertainment occupation {jobs}")); continue
        imgs = [c["mainsnak"]["datavalue"]["value"] for c in best_claims(cl, "P18")]
        if not imgs:
            dropped.append((s["name"], "no image (P18)")); continue
        p27 = set(item_ids(cl, "P27"))
        want = set().union(*(v for f, v in FLAG_COUNTRY.items() if f in s["origin"]))
        if p27 and not (p27 <= want or (want and p27 & want and len(p27) == 1)):
            if p27 - want:
                warnings.append(f"{s['name']}: origin '{s['origin']}' vs P27 {sorted(p27)}")
        s.update(_bd=bd, _height=height(cl), _p18=imgs[0], _sitelinks=e.get("sitelinks", {}))
        cands.append(s)

    print(f"Commons imageinfo for {len(cands)} files...", file=sys.stderr)
    infos = imageinfo([s["_p18"] for s in cands], THUMB_W)

    guys = []
    for s in cands:
        info = infos.get(s["_p18"]) or infos.get(s["_p18"].replace("_", " "))
        if not info:
            dropped.append((s["name"], f"Commons file not found: {s['_p18']}")); continue
        summ, wiki_url = summary(s["_sitelinks"])
        if not summ:
            dropped.append((s["name"], "no vi/en Wikipedia summary")); continue
        path = None if refresh else existing_image(s["_slug"])
        if not path:
            url = info.get("thumburl") or info.get("url")
            data, ext = download(url)
            if data and ext and len(data) > MAX_IMG_BYTES:
                small = imageinfo([s["_p18"]], THUMB_W_SMALL)
                si = small.get(s["_p18"]) or next(iter(small.values()), {})
                data, ext = download(si.get("thumburl") or si.get("url"))
            if not data or not ext:
                dropped.append((s["name"], f"image download failed/not an image: {url}")); continue
            if len(data) > MAX_IMG_BYTES:
                dropped.append((s["name"], f"image too large ({len(data)} B)")); continue
            for old in ("jpg", "png", "webp", "gif"):  # drop stale other-extension copy
                p = os.path.join(IMG_DIR, f"{s['_slug']}.{old}")
                if old != ext and os.path.exists(p):
                    os.remove(p)
            path = os.path.join(IMG_DIR, f"{s['_slug']}.{ext}")
            with open(path, "wb") as f:
                f.write(data)
        y, m, d = s["_bd"]
        guys.append({
            "name": s["name"],
            "origin": s["origin"],
            "job": s["job"],
            "birthday": f"{d:02d}/{m:02d}/{y}",
            "height": s["_height"],
            "summary": summ,
            "wiki_url": wiki_url,
            "wikidata": f"https://www.wikidata.org/wiki/{s['qid']}",
            "image_url": f"{IMG_REL}/{os.path.basename(path)}",
            "image_credit": credit(info) or "Không rõ tác giả",
            "tags": s["tags"],
        })
        print(f"  ok  {s['name']}", file=sys.stderr)

    write_py(guys)
    write_html(guys)
    print(f"\nKept {len(guys)} / {len(seed)}. Dropped {len(dropped)}:")
    for n, r in dropped:
        print(f"  - {n}: {r}")
    if warnings:
        print(f"\nOrigin vs Wikidata P27 citizenship ({len(warnings)} to review):")
        for w in warnings:
            print(f"  ! {w}")


HEADER = '''"""handsome_guys.py - "Trai Đẹp Hôm Nay" dataset.

GENERATED by files/curate_guys.py from files/guys_seed.json - do not edit by hand;
edit the seed (name / Wikidata QID / origin / job / tags) and re-run the script.

Fields (all verifiable):
  name, origin, job, tags  - curated in guys_seed.json
  birthday     - "DD/MM/YYYY", Wikidata P569 (day precision)
  height       - e.g. "1m81" from Wikidata P2048, "" if unknown
  summary      - first 2-3 sentences of the Wikipedia summary (vi, else en)
  wiki_url     - that Wikipedia page; wikidata - Wikidata item URL
  image_url    - local file relative to docs/ (Commons thumbnail of P18)
  image_credit - author + license from Commons extmetadata
Age and zodiac are computed at runtime; the playful intro is generated at runtime
by an LLM strictly from these fields.
"""

GUYS = '''


def write_py(guys):
    with open(OUT_PY, "w", encoding="utf-8") as f:
        f.write(HEADER + json.dumps(guys, ensure_ascii=False, indent=1) + "\n")


def write_html(guys):
    e = lambda s: html.escape(str(s), quote=True)  # noqa: E731
    cards = "\n".join(
        f'<figure><img src="{e(g["image_url"])}" alt="{e(g["name"])}" loading="lazy">'
        f'<figcaption><b>{i}. {e(g["name"])}</b><br>{e(g["origin"])} · {e(g["job"])}<br>'
        f'🎂 {e(g["birthday"])}{" · " + e(g["height"]) if g["height"] else ""}<br>'
        f'<small>Ảnh: {e(g["image_credit"])}</small><br>'
        f'<a href="{e(g["wiki_url"])}">Wikipedia</a> · <a href="{e(g["wikidata"])}">Wikidata</a>'
        f'</figcaption></figure>' for i, g in enumerate(guys, 1))
    page = f"""<!doctype html>
<html lang="vi"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Trai Đẹp - review ảnh</title>
<style>
body{{font-family:Arial,sans-serif;margin:16px;background:#fff7fa;color:#333}}
h1{{color:#c2185b;font-size:22px}}
.grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(200px,1fr));gap:14px}}
figure{{margin:0;background:#fff;border-radius:10px;box-shadow:0 1px 4px #0002;overflow:hidden}}
img{{width:100%;aspect-ratio:3/4;object-fit:cover;object-position:top;display:block;background:#eee}}
figcaption{{padding:8px 10px;font-size:13px;line-height:1.5}}
small{{color:#888}} a{{color:#c2185b}}
</style></head><body>
<h1>Trai Đẹp Hôm Nay - {len(guys)} nhân vật (review ảnh)</h1>
<p>Generated by files/curate_guys.py. Kiểm tra ảnh có đúng người không.</p>
<div class="grid">
{cards}
</div></body></html>
"""
    with open(OUT_HTML, "w", encoding="utf-8") as f:
        f.write(page)


if __name__ == "__main__":
    main()
