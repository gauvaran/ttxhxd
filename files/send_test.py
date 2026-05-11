#!/usr/bin/env python3
"""One-shot: send today's existing newsletter HTML as a test email."""
import os, sys
sys.path.insert(0, os.path.dirname(__file__))

# Load .env
_env = os.path.join(os.path.dirname(__file__), ".env")
if os.path.exists(_env):
    with open(_env) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())

from ai_news_bot import send_email

html_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "docs", "2026-05-09.html")
with open(html_path, "r", encoding="utf-8") as f:
    html = f.read()

subject = "TTXHXD 🌸 Test — Bản tin ngày 09/05/2026"
plain = "Bản tin TTXHXD ngày 09/05/2026. Xem HTML để đọc đầy đủ."

print(f"Sending to BCC: {os.environ.get('EMAIL_BCC', '(not set)')}")
ok = send_email(subject, html, plain)
sys.exit(0 if ok else 1)
