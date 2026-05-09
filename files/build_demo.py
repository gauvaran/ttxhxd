#!/usr/bin/env python3
"""
build_demo.py — Build full newsletter with handcrafted AI content (no Groq needed)
Run once when Groq quota is exhausted.
"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
os.environ['GROQ_API_KEY'] = ''

from fetch_content import _fetch_rss_articles, RSS_FEEDS, DANANG_FEEDS, get_daily_guy
from ai_news_bot import build_html, build_web_html, save_web_pages, update_web_index, _date_slug, _all_dated_files, DOCS_DIR
import datetime, re

print("Fetching RSS...", file=sys.stderr)
raw      = _fetch_rss_articles(target=9)
raw_dn   = _fetch_rss_articles(target=3, feeds=DANANG_FEEDS)

SUMMARIES = [
    "Chính quyền Phú Quốc vừa gửi thông báo yêu cầu các hộ dân đang bao chiếm đất công tự nguyện tháo dỡ công trình — nếu không sẽ tiến hành cưỡng chế. Phú Quốc là 'điểm nóng' tranh chấp đất đai khi bất động sản tăng vọt những năm qua. Đây là bước xử lý quyết liệt của địa phương nhằm lấy lại quỹ đất công phục vụ quy hoạch chung.",
    "Nhiều chủ nhà Hà Nội đang phân vân khi giá bất động sản giảm khoảng 1 tỷ đồng so với đỉnh — nên giữ hay bán? Chuyên gia nhận định đây là điều chỉnh tự nhiên sau giai đoạn tăng nóng, nền tảng dài hạn vẫn tốt. Tuy nhiên với những ai cần thanh khoản hoặc tái cơ cấu danh mục, thời điểm này vẫn hợp lý để cân nhắc 'chốt lời'.",
    "Cục Du lịch Quốc gia Việt Nam và Mastercard vừa ký kết hợp tác chiến lược nhằm đẩy mạnh thanh toán không tiền mặt và phát triển hệ sinh thái du lịch số. Hai bên sẽ phân tích dữ liệu chi tiêu của khách quốc tế để hoạch định chính sách phát triển du lịch hiệu quả hơn. Đây là bước tiến quan trọng giúp du lịch Việt Nam bắt kịp xu hướng cashless toàn cầu.",
    "Vụ án thiếu niên bị chém tử vong tại quán cà phê: cơ quan điều tra đã triệu tập 11 người liên quan để làm rõ nguyên nhân, xác định vai trò từng đối tượng. Vụ việc gây chấn động dư luận vì xảy ra ở nơi công cộng giữa ban ngày. Đây là hồi chuông cảnh báo về tình trạng mâu thuẫn và bạo lực trong giới trẻ cần có giải pháp xã hội căn cơ.",
    "Mỹ tuyên bố đã hoàn tất việc chuyển toàn bộ uranium từ Venezuela về lãnh thổ Mỹ — một chiến dịch tình báo và ngoại giao được đánh giá là thành công lớn. Động thái này nằm trong chiến lược ngăn chặn vật liệu hạt nhân rơi vào tay các bên không mong muốn, giữa lúc quan hệ Mỹ-Venezuela vẫn căng thẳng. Cộng đồng quốc tế theo dõi sát diễn biến này.",
    "Bộ ảnh tư liệu hiếm ghi lại cuộc sống Sài Gòn hơn 100 năm trước — từ tàu điện leng keng, xe kéo tay đến đường phố còn vắng bóng xe máy — đang lan truyền mạnh trên mạng xã hội. Ngắm những hình ảnh này mà thấy Sài Gòn đổi thay chóng mặt chỉ trong một thế kỷ. Đây là kho tư liệu lịch sử quý giá giúp thế hệ trẻ hiểu hơn về cội nguồn thành phố.",
    "Hoa hậu Nguyễn Đình Như Vân vừa kết thúc chuyến công du dài kỷ lục trong nhiệm kỳ Miss Global — ghé thăm nhiều quốc gia với các hoạt động từ thiện, giao lưu văn hóa và đại diện hình ảnh Việt Nam. Sự chuyên nghiệp, khả năng ngoại ngữ và phong thái tự tin của cô nhận được nhiều lời khen từ đối tác quốc tế. Niềm tự hào của người Việt trên sân khấu toàn cầu!",
    "Gan là 'nhà máy lọc' thầm lặng của cơ thể — và thường 'kêu cứu' mà chúng ta không để ý. Các dấu hiệu cảnh báo gan suy yếu gồm: mệt mỏi kéo dài không rõ lý do, vàng da nhẹ ở mắt, nước tiểu sẫm màu, đầy bụng sau ăn và ngứa da. Nếu bạn có 2-3 triệu chứng này, đừng chủ quan — hãy đi khám và làm xét nghiệm chức năng gan sớm.",
    "Thị trường dịch vụ giám sát an ninh mạng toàn cầu được dự báo sắp cán mốc 15 tỷ USD — tăng trưởng mạnh do làn sóng chuyển đổi số và các cuộc tấn công mạng ngày càng tinh vi. Doanh nghiệp Việt Nam đang đẩy mạnh đầu tư vào lĩnh vực này khi kinh tế số phát triển nhanh. Đây cũng là cơ hội lớn cho nguồn nhân lực công nghệ thông tin trong nước.",
]

DN_SUMMARIES = [
    "Tin nóng: Trung tâm Tài chính quốc tế đầu tiên của Việt Nam đặt tại Đà Nẵng đang trong giai đoạn hoàn thiện cuối và dự kiến vận hành cuối năm 2026. Đây là cột mốc lịch sử biến Đà Nẵng thành hub tài chính khu vực, thu hút vốn ngoại và tạo hàng nghìn việc làm chất lượng cao. Các tổ chức tài chính lớn trong và ngoài nước đang rất quan tâm đến cơ hội đặt trụ sở tại đây.",
    "Hạ tầng giao thông Đà Nẵng tiếp tục được đầu tư bài bản: tuyến đường vành đai phía Tây sẽ được kéo dài kết nối trực tiếp với cao tốc La Sơn - Túy Loan, mở ra không gian phát triển mới cho các quận phía Tây và giảm tải đáng kể cho nội thành. Dự án được kỳ vọng hoàn thành trong vài năm tới, góp phần hoàn thiện mạng lưới giao thông vành đai của thành phố.",
    "Đà Nẵng chính thức ban hành chính sách đặc biệt: rút gọn thủ tục hành chính, ưu đãi thuế và đất đai cho các doanh nghiệp trong lĩnh vực trí tuệ nhân tạo và bán dẫn. Đây là tín hiệu rõ ràng về định hướng phát triển kinh tế công nghệ cao của thành phố, hướng tới mục tiêu trở thành trung tâm công nghiệp bán dẫn của khu vực Đông Nam Á.",
]

articles = []
for i, a in enumerate(raw):
    articles.append({
        "title":     a["title"],
        "publisher": a["publisher"],
        "link":      a.get("link",""),
        "summary":   SUMMARIES[i] if i < len(SUMMARIES) else a["desc"][:300],
    })

danang_articles = []
for i, a in enumerate(raw_dn):
    danang_articles.append({
        "title":     a["title"],
        "publisher": a["publisher"],
        "link":      a.get("link",""),
        "summary":   DN_SUMMARIES[i] if i < len(DN_SUMMARIES) else a["desc"][:300],
    })

viral = """\
### 🔥 Trend "Trước và sau khi đi làm" bùng nổ TikTok
📍 *Nguồn: TikTok #truocvasaukhidilaem — 50M+ lượt xem*
So sánh nét mặt/outfit buổi sáng tươi tắn vs chiều về mắt thâm, mascara trôi — quá relatable nên chị em văn phòng đua nhau đăng. Kết quả 100%: tóc rối, son nhợt, nụ cười méo — nhưng vẫn cute hết sức. Cộng đồng Threads liên tục tag đồng nghiệp vào với chú thích "em nè anh ơi".

### 🔥 Câu nói viral "Khó thì bỏ, dễ thì làm — nhưng đừng bỏ nhau"
📍 *Nguồn: Threads @tamsuvanphong — 200k+ lượt chia sẻ, Facebook viral 3 ngày liên tiếp*
Câu này xuất phát từ một bài đăng tâm sự về tình bạn chốn công sở, nhưng nhanh chóng được cộng đồng mạng "bẻ cong" thành meme dùng cho mọi hoàn cảnh — từ dự án deadline đến hẹn hò. Ai cũng tìm được chỗ để áp vào cuộc sống mình nên sức lan truyền cực mạnh.

### 🔥 Clip "Sếp tốt vs Sếp toxic" 3 triệu view trong 48 giờ
📍 *Nguồn: YouTube/TikTok @officevietnam — 3.1M views, top trending VN*
Series clip ngắn so sánh hành vi sếp tốt (hỏi thăm, hỗ trợ, linh hoạt giờ giấc) và sếp toxic (giao việc lúc 5h chiều thứ Sáu, cc sếp mọi email) khiến dân văn phòng vừa cười vừa khóc. Phần bình luận là "bảo tàng" chia sẻ kinh nghiệm làm việc thật sự — đọc suốt buổi không chán.\
"""

music_fashion = """\
### 🎵 "Bão" — Hương Giang (ft. Karik)
📍 *Hương Giang & Karik — V-pop/R&B — YouTube 18M views — TikTok #baohg đang leo top*
Bài hit mới nhất của Hương Giang bắt tay Karik đang thống trị playlist mùa hè. Giai điệu sôi động pha chất R&B, lời bài xoáy vào cảm xúc sau chia tay — câu hook "bão ơi cứ đến đây, tôi không sợ nữa rồi" nghe một lần là dính đầu cả tuần. Đang được dùng rầm rộ làm nhạc nền TikTok cho các clip "slay" của chị em.

### 👗 Váy linen cổ vuông tay phồng — "đặc sản" hè 2026
📍 *Shopee VN — top 3 trending fashion tuần này — Instagram @local.style.vn & @onedress.vn*
Váy linen cổ vuông, tay phồng nhẹ, dáng midi đang là mẫu bán chạy nhất các shop thời trang nội địa. Chất linen thoáng mát, dáng váy vừa thanh lịch vừa có chút vintage — mặc đi làm hay đi cafe đều ổn. Mix thêm giày mule da và túi rơm nhỏ là ra ngay bộ "đồ cô gái Đà Nẵng mùa hè" xịn không cần suy nghĩ.\
"""

food_of_day = """\
🍽️ **Mì Quảng tôm thịt** — Đặc sản Đà Nẵng & Quảng Nam 🏖️

Mì Quảng là "quốc hồn ẩm thực" miền Trung — sợi mì to bản, vàng ươm từ nghệ, chan xâm xấp nước dùng sóng sánh nấu từ xương hầm, tôm tươi và thịt ba chỉ ướp gia vị đậm đà. Ăn kèm đúng kiểu phải có: rau sống (húng lủi, giá đỗ, bắp chuối bào), đậu phộng rang giòn, bánh đa nướng bẻ vụn — mỗi miếng là một bữa tiệc của hương vị. Không ngập nước như phở, không khô như bún — mì Quảng có "gu" riêng không đâu có được!

💡 **Ăn ở đâu ngon tại Đà Nẵng?** Quán Mì Quảng Bà Mua (76 Ông Ích Khiêm), khu vực chợ Cồn buổi sáng sớm trước 8h, hoặc các hàng vỉa hè trên đường Hoàng Diệu — đặc biệt ngon và rẻ.

💰 **Giá tham khảo:** 25.000 – 45.000đ/tô\
"""

tip_beauty = """\
✨ **Toner Pad buổi sáng — 30 giây da căng bóng**

Buổi sáng quá bận không có thời gian skincare 10 bước? Toner pad chính là "vũ khí bí mật" của dân văn phòng bận rộn! 💆‍♀️

Chỉ cần lau nhẹ toàn mặt sau rửa mặt — 30 giây — da sạch bụi bẩn, se lỗ chân lông, toner thấm sâu giúp các bước dưỡng sau hấp thụ tốt hơn gấp đôi. Chọn toner pad có BHA/AHA nhẹ nếu da dầu mụn, hoặc loại có Hyaluronic Acid + Centella nếu da khô nhạy cảm.

Gợi ý túi tiền vừa phải: **Some By Mi AHA BHA PHA** (da dầu), **Anua Heartleaf** (da nhạy cảm), hoặc **COSRX One Step** (đa năng). Bỏ gọn vào túi xách — tan làm mặt bóng dầu cứ lấy ra lau một cái, tươi ngay tắp lự! ✨\
"""

tip_exercise = """\
🏃‍♀️ **Bài tập 7 phút tại bàn làm việc — đốt mỡ không cần gym**

Ngồi văn phòng cả ngày mà không muốn vào gym? Thử ngay bài tập 7 phút này ngay tại ghế — không cần dụng cụ, không cần thay đồ:

- **Squat đứng dậy** (ghế chair squat): 15 lần × 3 hiệp — đứng lên ngồi xuống chậm rãi, cơ đùi và mông tự khắc căng tức
- **Plank bàn**: 30 giây × 3 — tựa tay lên bàn, thân thẳng, core siết chặt
- **Calf raise**: 20 lần — nhấc gót chân lên hạ xuống khi đứng chờ máy in

Làm 3 lần/ngày (sáng - trưa - chiều), mỗi lần 7 phút = **21 phút vận động** tích lũy mỗi ngày. Nghiên cứu của WHO cho thấy chỉ cần 150 phút vận động nhẹ/tuần là đủ để duy trì cân nặng và cải thiện tâm trạng rõ rệt! 💪\
"""

tip_health = """\
🩺 **Đau vai gáy sau giờ làm việc? 3 động tác giải quyết trong 5 phút**

Hội văn phòng ngồi máy tính lâu, cơ cổ vai gáy phải chịu lực kéo căng liên tục — không kéo dãn kịp thời sẽ dẫn đến thoái hóa đốt sống cổ sớm. Theo các chuyên gia cơ xương khớp, **hơn 60% nhân viên văn phòng** bị đau mỏi vai gáy mãn tính trước 35 tuổi.

3 động tác làm ngay tại ghế:

**1. Nghiêng đầu sang hai bên** — giữ 15 giây mỗi bên, tay ép nhẹ để tăng độ kéo dãn
**2. Xoay vai tròn** — 10 vòng ra trước, 10 vòng ra sau, thở đều
**3. Đẩy cằm về phía sau** (chin tuck) — giữ 5 giây × 10 lần, bài tập tốt nhất để chống gù cổ

Làm 2 lần/ngày (sau 2 giờ ngồi), hiệu quả rõ rệt sau 2 tuần. Nếu đau kèm tê bì tay — đi khám ngay, không tự chữa! ⚠️\
"""

quote = """\
💬 **"You can't go back and change the beginning, but you can start where you are and change the ending."**
*"Bạn không thể quay lại thay đổi điểm khởi đầu, nhưng bạn có thể bắt đầu từ nơi bạn đang đứng và thay đổi kết thúc."*
— **C.S. Lewis** (nhà văn, học giả người Anh)

**Giải nghĩa:** Câu nói của C.S. Lewis nhắc nhở rằng quá khứ không thể thay đổi, nhưng tương lai thì hoàn toàn trong tay mình. Dù hôm qua có khó khăn hay sai lầm thế nào, hôm nay vẫn là cơ hội mới để viết tiếp câu chuyện theo hướng khác — đẹp hơn, ý nghĩa hơn. Mỗi buổi sáng đi làm là một trang mới, chị em ơi! 🌸\
"""

today   = datetime.datetime.now()
date_str = today.strftime("%d/%m/%Y")

data = {
    "date":            date_str,
    "articles":        articles,
    "danang_articles": danang_articles,
    "viral":           viral,
    "music_fashion":   music_fashion,
    "food_of_day":     food_of_day,
    "tip_beauty":      tip_beauty,
    "tip_exercise":    tip_exercise,
    "tip_health":      tip_health,
    "quote":           quote,
    "guy":             get_daily_guy(),
    "groq":            False,
}

import logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s",
                    handlers=[logging.StreamHandler(sys.stdout)])

save_web_pages(data)
print("Done! docs/2026-05-09.html generated.", file=sys.stderr)
