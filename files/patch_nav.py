#!/usr/bin/env python3
"""
patch_nav.py — Inject updated prev/next nav into all existing docs/*.html files.
Usage: python files/patch_nav.py
"""
import os, re, sys

FILES_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR  = os.path.dirname(FILES_DIR)
DOCS_DIR  = os.path.join(ROOT_DIR, "docs")

C_PRIMARY = "#8B6508"
C_ACCENT  = "#C9950C"

BTN_STYLE = "background:rgba(255,255,255,.15);color:#fff;border:1px solid rgba(255,255,255,.3);padding:5px 12px;border-radius:4px;font-size:12px;cursor:pointer;font-family:Arial,sans-serif;text-decoration:none;display:inline-block;"


def _nav_block(display_date, pdf_slug):
    return (
        f'<div id="web-nav" style="background:{C_PRIMARY};padding:8px 16px;font-family:Arial,sans-serif;font-size:13px;position:sticky;top:0;z-index:999;border-bottom:2px solid {C_ACCENT};display:flex;align-items:center;justify-content:center;gap:10px;flex-wrap:wrap;">\n'
        f'  <a id="nav-prev" href="#" style="color:#FFE082;text-decoration:none;visibility:hidden;">&#8592; --/--</a>\n'
        f'  <a href="all.html" style="color:#FFD700;text-decoration:none;font-weight:bold;">&#128240; T&#7845;t c&#7843; b&#7843;n tin</a>\n'
        f'  <span style="color:#FFFFFF;font-weight:bold;">{display_date}</span>\n'
        f'  <a id="nav-next" href="#" style="color:#FFE082;text-decoration:none;visibility:hidden;">--/-- &#8594;</a>\n'
        f'  <a href="{pdf_slug}.pdf" download="{pdf_slug}.pdf" style="{BTN_STYLE}">&#128196; T&#7843;i PDF</a>\n'
        f'  <button onclick="sharePage()" style="{BTN_STYLE}">&#128279; Chia s&#7867;</button>\n'
        f'</div>\n'
        f'<script>\n'
        f'function sharePage(){{\n'
        f"  var title='TTXHXD – {display_date}';\n"
        f'  if(navigator.share){{navigator.share({{title:title,url:location.href}});}}\n'
        f"  else{{navigator.clipboard.writeText(location.href).then(function(){{alert('\\u0110\\u00e3 sao ch\\u00e9p link!');}}); }}\n"
        f'}}\n'
        f'(function(){{\n'
        f"  var m=location.pathname.match(/(\\d{{4}}-\\d{{2}}-\\d{{2}})\\.html/);\n"
        f'  if(!m)return;\n'
        f'  var slug=m[1];\n'
        f"  function fmt(s){{var p=s.split('-');return p[2]+'/'+p[1];}}\n"
        f"  fetch('dates.json?_='+Date.now())\n"
        f'    .then(function(r){{return r.json();}}\n'
        f'    ).then(function(dates){{\n'
        f'      var idx=dates.indexOf(slug);\n'
        f"      var prevEl=document.getElementById('nav-prev');\n"
        f"      var nextEl=document.getElementById('nav-next');\n"
        f'      if(idx>0){{\n'
        f'        var pd=dates[idx-1];\n'
        f"        prevEl.href=pd+'.html';\n"
        f"        prevEl.innerHTML='&#8592; '+fmt(pd);\n"
        f"        prevEl.style.visibility='visible';\n"
        f'      }}\n'
        f'      if(idx>=0&&idx<dates.length-1){{\n'
        f'        var nd=dates[idx+1];\n'
        f"        nextEl.href=nd+'.html';\n"
        f"        nextEl.innerHTML=fmt(nd)+' &#8594;';\n"
        f"        nextEl.style.visibility='visible';\n"
        f'      }}\n'
        f'    }}).catch(function(){{}});\n'
        f'  document.addEventListener(\'keydown\',function(e){{\n'
        f"    if(e.key==='ArrowLeft'){{var p=document.getElementById('nav-prev');if(p&&p.style.visibility==='visible')location.href=p.href;}}\n"
        f"    if(e.key==='ArrowRight'){{var n=document.getElementById('nav-next');if(n&&n.style.visibility==='visible')location.href=n.href;}}\n"
        f'  }});\n'
        f'}})();\n'
        f'</script>'
    )


# Regex: match existing web-nav block (div + script), OR bare <body> with no nav
NAV_PATTERN = re.compile(
    r'<div id="web-nav".*?</script>',
    re.DOTALL
)

patched = skipped = 0
html_files = sorted(
    f for f in os.listdir(DOCS_DIR)
    if re.match(r'\d{4}-\d{2}-\d{2}\.html$', f)
)

for fname in html_files:
    slug = fname[:-5]  # YYYY-MM-DD
    parts = slug.split('-')
    display_date = f"{parts[2]}/{parts[1]}/{parts[0]}"  # DD/MM/YYYY
    path = os.path.join(DOCS_DIR, fname)

    with open(path, encoding='utf-8') as f:
        content = f.read()

    new_nav = _nav_block(display_date, slug)

    if NAV_PATTERN.search(content):
        new_content = NAV_PATTERN.sub(lambda _: new_nav, content, count=1)
    else:
        # Inject nav right after <body...>
        new_content = re.sub(r'(<body[^>]*>)', lambda m: m.group(0) + '\n' + new_nav, content, count=1)

    if new_content == content:
        print(f"[skip] {slug} — no change")
        skipped += 1
    else:
        with open(path, 'w', encoding='utf-8') as f:
            f.write(new_content)
        print(f"[ok]   {slug}")
        patched += 1

print(f"\nDone: {patched} patched, {skipped} skipped.")
