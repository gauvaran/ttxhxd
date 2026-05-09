# TTXHXD — Thông Tấn Xã Heo Xinh Đẹp

Bản tin hàng ngày gửi email + lưu trữ web. Đây là project mới, clone ý tưởng kỹ thuật
từ project `gauvaran/ainews` (AI News Bot) nhưng hoàn toàn khác về nội dung.

---

## 🎯 Đối tượng độc giả

**Nữ nhân viên văn phòng** — Hành chính, Văn phòng đại diện VietinBank tại Đà Nẵng.

Sở thích: âm nhạc, thời trang, du lịch, ẩm thực, văn hóa, lịch sử, tin tức kinh tế-tài chính-ngân hàng, mạng xã hội. Thích cái đẹp, thích trai trẻ đẹp. Bận rộn, cần thông tin nhanh gọn nhưng thú vị.

---

## ✍️ Tone giọng văn

**Dí dỏm, hài hước, thông minh** — như người bạn thân kể chuyện, không khô khan, không học thuật.
- Dùng emoji tự nhiên, trẻ trung, vui tươi (không lạm dụng)
- Câu văn linh hoạt: có thể dài khi cần chiều sâu, ngắn khi cần punch
- Chêm tiếng lóng, tiếng Anh quen thuộc tự nhiên (vibe, crush, slay, v.v.)
- Tuyệt đối **không cứng nhắc, không báo cáo, không văn phòng**

---

## 📰 Các chuyên mục

### 1. 🌏 Tin tức hôm nay
Kinh tế, chính trị, văn hóa, tài chính ngân hàng — Thế giới, Việt Nam, Đà Nẵng.
- 5–7 tin, mỗi tin có **tóm tắt 3–5 câu** đủ để hiểu mà không cần đọc bài gốc
- Ưu tiên tin có ảnh hưởng đến đời sống, kinh tế, ngân hàng
- Đà Nẵng luôn có ít nhất 1 tin

### 2. 🔥 Mạng xã hội hôm nay
Xu hướng viral, câu nói hot, joke/meme đang lan truyền trên Facebook, TikTok, Threads.
- **Tổng hợp thật** — bắt kịp trend thực tế, không bịa đặt
- 3–4 item, mỗi item ngắn gọn, có dẫn chứng câu nói/hashtag cụ thể
- Ví dụ: câu cửa miệng đang hot ("thôi kệ", "chúc mừng sinh nhật tôi"...), tin hot trên Threads, clip triệu view TikTok
- Groq generate dựa trên date seed + kiến thức văn hóa VN — cần prompt bắt kịp xu hướng

### 3. 🍜 Tip hôm nay
Luân phiên theo ngày lẻ/chẵn:
- **Ngày lẻ**: Tip ẩm thực — công thức nhanh, mẹo nấu ăn, món ngon Đà Nẵng / VN
- **Ngày chẵn**: Tip sức khỏe — thói quen tốt, dinh dưỡng, làm đẹp đơn giản
- Mỗi tip ~100–150 từ, thực tế, áp dụng được ngay, có emoji sinh động

### 4. 🌟 Trai Đẹp Hôm Nay
1 nhân vật nam mỗi ngày. Có ảnh + giới thiệu hấp dẫn ~100 từ.

**Profile trai đẹp ưu tiên:**
- Nghệ sĩ châu Á: Việt Nam, Hàn Quốc, Nhật Bản, Trung Quốc, Hồng Kông, Đài Loan
- Ngoại hình: cao ráo, thư sinh, trắng trẻo, trẻ (không cần cơ bắp)
- Nghề nghiệp: ca sĩ, diễn viên, idol K-pop/C-pop/V-pop, streamer nổi tiếng
- Tránh: chính trị gia, vận động viên cơ bắp, người lớn tuổi

**Ví dụ**: Sơn Tùng M-TP, Đen Vâu, Trấn Thành (trẻ), BTS (Jungkook, V, Jimin), EXO (Lay, Baekhyun), Tiêu Chiến (肖战), Vương Nhất Bác (王一博), Lâm Nhất (Lin Yi), Vương Hạc Đệ...

---

## Mục tiêu

Gửi email hàng ngày (và lưu lên GitHub Pages) với các chuyên mục trên.
Nội dung **hoàn toàn tiếng Việt**. Không cần dịch (khác ainews dịch từ EN→VI).

---

## Tái sử dụng từ ainews

Clone code gốc từ GitHub:
```bash
git clone https://github.com/gauvaran/ainews.git
```

**Giữ nguyên (không cần sửa nhiều):**
- `files/ai_news_bot.py` — phần build HTML email + web page + PDF + send email
- `files/quotes.py` — có thể tái sử dụng cấu trúc cho danh sách trai đẹp
- `.github/workflows/daily_news.yml` — chỉ đổi tên và schedule nếu cần
- Toàn bộ logic GitHub Actions + GitHub Pages deploy

**Cần viết lại:**
- `files/fetch_news.py` → `files/fetch_content.py` — fetch tin tức VN, tổng hợp nội dung
- `files/handsome_guys.py` — danh sách 365 nhân vật nam, mỗi ngày 1 người (như quotes.py)
- Prompt Groq: viết tiếng Việt từ đầu, không dịch

---

## Kiến trúc kỹ thuật (giống ainews)

```
GitHub Actions (cron 07:30 GMT+7)
    └── python files/bot.py
            ├── fetch_content.py  ← fetch RSS feeds VN + Groq generate
            ├── handsome_guys.py  ← danh sách curated
            └── ai_news_bot.py    ← build HTML + send email + save docs/

docs/                             ← GitHub Pages (HTML + PDF)
    ├── index.html                ← redirect to latest
    ├── all.html                  ← archive list
    ├── dates.json                ← JS nav
    └── YYYY-MM-DD.html/.pdf
```

**Stack:**
- Python 3.11 (no external deps ngoài feedparser + weasyprint)
- Groq API: `llama-3.3-70b-versatile` cho tất cả content (free tier)
- Gemini 2.5 Flash (optional, nếu cần dịch): free 20 req/day
- Gmail SMTP (App Password)
- GitHub Actions + GitHub Pages

---

## Nguồn tin RSS tiếng Việt

```python
# Tin tổng hợp VN
"https://vnexpress.net/rss/tin-muc-moi-nhat.rss"          # VnExpress mới nhất
"https://tuoitre.vn/rss/tin-moi-nhat.rss"                 # Tuổi Trẻ
"https://thanhnien.vn/rss/home.rss"                        # Thanh Niên
"https://dantri.com.vn/rss/home.rss"                       # Dân Trí

# Tài chính ngân hàng
"https://cafef.vn/rss/home.rss"                            # CafeF
"https://tinnhanhchungkhoan.vn/rss/home.rss"               # Tin nhanh chứng khoán
"https://vneconomy.vn/rss/home.rss"                        # VnEconomy

# Thế giới
"https://www.bbc.com/vietnamese/index.xml"                 # BBC Tiếng Việt
"https://feeds.bbci.co.uk/vietnamese/rss.xml"

# Đà Nẵng
"https://baodanang.vn/rss/home.rss"                        # Báo Đà Nẵng
"https://danangfantasticity.com/feed/"                     # Du lịch Đà Nẵng (nếu có)

# Sức khỏe
"https://suckhoedoisong.vn/rss/home.rss"                   # Sức khỏe & Đời sống
"https://vnexpress.net/rss/suc-khoe.rss"                   # VnExpress Sức khỏe

# Ẩm thực
"https://vnexpress.net/rss/am-thuc.rss"                    # VnExpress Ẩm thực
```

> **Lưu ý**: Cần verify từng feed URL trước khi dùng — RSS VN đôi khi thay đổi.

---

## Chuyên mục Mạng xã hội / Viral

Không có RSS ổn định cho trend MXH → dùng Groq 70B generate dựa trên date + kiến thức văn hóa VN:

```python
def _groq_viral_content(api_key, date_str):
    prompt = f"""Hôm nay là {date_str}. Bạn là người nghiện MXH, theo dõi sát Facebook, TikTok, Threads VN.

Viết ĐÚNG 3 trend/nội dung viral đang hot trên MXH Việt Nam gần đây, theo format:

### 🔥 [Tên trend / câu nói / sự kiện hot]
[2-3 câu: tại sao nó hot, ví dụ câu nói cụ thể hoặc tình huống, phản ứng cộng đồng]

Yêu cầu:
- Bắt kịp văn hóa internet VN thực tế (không bịa hoàn toàn)
- Có thể là: câu cửa miệng đang viral, meme, sự kiện gây tranh cãi, clip triệu view, hashtag hot
- Hài hước tự nhiên, không gượng gạo
- Tiếng Việt sinh động, có thể chêm tiếng lóng"""
```

---

## Chuyên mục Trai Đẹp Hôm Nay

Tạo file `files/handsome_guys.py` tương tự `files/quotes.py`.
Cấu trúc mỗi entry:

```python
GUYS = [
    {
        "name": "Vương Nhất Bác",           # tên phổ biến ở VN
        "origin": "Trung Quốc 🇨🇳",
        "job": "Ca sĩ, diễn viên, vũ công",
        "intro": "Sinh năm 1997, thành viên nhóm UNIQ, nổi tiếng với phim 'Trần Tình Lệnh'. Cao 1m82, vibe lạnh lùng ngầu mà lại cực kỳ tài năng — cưỡi moto, diễn xuất, nhảy đều đỉnh.",
        "why_today": "Vì hôm nay cần một liều vitamin đẹp trai để vượt qua deadline 😌",
        "image_url": "https://upload.wikimedia.org/...",  # Wikimedia Commons
        "tags": ["idol", "diễn viên", "C-pop"],
    },
    # Mục tiêu: 60–100 nhân vật, xoay vòng theo day_of_year % len(GUYS)
]
```

**Danh sách ưu tiên** (châu Á, thư sinh, trắng, trẻ):
- 🇻🇳 VN: Sơn Tùng M-TP, Đen Vâu, Isaac, Erik, Anh Tú Atus, Negav, tlinh (nam), Jack
- 🇰🇷 Hàn: BTS (V, Jungkook, Jimin), EXO (Baekhyun, Lay), Stray Kids (Felix), ENHYPEN, TXT
- 🇨🇳🇭🇰🇹🇼 C-pop: Vương Nhất Bác, Tiêu Chiến, Lâm Nhất (Lin Yi), Vương Hạc Đệ, Cung Tuấn
- 🇯🇵 Nhật: thành viên các nhóm idol Nhật nổi tiếng tại VN

> ⚠️ Ảnh: dùng Wikimedia Commons (free license) hoặc ảnh từ trang fan chính thức.
> Format `image_url` để trống nếu chưa có — bot vẫn hiển thị được phần text.

---

## GitHub Secrets cần set

| Secret | Giá trị |
|--------|---------|
| `EMAIL_FROM` | `Tên hiển thị <email@gmail.com>` |
| `EMAIL_TO` | (để trống) |
| `EMAIL_BCC` | Danh sách email nhận |
| `EMAIL_PASSWORD` | Gmail App Password |
| `GROQ_API_KEY` | Key từ console.groq.com |
| `GEMINI_API_KEY` | Key từ aistudio.google.com (optional) |

---

## Setup từ đầu (step by step)

```bash
# 1. Tạo GitHub repo mới (public, để dùng GitHub Pages)
gh repo create gauvaran/ttxhxd --public

# 2. Clone ainews làm base
git clone https://github.com/gauvaran/ainews.git ttxhxd-code
cd ttxhxd-code

# 3. Đổi remote sang repo mới
git remote set-url origin https://github.com/gauvaran/ttxhxd.git

# 4. Xóa docs/ cũ (bắt đầu sạch)
rm -rf docs/ && mkdir docs

# 5. Viết lại files/fetch_content.py, files/handsome_guys.py
# 6. Sửa files/ai_news_bot.py: đổi subject, tên newsletter, màu sắc
# 7. Set GitHub Secrets
# 8. Enable GitHub Pages (Settings → Pages → Deploy from /docs)
# 9. Push và trigger workflow lần đầu
git push -u origin master
gh workflow run daily_news.yml --repo gauvaran/ttxhxd
```

---

## Điểm khác biệt quan trọng so với ainews

| | ainews | ttxhxd |
|---|---|---|
| Ngôn ngữ nguồn | Tiếng Anh | Tiếng Việt |
| Cần dịch? | Có (EN→VI) | **Không** |
| Tóm tắt | Groq 8B extract EN → 70B dịch VI | Groq 70B tóm tắt thẳng VI |
| Lesson/Tips | AI dev tips | Tip món ăn + sức khỏe (luân phiên) |
| Section đặc biệt | Quote hàng ngày | Trai đẹp hôm nay |
| Viral content | Không có | Mạng xã hội / joke trending |

---

## File .env cần tạo (local, gitignore)

```
EMAIL_PASSWORD=...
EMAIL_FROM=TTXHXD <email@gmail.com>
EMAIL_TO=
EMAIL_BCC=email1@...,email2@...
GROQ_API_KEY=gsk_...
GEMINI_API_KEY=AIza...   # optional
```

---

## Context người dùng & project

- **Dev**: người dùng là dev Việt Nam, quen làm việc với Claude Code CLI
- **Ainews**: project gốc tại `gauvaran/ainews` đang chạy ổn định — đọc code trên GitHub để hiểu kiến trúc
- **Groq API key**: đã có, lấy từ `.env` của ainews hoặc GitHub Secrets của ainews
- **Gmail App Password**: đã có, dùng chung `bismtaiteam@gmail.com` hoặc tạo sender mới
- **Gemini key**: `AIzaSyCYHHSPjPqQk4xiZYH0wTEjigTfChXI4u4` (free 20 req/day — chỉ dùng production, không backfill)
- **Thư mục làm việc**: `/Users/tuantt/projects/ttxhxd/`

### Việc cần làm ngay khi bắt đầu session mới:
1. `git clone https://github.com/gauvaran/ainews.git` để đọc code tham khảo
2. Tạo GitHub repo mới: `gh repo create gauvaran/ttxhxd --public`
3. Viết `files/fetch_content.py` — fetch RSS VN + Groq generate viral/tip
4. Viết `files/handsome_guys.py` — danh sách 60+ nhân vật (bắt đầu ít, tăng dần)
5. Fork/adapt `files/ai_news_bot.py` — đổi màu, subject, layout cho phù hợp nữ độc giả
6. Test local: `NO_EMAIL=1 python3 files/bot.py`
7. Set GitHub Secrets và deploy
