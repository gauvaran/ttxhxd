#!/usr/bin/env python3
"""
Backfill newsletter HTML for past N days without sending email.
Usage:
  python files/backfill.py           # last 30 days
  BACKFILL_DAYS=7 python files/backfill.py
"""
import os, sys, subprocess, datetime

FILES_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR  = os.path.dirname(FILES_DIR)
DOCS_DIR  = os.path.join(ROOT_DIR, "docs")

_env_path = os.path.join(FILES_DIR, ".env")
if os.path.exists(_env_path):
    with open(_env_path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())

N_DAYS = int(os.environ.get("BACKFILL_DAYS", "30"))
today  = datetime.date.today()
dates  = [today - datetime.timedelta(days=d) for d in range(N_DAYS, 0, -1)]

print(f"Backfilling {N_DAYS} days: {dates[0]} → {dates[-1]}")
generated = skipped = 0

for d in dates:
    slug = d.strftime("%Y-%m-%d")
    if os.path.exists(os.path.join(DOCS_DIR, f"{slug}.html")):
        print(f"[skip] {slug}")
        skipped += 1
        continue

    print(f"\n{'='*55}\n[run]  {slug}\n{'='*55}")
    env = os.environ.copy()
    env["NO_EMAIL"]          = "1"
    env["DATE_OVERRIDE"]     = slug
    env["WEB_DATE_OVERRIDE"] = slug

    rc = subprocess.run(
        [sys.executable, os.path.join(FILES_DIR, "ai_news_bot.py")],
        env=env,
    ).returncode

    if rc != 0:
        print(f"[error] {slug} failed (exit {rc}) — stopping", file=sys.stderr)
        sys.exit(1)
    generated += 1

print(f"\nDone: {generated} generated, {skipped} skipped.")
