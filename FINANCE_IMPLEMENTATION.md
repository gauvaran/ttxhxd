# 💰 Bản Tin Tài Chính — Kế Hoạch Triển Khai

Dựa trên `financial_news_sources.md` và kết quả kiểm thử thực tế ngày 12/05/2026.

---

## 1. Kiểm Thử Nguồn Dữ Liệu

| Nguồn | Loại dữ liệu | Trạng thái | Ghi chú |
|---|---|---|---|
| `vang.today/api/prices` | Vàng SJC, Doji, PNJ | ✅ **Dùng được** | JSON miễn phí, không cần key |
| `portal.vietcombank.com.vn/...pXML.aspx` | Tỷ giá ngoại tệ | ✅ **Dùng được** | XML công khai, 20+ đồng tiền |
| `api.coingecko.com` | BTC, ETH, USDT/VNĐ | ✅ **Dùng được** | JSON miễn phí, không cần key |
| `api.binance.com` | Giá BTC spot | ✅ **Dùng được** | Public endpoint, không cần key |
| `giavang.org` | Bạc Phú Quý | ✅ **Giữ nguyên** | Scraping HTML đã implement |
| `vapi.vnappmob.com` (gold) | Vàng Doji/SJC | ❌ Cần API key | 403 Forbidden |
| `vapi.vnappmob.com` (FX) | Tỷ giá ngân hàng | ❌ Endpoint 404 | Đã bị gỡ |
| `vietinbank.vn/web/home/vn/ty-gia` | Tỷ giá VietinBank | ❌ JS-rendered | 0 bytes trả về |
| `developer.vietinbank.vn` (sandbox) | VietinBank Open API | ❌ Cần OAuth token | Production cần đăng ký |
| `phuquy.com.vn/gia-bac/` | Bạc Phú Quý | ❌ 404 Not Found | URL đã đổi |
| `anmint.vn/gia-bac-hom-nay` | Bạc Ancarat | ❌ 404 Not Found | URL đã đổi |
| `topi.vn/gia-bac-hom-nay.html` | Bạc tổng hợp | ❌ JS-rendered | 5KB, không có giá |
| `petrolimex.com.vn` | Giá xăng dầu | ❌ JS-rendered | Cần Playwright |
| `xangdau.net` | Giá xăng dầu | ❌ Trả về 178 bytes | Không hoạt động |

---

## 2. Nguồn Sẽ Dùng Sau Khi Cập Nhật

### 2.1 Tỷ giá (giữ nguyên Vietcombank)
```
GET https://portal.vietcombank.com.vn/Usercontrols/TVPortal.TyGia/pXML.aspx?b=10
```
- XML, không cần auth
- Ghi chú: VietinBank không có public API/endpoint nào hoạt động.
  Tỷ giá Vietcombank ≈ VietinBank (cùng track tỷ giá trung tâm NHNN, chênh lệch < 0.1%)
- Currencies: USD 🇺🇸 EUR 🇪🇺 JPY 🇯🇵 CNY 🇨🇳 GBP 🇬🇧 AUD 🇦🇺 SGD 🇸🇬 KRW 🇰🇷

### 2.2 Giá vàng (MỚI → vang.today)
```
GET https://www.vang.today/api/prices
```
- JSON, miễn phí, không cần auth
- Keys sử dụng:
  - `SJL1L10` → SJC 9999 1 lượng/10 lượng (buy/sell in VNĐ)
  - `SJ9999`  → SJC nhẫn tròn 9999
  - `DOJINHTV` → DOJI nhẫn tròn (Jewelry)
  - `PQHN24NTT` → PNJ nhẫn tròn 24K
  - `XAUUSD` → Giá vàng thế giới (USD/oz)
- Prices in VNĐ full (divide by 1,000,000 → "X triệu đ/lượng")
- Has `change_buy`/`change_sell` for delta display (+/-)

### 2.3 Giá bạc (giữ nguyên giavang.org)
- Scrape `https://giavang.org/trong-nuoc/phu-quy/`
- Key: `Đồng bạc mỹ nghệ 99.9` row → buy/sell per chỉ

### 2.4 Crypto (MỚI)
```
GET https://api.coingecko.com/api/v3/simple/price?ids=bitcoin,ethereum,tether&vs_currencies=usd,vnd
```
- JSON, miễn phí, no key needed (rate-limited but fine for 1 call/day)
- Response: `{"bitcoin":{"usd":81170,"vnd":2137164588},...}`
- Display:
  - BTC: 81,170 USD
  - ETH: 2,311 USD
  - USDT/VNĐ: 26,321 đ (chỉ số tỷ giá phi chính thức)

---

## 3. Tính Năng Mới (Theo file financial_news_sources.md)

| Tính năng | Nguồn | Khả thi? | Triển khai |
|---|---|---|---|
| Tỷ giá VietinBank | VietinBank Direct | ❌ | Dùng Vietcombank thay thế |
| Vàng SJC + Doji | vang.today JSON | ✅ | **Implement** |
| Bạc Phú Quý | giavang.org (hiện tại) | ✅ | Giữ nguyên |
| Bạc Ancarat | anmint.vn | ❌ 404 | Bỏ qua |
| Crypto BTC/ETH | CoinGecko | ✅ | **Implement** |
| VN-Index | Chưa có source hoạt động | ❌ | Bỏ qua lần này |
| Giá xăng | Petrolimex (JS) | ❌ | Bỏ qua lần này |
| Lịch sự kiện | Groq generate | 🔶 | Bỏ qua (dễ hallucinate) |

---

## 4. Thay Đổi Code

### 4.1 `files/fetch_content.py`

#### Thêm `_fetch_vangtodaygold()`
```python
def _fetch_vangtodaygold():
    """Fetch gold prices from vang.today free JSON API."""
    url = "https://www.vang.today/api/prices"
    KEYS = {
        "SJL1L10":   "🥇 SJC 1 lượng (9999)",
        "SJ9999":    "💍 SJC nhẫn tròn 9999",
        "DOJINHTV":  "💛 DOJI nhẫn tròn",
        "PQHN24NTT": "✨ PNJ nhẫn tròn 24K",
        "XAUUSD":    "🌍 Vàng thế giới",
    }
    # ...returns list of {label, buy_str, sell_str, change_str, currency}
```

#### Thêm `_fetch_crypto()`
```python
def _fetch_crypto():
    """Fetch BTC, ETH, USDT prices from CoinGecko (free, no auth)."""
    url = "https://api.coingecko.com/api/v3/simple/price?ids=bitcoin,ethereum,tether&vs_currencies=usd,vnd"
    # ...returns {btc_usd, btc_vnd, eth_usd, usdt_vnd}
```

#### Cập nhật `_fetch_finance_data()`
- Gọi `_fetch_vangtodaygold()` thay vì `_scrape_giavang('sjc')` / `_scrape_giavang('doji')`
- Gọi `_fetch_crypto()` → thêm vào dict return
- Giữ `_scrape_giavang('phu-quy')` cho bạc

### 4.2 `files/ai_news_bot.py`

#### Thêm row crypto vào finance HTML block
```html
<!-- Crypto section -->
<p>₿ BTC: 81,170 USD | 2,137 triệu đ</p>
<p>Ξ ETH: 2,311 USD</p>
<p>💵 USDT/VNĐ: 26,321 đ (tỷ giá phi chính thức)</p>
```

---

## 5. Format Hiển Thị Giá Vàng

vang.today trả về giá full VNĐ (164,000,000). Convert để hiển thị:
```python
# 164000000 → "164.00 triệu"
def _fmt_gold(val_vnd):
    return f"{val_vnd / 1_000_000:.2f} triệu"

# Delta: +1800000 → "+1.80 triệu ↑" / "-500000 → "-0.50 triệu ↓"
def _fmt_delta(delta):
    arrow = "↑" if delta > 0 else "↓" if delta < 0 else "→"
    return f"{abs(delta)/1_000_000:+.2f} triệu {arrow}"
```

---

## 6. Thứ Tự Hiển Thị Trong Bản Tin Tài Chính

```
💰 BẢN TIN TÀI CHÍNH HÔM NAY
├── 💱 Tỷ giá hôm nay (Vietcombank)
│   USD | EUR | JPY | CNY | GBP | AUD | SGD | KRW
├── 🥇 Giá vàng trong nước (vang.today)
│   SJC 1 lượng | SJC nhẫn | DOJI nhẫn | PNJ nhẫn
│   + Vàng thế giới XAU/USD
├── 🥈 Giá bạc (Phú Quý - giavang.org)
│   Đồng bạc mỹ nghệ 99.9
└── ₿ Crypto hôm nay (CoinGecko)
    BTC/USD | ETH/USD | USDT/VNĐ
```
