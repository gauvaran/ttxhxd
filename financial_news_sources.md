# 📊 Báo Cáo Nghiên Cứu Nguồn Dữ Liệu Bản Tin Tài Chính

## 1. Tỷ giá Ngoại tệ (VietinBank)
| Loại nguồn | Chi tiết | Liên kết / Thông tin |
| :--- | :--- | :--- |
| **API Chính thức** | VietinBank Open API | [developer.vietinbank.vn](https://developer.vietinbank.vn/) |
| **Endpoint (Test)** | POST | `https://sandbox.vietinbank.vn/vtb/openbanking/inquirybic-rate` |
| **Website** | Bảng tỷ giá niêm yết | [vietinbank.vn/web/home/vn/ty-gia](https://www.vietinbank.vn/web/home/vn/ty-gia) |
| **API thay thế** | VNAppMob (Dễ dùng hơn) | [vapi.vnappmob.com](https://vapi.vnappmob.com/) |

## 2. Giá Vàng (Doji & SJC)
| Loại nguồn | Chi tiết | Liên kết / Thông tin |
| :--- | :--- | :--- |
| **API Miễn phí** | Vang.today (JSON) | `https://www.vang.today/api/prices` |
| **API Key-based** | VNAppMob | `https://vapi.vnappmob.com/api/v2/gold/doji` |
| **Web Doji** | Giá vàng Doji toàn quốc | [doji.vn/bang-gia-vang/](https://doji.vn/bang-gia-vang/) |
| **Web SJC** | Giá vàng miếng SJC | [sjc.com.vn/gia-vang-trong-nuoc.html](https://sjc.com.vn/gia-vang-trong-nuoc.html) |

## 3. Giá Bạc (Phú Quý & Ancarat)
*Lưu ý: Không có API công khai, cần dùng kỹ thuật cào dữ liệu (Web Scraping).*
| Thương hiệu | Loại dữ liệu | Liên kết tra cứu |
| :--- | :--- | :--- |
| **Phú Quý** | Bạc miếng, bạc thỏi 999 | [phuquy.com.vn/gia-bac/](https://phuquy.com.vn/gia-bac/) |
| **Ancarat** | Bạc tích trữ (Anmint) | [anmint.vn/gia-bac-hom-nay](https://anmint.vn/gia-bac-hom-nay) |
| **Tổng hợp** | So sánh cả hai bên | [topi.vn/gia-bac-hom-nay.html](https://topi.vn/gia-bac-hom-nay.html) |

## 4. Lãi suất Ngân hàng
| Đơn vị | Phương thức lấy dữ liệu | Nguồn |
| :--- | :--- | :--- |
| **NHNN** | Văn bản điều hành/Trần lãi suất | [sbv.gov.vn](https://www.sbv.gov.vn) |
| **VietinBank** | API / Website chính thức | [vietinbank.vn/web/home/vn/lai-suat](https://www.vietinbank.vn/web/home/vn/lai-suat) |
| **Toàn hệ thống** | Bảng so sánh đa ngân hàng | [Vietstock Finance](https://finance.vietstock.vn/du-lieu-vi-mo/21-7/lai-suat-ngan-hang.htm) |

---

## 💡 Gợi ý Ý tưởng Mở rộng cho Bản tin
Để bản tin tài chính của bạn chuyên nghiệp và có chiều sâu hơn, bạn nên tích hợp thêm các mục sau:

1.  **Chỉ số Chứng khoán (Market Snap):**
    *   Cập nhật điểm số VN-Index, HNX-Index và thanh khoản thị trường.
    *   *Nguồn:* Thư viện `vnstock` (Python) lấy dữ liệu từ SSI/TCBS.
2.  **Giá Xăng dầu (Energy Update):**
    *   Cập nhật giá bán lẻ xăng RON 95, E5, Dầu Diesel từ Petrolimex.
    *   *Nguồn:* [petrolimex.com.vn](https://www.petrolimex.com.vn/nd/gia-ban-le-xang-dau.html).
3.  **Tỷ giá Crypto (Digital Assets):**
    *   Giá BTC, ETH và đặc biệt là tỷ giá USDT/VND (thường biến động sát với tỷ giá USD chợ đen).
    *   *Nguồn:* Binance API hoặc CoinGecko.
4.  **Lịch sự kiện Tài chính (Financial Calendar):**
    *   Nhắc lịch công bố CPI, ngày điều chỉnh giá xăng, ngày họp của FED/NHNN.
    *   Giúp người xem có cái nhìn dự báo thay vì chỉ nhìn số liệu quá khứ.
5.  **Tóm tắt tin vĩ mô (AI Daily Digest):**
    *   Sử dụng AI để tóm tắt 3 tin tức ảnh hưởng nhất đến túi tiền người dân trong ngày.

---

## 🛠 Gợi ý Giải pháp Kỹ thuật
*   **Với các nguồn có API:** Ưu tiên dùng `requests` (Python) hoặc `axios` (Node.js) để lấy dữ liệu trực tiếp.
*   **Với các nguồn chỉ có Web (Bạc, Xăng dầu):** Sử dụng `BeautifulSoup` hoặc `Playwright` để cào dữ liệu tự động mỗi sáng.
*   **Công cụ tổng hợp:** Bạn có thể hướng tới việc tạo một trang trung gian (Scraper Service) để gom tất cả dữ liệu trên thành một file JSON duy nhất.
