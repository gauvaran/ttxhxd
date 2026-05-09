#!/usr/bin/env python3
"""
ai_news_bot.py - TTXHXD: Build HTML newsletter, send email, save web pages
"""

import smtplib
import sys
import os
import re
import time
import logging
import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.header import Header
from email.utils import formataddr
from html import escape as h
import re as _re

_env_file = os.path.join(os.path.dirname(__file__), ".env")
if os.path.exists(_env_file):
    with open(_env_file) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())

from fetch_content import fetch_content

# ─── CONFIG ───────────────────────────────────────────────────────────────────
EMAIL_FROM     = os.environ.get("EMAIL_FROM", "")
EMAIL_TO       = os.environ.get("EMAIL_TO",   "")
EMAIL_BCC      = os.environ.get("EMAIL_BCC",  "")
EMAIL_PASSWORD = os.environ.get("EMAIL_PASSWORD", "")
SMTP_HOST      = "smtp.gmail.com"
SMTP_PORT      = 587
MAX_RETRIES    = 3
RETRY_DELAY    = 15
LOG_FILE       = os.path.join(os.path.dirname(__file__), "bot.log")

# Color palette — rose/feminine
C_PRIMARY   = "#8B1A4A"   # deep rose header
C_ACCENT    = "#C2185B"   # vibrant rose
C_LIGHT     = "#FFF0F5"   # blush background
C_PINK_BG   = "#FCE4EC"   # light pink section
C_AMBER_BG  = "#FFF8E1"   # light amber (tip odd)
C_GREEN_BG  = "#E8F5E9"   # light green (tip even)
C_GOLD      = "#F9A825"   # star gold
C_TEAL_BG   = "#E0F2F1"   # teal bg (Đà Nẵng section)
C_TEAL      = "#00796B"   # teal accent
C_PURPLE_BG = "#F3E5F5"   # purple bg (quote section)
C_PURPLE    = "#7B1FA2"   # purple accent
C_BEAUTY_BG = "#FCE4EC"   # beauty tip bg (already C_PINK_BG alias)
# ──────────────────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.FileHandler(LOG_FILE), logging.StreamHandler(sys.stdout)]
)


def md_to_html(text):
    text = h(text)
    text = _re.sub(
        r'```(?:\w+)?\n?(.*?)```',
        lambda m: f'<pre style="background:#F3F4F6;color:#1F2937;padding:10px 14px;border:1px solid #D1D5DB;border-radius:4px;font-size:12px;overflow-x:auto;margin:8px 0;">{m.group(1).strip()}</pre>',
        text, flags=_re.DOTALL
    )
    text = _re.sub(r'`([^`]+)`', r'<code style="background:#F3F4F6;color:#1F2937;border:1px solid #D1D5DB;padding:1px 5px;border-radius:3px;font-size:12px;">\1</code>', text)
    text = _re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', text)
    text = _re.sub(r'\*(.+?)\*', r'<em>\1</em>', text)
    text = _re.sub(r'^#{1,3}\s+(.+)$', r'<strong style="font-size:14px;">\1</strong>', text, flags=_re.MULTILINE)
    text = _re.sub(r'^[\-\*]\s+(.+)$', r'&nbsp;&nbsp;&#8226;&nbsp;\1', text, flags=_re.MULTILINE)
    text = _re.sub(r'\n{2,}', '</p><p style="margin:8px 0;font-size:13px;color:#333;line-height:1.8;">', text)
    text = text.replace('\n', '<br>')
    text = f'<p style="margin:0;font-size:13px;color:#333;line-height:1.8;">{text}</p>'
    return text


def build_html(data):
    articles         = data["articles"]
    danang_articles  = data.get("danang_articles", [])
    date_str         = data["date"]
    viral            = data.get("viral", "")
    music_fashion    = data.get("music_fashion", "")
    food_of_day      = data.get("food_of_day", "")
    tip              = data.get("tip", "")
    tip_type         = data.get("tip_type", "food")
    quote            = data.get("quote", "")
    guy              = data.get("guy")

    # ── Articles ─────────────────────────────────────────────────────────────
    articles_html = ""
    for i, art in enumerate(articles, 1):
        summary_block = ""
        if art.get("summary"):
            summary_block = f"""
            <tr>
              <td colspan="2" style="padding:10px 0 0 44px;">
                <table role="presentation" width="100%" cellpadding="0" cellspacing="0">
                  <tr>
                    <td bgcolor="#FFF0F5" style="background-color:#FFF0F5;padding:12px 14px;border-left:3px solid {C_ACCENT};">
                      <p style="margin:0;font-size:13px;color:#333333;line-height:1.7;">{h(art["summary"])}</p>
                    </td>
                  </tr>
                </table>
              </td>
            </tr>"""

        pub_html  = f'<span style="color:#888;">{h(art["publisher"])}</span>&nbsp;&nbsp;' if art.get("publisher") else ""
        link_html = f'<a href="{h(art["link"], quote=True)}" style="color:{C_ACCENT};text-decoration:none;font-size:12px;">&#128279;&nbsp;Đọc thêm &#8594;</a>' if art.get("link") else ""

        articles_html += f"""
          <tr>
            <td bgcolor="#FFFFFF" style="background-color:#FFFFFF;padding:20px 30px;">
              <table role="presentation" width="100%" cellpadding="0" cellspacing="0">
                <tr>
                  <td width="32" valign="top" style="padding-right:12px;padding-top:2px;">
                    <table role="presentation" cellpadding="0" cellspacing="0">
                      <tr>
                        <td bgcolor="{C_PRIMARY}" width="28" height="28" align="center" valign="middle"
                            style="background-color:{C_PRIMARY};width:28px;height:28px;border-radius:14px;text-align:center;vertical-align:middle;">
                          <span style="color:#FFFFFF;font-size:13px;font-weight:bold;font-family:Arial,sans-serif;">{i}</span>
                        </td>
                      </tr>
                    </table>
                  </td>
                  <td valign="top">
                    <p style="margin:0 0 6px;font-size:15px;font-weight:bold;color:{C_PRIMARY};line-height:1.4;font-family:Arial,sans-serif;">{h(art["title"])}</p>
                    <p style="margin:0;font-size:12px;font-family:Arial,sans-serif;">{pub_html}{link_html}</p>
                  </td>
                </tr>
                {summary_block}
              </table>
            </td>
          </tr>
          <tr>
            <td style="padding:0 30px;">
              <table role="presentation" width="100%" cellpadding="0" cellspacing="0">
                <tr><td height="1" bgcolor="#F8D7E3" style="background-color:#F8D7E3;font-size:0;line-height:0;">&nbsp;</td></tr>
              </table>
            </td>
          </tr>"""

    # ── Đà Nẵng section ──────────────────────────────────────────────────────
    danang_html = ""
    if danang_articles:
        danang_items = ""
        for i, art in enumerate(danang_articles, 1):
            summary_block = ""
            if art.get("summary"):
                summary_block = f"""
                <tr>
                  <td colspan="2" style="padding:8px 0 0 44px;">
                    <table role="presentation" width="100%" cellpadding="0" cellspacing="0">
                      <tr>
                        <td bgcolor="#E0F2F1" style="background-color:#E0F2F1;padding:10px 14px;border-left:3px solid {C_TEAL};">
                          <p style="margin:0;font-size:13px;color:#333333;line-height:1.7;">{h(art["summary"])}</p>
                        </td>
                      </tr>
                    </table>
                  </td>
                </tr>"""
            pub_html  = f'<span style="color:#888;">{h(art["publisher"])}</span>&nbsp;&nbsp;' if art.get("publisher") else ""
            link_html = f'<a href="{h(art["link"], quote=True)}" style="color:{C_TEAL};text-decoration:none;font-size:12px;">&#128279;&nbsp;Đọc thêm &#8594;</a>' if art.get("link") else ""
            danang_items += f"""
              <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin-bottom:12px;">
                <tr>
                  <td width="32" valign="top" style="padding-right:12px;padding-top:2px;">
                    <table role="presentation" cellpadding="0" cellspacing="0">
                      <tr>
                        <td bgcolor="{C_TEAL}" width="28" height="28" align="center" valign="middle"
                            style="background-color:{C_TEAL};width:28px;height:28px;border-radius:14px;text-align:center;vertical-align:middle;">
                          <span style="color:#FFFFFF;font-size:13px;font-weight:bold;font-family:Arial,sans-serif;">{i}</span>
                        </td>
                      </tr>
                    </table>
                  </td>
                  <td valign="top">
                    <p style="margin:0 0 6px;font-size:15px;font-weight:bold;color:{C_TEAL};line-height:1.4;font-family:Arial,sans-serif;">{h(art["title"])}</p>
                    <p style="margin:0;font-size:12px;font-family:Arial,sans-serif;">{pub_html}{link_html}</p>
                  </td>
                </tr>
                {summary_block}
              </table>"""

        danang_html = f"""
  <tr>
    <td bgcolor="{C_TEAL_BG}" style="background-color:{C_TEAL_BG};padding:20px 30px;border-top:3px solid {C_TEAL};">
      <p style="margin:0 0 16px;font-size:11px;color:{C_TEAL};letter-spacing:1px;font-family:Arial,sans-serif;text-transform:uppercase;font-weight:bold;">
        &#127968;&nbsp;G&#243;c &#272;&#224; N&#7861;ng h&#244;m nay
      </p>
      {danang_items}
    </td>
  </tr>"""

    # ── Viral MXH ────────────────────────────────────────────────────────────
    viral_html = ""
    if viral:
        viral_html = f"""
  <tr>
    <td bgcolor="{C_PINK_BG}" style="background-color:{C_PINK_BG};padding:20px 30px;border-top:3px solid {C_ACCENT};">
      <p style="margin:0 0 12px;font-size:11px;color:{C_ACCENT};letter-spacing:1px;font-family:Arial,sans-serif;text-transform:uppercase;font-weight:bold;">
        &#128293;&nbsp;M&#7841;ng x&#227; h&#7897;i h&#244;m nay
      </p>
      {md_to_html(viral)}
    </td>
  </tr>"""

    # ── Tip ──────────────────────────────────────────────────────────────────
    tip_html = ""
    if tip:
        if tip_type == "food":
            tip_bg, tip_color = C_AMBER_BG, "#E65100"
            tip_icon  = "&#127836;"
            tip_label = "Tip &#7848;m th&#7921;c h&#244;m nay"
        elif tip_type == "health":
            tip_bg, tip_color = C_GREEN_BG, "#2E7D32"
            tip_icon  = "&#127808;"
            tip_label = "Tip s&#7913;c kh&#7887;e h&#244;m nay"
        else:  # beauty
            tip_bg, tip_color = C_PINK_BG, "#AD1457"
            tip_icon  = "&#10024;"
            tip_label = "Tip l&#224;m &#273;&#7865;p &amp; phong c&#225;ch s&#7889;ng"
        tip_html = f"""
  <tr>
    <td bgcolor="{tip_bg}" style="background-color:{tip_bg};padding:20px 30px;border-top:3px solid {tip_color};">
      <p style="margin:0 0 12px;font-size:11px;color:{tip_color};letter-spacing:1px;font-family:Arial,sans-serif;text-transform:uppercase;font-weight:bold;">
        {tip_icon}&nbsp;{tip_label}
      </p>
      {md_to_html(tip)}
    </td>
  </tr>"""

    # ── Music + Fashion Trending ─────────────────────────────────────────────
    music_fashion_html = ""
    if music_fashion:
        music_fashion_html = f"""
  <tr>
    <td bgcolor="#EDE7F6" style="background-color:#EDE7F6;padding:20px 30px;border-top:3px solid #7B1FA2;">
      <p style="margin:0 0 12px;font-size:11px;color:#7B1FA2;letter-spacing:1px;font-family:Arial,sans-serif;text-transform:uppercase;font-weight:bold;">
        &#127925;&nbsp;&#193;m nh&#7841;c &amp; Th&#7901;i trang h&#244;m nay
      </p>
      {md_to_html(music_fashion)}
    </td>
  </tr>"""

    # ── Food of the Day ───────────────────────────────────────────────────────
    food_of_day_html = ""
    if food_of_day:
        food_of_day_html = f"""
  <tr>
    <td bgcolor="#FFF3E0" style="background-color:#FFF3E0;padding:20px 30px;border-top:3px solid #E65100;">
      <p style="margin:0 0 12px;font-size:11px;color:#E65100;letter-spacing:1px;font-family:Arial,sans-serif;text-transform:uppercase;font-weight:bold;">
        &#127869;&nbsp;M&#243;n ngon h&#244;m nay
      </p>
      {md_to_html(food_of_day)}
    </td>
  </tr>"""

    # ── Motivational Quote ────────────────────────────────────────────────────
    quote_html = ""
    if quote:
        quote_html = f"""
  <tr>
    <td bgcolor="{C_PURPLE_BG}" style="background-color:{C_PURPLE_BG};padding:20px 30px;border-top:3px solid {C_PURPLE};">
      <p style="margin:0 0 12px;font-size:11px;color:{C_PURPLE};letter-spacing:1px;font-family:Arial,sans-serif;text-transform:uppercase;font-weight:bold;">
        &#128150;&nbsp;C&#226;u ch&#226;m ng&#244;n h&#244;m nay
      </p>
      {md_to_html(quote)}
    </td>
  </tr>"""

    # ── Handsome guy ─────────────────────────────────────────────────────────
    guy_html = ""
    if guy:
        img_block = ""
        if guy.get("image_url"):
            img_block = f'<img src="{h(guy["image_url"], quote=True)}" alt="{h(guy["name"])}" width="140" style="width:140px;border-radius:10px;display:block;margin:0 auto 10px;box-shadow:0 2px 8px rgba(0,0,0,.15);" />'
        tags_html = " ".join(
            f'<span style="background:{C_PRIMARY};color:#fff;font-size:10px;padding:2px 8px;border-radius:10px;margin-right:4px;margin-bottom:4px;display:inline-block;font-family:Arial,sans-serif;">{h(t)}</span>'
            for t in guy.get("tags", [])
        )

        def _info_row(label, val):
            if not val:
                return ""
            return f'<tr><td style="font-size:11px;color:#888;padding:2px 8px 2px 0;font-family:Arial,sans-serif;white-space:nowrap;"><strong>{label}</strong></td><td style="font-size:12px;color:#444;padding:2px 0;font-family:Arial,sans-serif;">{h(val)}</td></tr>'

        info_table = (
            f'<table cellpadding="0" cellspacing="0" style="margin:8px 0;">'
            + _info_row("Ngày sinh", guy.get("birthday") or (guy.get("born") and f"Năm {guy['born']}") or "")
            + _info_row("Chiều cao", guy.get("height"))
            + _info_row("Cân nặng", guy.get("weight"))
            + _info_row("Nhóm máu", guy.get("blood_type"))
            + _info_row("Cung HĐ", guy.get("zodiac"))
            + _info_row("Màu yêu thích", guy.get("fav_color"))
            + _info_row("Con số may", guy.get("fav_number"))
            + _info_row("Tình trạng", guy.get("status"))
            + _info_row("Sở thích", guy.get("hobbies"))
            + "</table>"
        )

        works_html = ""
        if guy.get("top_works"):
            works_html = f'<p style="margin:6px 0 2px;font-size:11px;color:{C_ACCENT};font-weight:bold;font-family:Arial,sans-serif;">&#127942; Tác phẩm nổi bật:</p><p style="margin:0 0 4px;font-size:12px;color:#555;font-family:Arial,sans-serif;">{h(guy["top_works"])}</p>'
        awards_html = ""
        if guy.get("awards"):
            awards_html = f'<p style="margin:6px 0 2px;font-size:11px;color:{C_GOLD};font-weight:bold;font-family:Arial,sans-serif;">&#127881; Giải thưởng:</p><p style="margin:0 0 8px;font-size:12px;color:#555;font-family:Arial,sans-serif;">{h(guy["awards"])}</p>'

        guy_html = f"""
  <tr>
    <td bgcolor="{C_LIGHT}" style="background-color:{C_LIGHT};padding:20px 30px;border-top:3px solid {C_GOLD};">
      <p style="margin:0 0 14px;font-size:11px;color:{C_GOLD};letter-spacing:1px;font-family:Arial,sans-serif;text-transform:uppercase;font-weight:bold;">
        &#127775;&nbsp;Trai &#272;&#7865;p H&#244;m Nay
      </p>
      <table role="presentation" width="100%" cellpadding="0" cellspacing="0">
        <tr>
          <td width="150" valign="top" style="padding-right:16px;text-align:center;">
            {img_block}
            <p style="margin:4px 0 0;text-align:center;">{tags_html}</p>
          </td>
          <td valign="top">
            <p style="margin:0 0 2px;font-size:20px;font-weight:bold;color:{C_PRIMARY};font-family:Arial,sans-serif;">&#128149;&nbsp;{h(guy["name"])}</p>
            <p style="margin:0 0 4px;font-size:12px;color:#888;font-family:Arial,sans-serif;">{h(guy.get("origin",""))} &nbsp;|&nbsp; {h(guy.get("job",""))}</p>
            {info_table}
            <p style="margin:8px 0;font-size:13px;color:#333;line-height:1.7;font-family:Arial,sans-serif;">{h(guy.get("intro",""))}</p>
            {works_html}
            {awards_html}
          </td>
        </tr>
      </table>
    </td>
  </tr>"""

    return f"""<!DOCTYPE html>
<html lang="vi" xmlns:o="urn:schemas-microsoft-com:office:office" xmlns:v="urn:schemas-microsoft-com:vml">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<meta http-equiv="X-UA-Compatible" content="IE=edge">
</head>
<body style="margin:0;padding:0;background-color:{C_LIGHT};-webkit-text-size-adjust:100%;-ms-text-size-adjust:100%;">

<table role="presentation" width="100%" cellpadding="0" cellspacing="0" bgcolor="{C_LIGHT}" style="background-color:{C_LIGHT};">
<tr><td align="center" style="padding:24px 12px;">

<table role="presentation" width="600" cellpadding="0" cellspacing="0"
       style="max-width:600px;width:100%;background-color:#FFFFFF;border-radius:10px;" bgcolor="#FFFFFF">

  <!-- HEADER -->
  <tr>
    <td bgcolor="{C_PRIMARY}" style="background-color:{C_PRIMARY};padding:28px 30px 22px 30px;text-align:center;border-radius:10px 10px 0 0;">
      <p style="margin:0 0 6px;font-size:11px;color:#F8BBD9;letter-spacing:2px;font-family:Arial,sans-serif;text-transform:uppercase;">
        &#127800;&nbsp;{date_str}&nbsp;&#127800;
      </p>
      <h1 style="margin:0;font-size:24px;font-weight:bold;color:#FFFFFF;font-family:Arial,sans-serif;line-height:1.2;">
        &#128150; Th&#244;ng T&#7845;n X&#227; Heo Xinh &#272;&#7865;p
      </h1>
      <p style="margin:8px 0 0;font-size:13px;color:#F8BBD9;font-family:Arial,sans-serif;">
        B&#7843;n tin h&#224;ng ng&#224;y d&#224;nh cho chị em v&#259;n ph&#242;ng
      </p>
    </td>
  </tr>

  <!-- SECTION LABEL: TIN TỨC -->
  <tr>
    <td bgcolor="#F5F7FA" style="background-color:#F5F7FA;padding:12px 30px;">
      <p style="margin:0;font-size:11px;color:#999999;letter-spacing:1px;font-family:Arial,sans-serif;text-transform:uppercase;font-weight:bold;">
        &#127757;&nbsp;Tin t&#7913;c h&#244;m nay
      </p>
    </td>
  </tr>

  <!-- ARTICLES -->
  {articles_html}

  <!-- GÓC ĐÀ NẴNG -->
  {danang_html}

  <!-- VIRAL MXH -->
  {viral_html}

  <!-- MUSIC + FASHION -->
  {music_fashion_html}

  <!-- FOOD OF THE DAY -->
  {food_of_day_html}

  <!-- TIP -->
  {tip_html}

  <!-- QUOTE -->
  {quote_html}

  <!-- TRAI ĐẸP -->
  {guy_html}

  <!-- FOOTER -->
  <tr>
    <td bgcolor="{C_PRIMARY}" style="background-color:{C_PRIMARY};padding:20px 30px;text-align:center;border-radius:0 0 10px 10px;">
      <p style="margin:0 0 4px;font-size:13px;color:#F8BBD9;font-family:Arial,sans-serif;">
        &#127800;&nbsp;Ch&#250;c ch&#7883; em m&#7897;t ng&#224;y vui v&#7867; v&#224; n&#259;ng su&#7845;t!&nbsp;&#127800;
      </p>
      <p style="margin:6px 0 0;font-size:11px;color:#E91E8C88;font-family:Arial,sans-serif;color:#F48FB1;">
        TTXHXD &mdash; T&#7893;ng h&#7907;p b&#7903;i Groq AI &amp; ngu&#7891;n tin VN
      </p>
    </td>
  </tr>

</table>

</td></tr>
</table>
</body>
</html>"""


def build_plain_text(data):
    lines = [
        "=" * 50,
        f"THÔNG TẤN XÃ HEO XINH ĐẸP | {data['date']}",
        "=" * 50,
    ]
    lines.append("\n🌏 TIN TỨC HÔM NAY\n")
    for i, art in enumerate(data["articles"], 1):
        lines.append(f"{i}. {art['title']}")
        if art.get("publisher"):
            lines.append(f"   {art['publisher']}")
        if art.get("link"):
            lines.append(f"   {art['link']}")
        if art.get("summary"):
            lines.append(f"\n   {art['summary']}\n")
    if data.get("danang_articles"):
        lines.append("\n" + "─" * 50)
        lines.append("🏖️ GÓC ĐÀ NẴNG HÔM NAY\n")
        for i, art in enumerate(data["danang_articles"], 1):
            lines.append(f"{i}. {art['title']}")
            if art.get("publisher"):
                lines.append(f"   {art['publisher']}")
            if art.get("link"):
                lines.append(f"   {art['link']}")
            if art.get("summary"):
                lines.append(f"\n   {art['summary']}\n")
    if data.get("viral"):
        lines.append("\n" + "─" * 50)
        lines.append("🔥 MẠNG XÃ HỘI HÔM NAY")
        lines.append(data["viral"])
    if data.get("music_fashion"):
        lines.append("\n" + "─" * 50)
        lines.append("🎵 ÂM NHẠC & THỜI TRANG HÔM NAY")
        lines.append(data["music_fashion"])
    if data.get("food_of_day"):
        lines.append("\n" + "─" * 50)
        lines.append("🍽️ MÓN NGON HÔM NAY")
        lines.append(data["food_of_day"])
    if data.get("tip"):
        lines.append("\n" + "─" * 50)
        tip_type = data.get("tip_type", "food")
        label = {"food": "🍜 TIP ẨM THỰC", "health": "🍀 TIP SỨC KHỎE", "beauty": "✨ TIP LÀM ĐẸP & PHONG CÁCH"}.get(tip_type, "💡 TIP HÔM NAY")
        lines.append(label)
        lines.append(data["tip"])
    if data.get("quote"):
        lines.append("\n" + "─" * 50)
        lines.append("💬 CÂU CHÂM NGÔN HÔM NAY")
        lines.append(data["quote"])
    if data.get("guy"):
        g = data["guy"]
        lines.append("\n" + "─" * 50)
        lines.append(f"🌟 TRAI ĐẸP HÔM NAY: {g['name']}")
        lines.append(f"   {g.get('origin','')} | {g.get('job','')}")
        lines.append(f"   {g.get('intro','')}")
    lines.append("\n" + "=" * 50)
    lines.append("Chúc chị em một ngày vui vẻ! 🌸")
    return "\n".join(lines)


def send_email(subject, html, plain_text):
    if not EMAIL_PASSWORD:
        logging.error("EMAIL_PASSWORD not set")
        return False

    match = re.match(r'^(.+?)\s*<(.+?)>$', EMAIL_FROM)
    if match:
        display_name, from_addr = match.group(1).strip(), match.group(2).strip()
        from_header = formataddr((str(Header(display_name, "utf-8")), from_addr))
    else:
        from_addr = EMAIL_FROM
        from_header = EMAIL_FROM

    bcc_raw  = f"{EMAIL_TO},{EMAIL_BCC}" if EMAIL_TO else EMAIL_BCC
    bcc_list = [b.strip() for b in bcc_raw.split(",") if b.strip()]

    msg = MIMEMultipart("alternative")
    msg["Subject"] = Header(subject, "utf-8")
    msg["From"]    = from_header
    msg["To"]      = "undisclosed-recipients:;"
    msg["Bcc"]     = ", ".join(bcc_list)

    msg.attach(MIMEText(plain_text, "plain", "utf-8"))
    msg.attach(MIMEText(html, "html", "utf-8"))

    for attempt in range(1, MAX_RETRIES + 1):
        logging.info(f"Send attempt {attempt}/{MAX_RETRIES}...")
        try:
            with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=30) as server:
                server.starttls()
                server.login(from_addr, EMAIL_PASSWORD)
                server.sendmail(from_addr, bcc_list, msg.as_bytes())
            logging.info("Email sent successfully!")
            return True
        except Exception as e:
            logging.warning(f"Attempt {attempt} failed: {e}")
        if attempt < MAX_RETRIES:
            logging.info(f"Retrying in {RETRY_DELAY}s...")
            time.sleep(RETRY_DELAY)
    return False


DOCS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "docs")


def _date_slug():
    return os.environ.get("WEB_DATE_OVERRIDE") or datetime.datetime.now().strftime("%Y-%m-%d")


def _all_dated_files():
    if not os.path.isdir(DOCS_DIR):
        return []
    return sorted(
        f[:-5] for f in os.listdir(DOCS_DIR)
        if re.match(r'\d{4}-\d{2}-\d{2}\.html$', f)
    )


def build_web_html(data, date_slug=None):
    btn_style = f"background:rgba(255,255,255,.15);color:#fff;border:1px solid rgba(255,255,255,.3);padding:5px 12px;border-radius:4px;font-size:12px;cursor:pointer;font-family:Arial,sans-serif;text-decoration:none;display:inline-block;"
    pdf_slug  = date_slug or _date_slug()
    nav = f"""<div id="web-nav" style="background:{C_PRIMARY};padding:8px 16px;font-family:Arial,sans-serif;font-size:13px;position:sticky;top:0;z-index:999;border-bottom:2px solid {C_ACCENT};display:flex;align-items:center;justify-content:center;gap:10px;flex-wrap:wrap;">
  <span id="nav-prev" style="color:#F48FB1;">&#8592;</span>
  <a href="all.html" style="color:#FFD700;text-decoration:none;font-weight:bold;">&#128240; T&#7845;t c&#7843; b&#7843;n tin</a>
  <span style="color:#FFFFFF;">{h(data['date'])}</span>
  <span id="nav-next" style="color:#F48FB1;">&#8594;</span>
  <a href="{pdf_slug}.pdf" download="{pdf_slug}.pdf" style="{btn_style}">&#128196; T&#7843;i PDF</a>
  <button onclick="sharePage()" style="{btn_style}">&#128279; Chia s&#7867;</button>
</div>
<script>
function sharePage(){{
  var title='TTXHXD – {h(data["date"])}';
  if(navigator.share){{navigator.share({{title:title,url:location.href}});}}
  else{{navigator.clipboard.writeText(location.href).then(function(){{alert('Đã sao chép link!');}}); }}
}}
(function(){{
  var m=location.pathname.match(/(\d{{4}}-\d{{2}}-\d{{2}})\.html/);
  if(!m)return;
  var slug=m[1];
  function fmt(s){{var p=s.split('-');return p[2]+'/'+p[1];}}
  var lnkStyle='color:#F8BBD9;text-decoration:none;';
  fetch('dates.json?_='+Date.now())
    .then(function(r){{return r.json();}})
    .then(function(dates){{
      var idx=dates.indexOf(slug);
      if(idx>0){{var p=dates[idx-1];document.getElementById('nav-prev').innerHTML='<a href="'+p+'.html" style="'+lnkStyle+'">&#8592; '+fmt(p)+'</a>';}}
      if(idx>=0&&idx<dates.length-1){{var n=dates[idx+1];document.getElementById('nav-next').innerHTML='<a href="'+n+'.html" style="'+lnkStyle+'">'+fmt(n)+' &#8594;</a>';}}
    }}).catch(function(){{}});
}})();
</script>
"""
    print_css = """<style>
@media screen and (max-width:620px) {
  table[width="600"] { width:100% !important; }
  td { word-break:break-word; overflow-wrap:break-word; }
  td[style*="padding:28px 30px"], td[style*="padding:20px 30px"], td[style*="padding:16px 30px"], td[style*="padding:12px 30px"] { padding-left:14px !important; padding-right:14px !important; }
}
@media print { #web-nav { display:none !important; } body { background:#fff !important; } }
</style>
"""
    email_html = build_html(data)
    email_html = _re.sub(r'(</head>)', print_css + r'\1', email_html, count=1)
    return _re.sub(r'(<body[^>]*>)', lambda m: m.group(0) + '\n' + nav, email_html, count=1)


def update_web_index(all_dates):
    import json as _json
    os.makedirs(DOCS_DIR, exist_ok=True)
    latest = all_dates[-1] if all_dates else ""

    with open(os.path.join(DOCS_DIR, "dates.json"), "w", encoding="utf-8") as f:
        _json.dump(all_dates, f)

    index_html = f"""<!DOCTYPE html>
<html lang="vi">
<head><meta charset="UTF-8"><meta http-equiv="refresh" content="0; url={latest}.html">
<title>TTXHXD - Bản tin hàng ngày</title></head>
<body><p><a href="{latest}.html">Chuyển hướng...</a></p></body>
</html>"""
    with open(os.path.join(DOCS_DIR, "index.html"), "w", encoding="utf-8") as f:
        f.write(index_html)

    rows = ""
    for d in reversed(all_dates):
        dt = datetime.datetime.strptime(d, "%Y-%m-%d")
        label = dt.strftime("%d/%m/%Y")
        weekday = ["Thứ Hai","Thứ Ba","Thứ Tư","Thứ Năm","Thứ Sáu","Thứ Bảy","Chủ Nhật"][dt.weekday()]
        rows += f'<tr><td style="padding:12px 20px;border-bottom:1px solid #FCE4EC;"><a href="{d}.html" style="color:{C_PRIMARY};text-decoration:none;font-size:15px;font-weight:bold;">{label}</a><span style="color:#999;font-size:13px;margin-left:10px;">{weekday}</span></td></tr>\n'

    latest_dt = datetime.datetime.strptime(latest, "%Y-%m-%d") if latest else None
    latest_label = latest_dt.strftime("%d/%m/%Y") if latest_dt else ""

    all_html = f"""<!DOCTYPE html>
<html lang="vi">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>Tất cả bản tin - TTXHXD</title></head>
<body style="margin:0;padding:0;background:{C_LIGHT};font-family:Arial,sans-serif;">
<div style="max-width:600px;margin:40px auto;background:#fff;border-radius:10px;overflow:hidden;box-shadow:0 2px 12px rgba(0,0,0,.1);">
  <div style="background:{C_PRIMARY};padding:24px 30px;text-align:center;">
    <h1 style="margin:0;color:#fff;font-size:22px;">&#128150; TTXHXD — Bản tin hàng ngày</h1>
    <p style="margin:8px 0 0;color:#F8BBD9;font-size:13px;">Thông Tấn Xã Heo Xinh Đẹp</p>
  </div>
  {f'<div style="padding:14px 20px;text-align:center;background:{C_PINK_BG};border-bottom:2px solid {C_ACCENT};"><a href="{latest}.html" style="display:inline-block;background:{C_PRIMARY};color:#fff;padding:9px 22px;border-radius:6px;text-decoration:none;font-size:14px;font-weight:bold;">&#128240; Bản tin mới nhất &mdash; {latest_label}</a></div>' if latest else ''}
  <div style="padding:10px 20px 4px;background:#F5F7FA;">
    <p style="margin:0;font-size:11px;color:#999;letter-spacing:1px;text-transform:uppercase;font-weight:bold;">Tất cả bản tin ({len(all_dates)})</p>
  </div>
  <table width="100%" cellpadding="0" cellspacing="0">{rows}</table>
  <div style="padding:14px 20px;text-align:center;background:#F5F7FA;">
    <p style="margin:0;font-size:12px;color:#999;">Cập nhật mỗi ngày lúc 07:30 GMT+7 &#127800;</p>
  </div>
</div>
</body>
</html>"""
    with open(os.path.join(DOCS_DIR, "all.html"), "w", encoding="utf-8") as f:
        f.write(all_html)


def _generate_pdf(data, pdf_path):
    import platform, subprocess, tempfile
    pdf_html = build_html(data)
    with tempfile.NamedTemporaryFile(suffix=".html", delete=False, mode="w", encoding="utf-8") as f:
        f.write(pdf_html)
        tmp_html = f.name
    try:
        if platform.system() == "Darwin":
            chrome = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
            result = subprocess.run(
                [chrome, "--headless=new", "--disable-gpu", "--no-sandbox",
                 f"--print-to-pdf={pdf_path}", f"file://{tmp_html}"],
                capture_output=True, timeout=30
            )
            if result.returncode == 0:
                logging.info(f"PDF saved (Chrome): {os.path.basename(pdf_path)}")
            else:
                logging.warning(f"Chrome PDF failed: {result.stderr.decode()[:200]}")
        else:
            from weasyprint import HTML as WeasyprintHTML
            WeasyprintHTML(filename=tmp_html).write_pdf(pdf_path)
            logging.info(f"PDF saved (WeasyPrint): {os.path.basename(pdf_path)}")
    except ImportError:
        logging.info("weasyprint not installed — skipping PDF")
    except Exception as e:
        logging.warning(f"PDF generation failed: {e}")
    finally:
        os.unlink(tmp_html)


def save_web_pages(data):
    os.makedirs(DOCS_DIR, exist_ok=True)
    today    = _date_slug()
    existing = _all_dated_files()
    all_dates = sorted(set(existing + [today]))

    web_html = build_web_html(data, date_slug=today)
    with open(os.path.join(DOCS_DIR, f"{today}.html"), "w", encoding="utf-8") as f:
        f.write(web_html)

    _generate_pdf(data, os.path.join(DOCS_DIR, f"{today}.pdf"))

    nojekyll = os.path.join(DOCS_DIR, ".nojekyll")
    if not os.path.exists(nojekyll):
        open(nojekyll, "w").close()

    update_web_index(all_dates)
    logging.info(f"Web pages saved: docs/{today}.html")


def main():
    logging.info("=== TTXHXD Bot started ===")

    logging.info("Fetching content...")
    data = fetch_content()
    if not data or not data.get("articles"):
        logging.error("Failed to fetch content. Aborting.")
        sys.exit(1)
    logging.info(f"Fetched {len(data['articles'])} articles")

    html       = build_html(data)
    plain_text = build_plain_text(data)
    subject    = f"TTXHXD 🌸 Bản tin ngày {data['date']}"

    if os.environ.get("NO_EMAIL"):
        logging.info("NO_EMAIL set — skipping email send")
    elif not EMAIL_PASSWORD:
        logging.info("No EMAIL_PASSWORD — skipping email send")
    elif send_email(subject, html, plain_text):
        logging.info("Email sent successfully")
    else:
        logging.error(f"Email failed after {MAX_RETRIES} attempts.")
        sys.exit(1)

    save_web_pages(data)
    logging.info("=== Bot finished successfully ===")


if __name__ == "__main__":
    main()
