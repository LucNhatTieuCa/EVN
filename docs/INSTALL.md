# Cài đặt, nâng cấp và khôi phục

## Chuẩn bị

- Home Assistant từ 2026.10.0; tài khoản EVN CPC miền Trung có mã bắt đầu PC.
- Kết nối HTTPS từ HA đến dịch vụ CPC; dung lượng trống để lưu SQLite và PDF lịch sử.
- Tạo backup HA có thể tải về trước khi cài hoặc nâng cấp.
- Bản 2026.10.28.4 đã test gỡ entry trên HAOS; chưa nghiệm thu cài mới hoặc nâng cấp toàn bộ gói chia sẻ.

## Cài qua HACS

Repository phải công khai. Repo private chỉ dùng lưu mã/chuẩn bị, không cài được bằng HACS.

1. Mở HACS → menu ba chấm → Custom repositories.
2. Dán URL GitHub của repository đã phát hành; chọn loại Integration → Add.
3. Tìm EVN VN, chọn Download và phiên bản muốn cài.
4. Khởi động lại Home Assistant.
5. Vào Cài đặt → Thiết bị & dịch vụ → Thêm tích hợp → EVN VN.
6. Nhập tài khoản EVN CPC; chờ tự tìm các mã liên kết. Không cần gửi mật khẩu cho người bảo trì.
7. Mở EVN Monitor trên thanh bên; kiểm tra sensor, mốc dữ liệu và tiến trình tải lịch sử.

Thêm Custom repository không có nghĩa integration đã vào danh sách mặc định của HACS.

## Cài thủ công

1. Tải mã từ revision/tag đã chọn, giải nén trên máy của bạn.
2. Chép riêng thư mục custom_components/evn vào thư mục cấu hình HA, thành custom_components/evn/manifest.json. Không chép lồng thêm một cấp npc.
3. Khởi động lại HA rồi thêm tích hợp như bước 5–7 phía trên.

Không cần add-on EVN để cài mới. Không xóa add-on hoặc dữ liệu của hệ thống cũ chỉ để thử bản này.

## Nâng cấp từ bản cũ

Domain từ bản 2026.10.28.5 là evn, thư mục custom_components/evn. Không chỉ đổi tên thư mục npc khi vẫn còn config entry domain npc: HA sẽ không tìm thấy integration cũ. Sao lưu HA và dữ liệu trước khi chuyển domain. Bản chuyển trên hệ thống chủ repo được bảo trì khi Core dừng, giữ entry_id/entity_id và dữ liệu. HACS không tự chuyển các config entry cũ sang domain mới.

Cài phiên bản mới qua HACS, hoặc thay nguyên thư mục mã evn khi cài thủ công để tránh sót module cũ. Không xóa evnvn, PDF, credentials hay HA Store. Khởi động lại HA, kiểm tra entry loaded, entity ID, số liệu và WebUI. Chờ lịch sử chạy nền thay vì thêm lại liên tục. Nâng cấp từ mọi biến thể upstream chưa được kiểm chứng.

## Khôi phục

Nếu bản mới lỗi, dùng HACS Redownload chọn bản đã chạy tốt, hoặc khôi phục nguyên thư mục mã từ backup rồi restart. Nếu dữ liệu đã được thay đổi schema hoặc lỗi vẫn còn, khôi phục backup HA tương ứng bằng chức năng chính thức. Chỉ hạ mã không bảo đảm tương thích dữ liệu đã nâng cấp. Không sửa trực tiếp .storage khi HA đang chạy.

## Nguồn quy cách

- https://www.hacs.xyz/docs/publish/integration/
- https://www.hacs.xyz/docs/use/repositories/dashboard/
- https://www.hacs.xyz/docs/faq/private_repositories/

## Gỡ tích hợp và dữ liệu

Sao lưu trước. Xóa entry trong Cài đặt → Thiết bị & dịch vụ → EVN VN sẽ xóa entity/sensor và dữ liệu mã đó. Xóa entry cuối cùng xóa toàn bộ dữ liệu EVN, thông tin đăng nhập và HA Store. Reload/disable/restart không xóa dữ liệu. Sensor công tơ vật lý thuộc integration khác và backup bên ngoài được giữ nguyên. Sau khi gỡ hết entry, có thể gỡ mã bằng HACS; nếu xóa mã trước, hook dọn dữ liệu sẽ không còn để chạy. Cài lại cần đăng nhập và tải dữ liệu lại, không tự khôi phục dữ liệu đã xóa.

## Chuyển từ domain npc sang evn

Bản 2026.10.28.5 thay domain và thư mục chương trình, giữ đường dẫn dữ liệu evnvn. Với hệ còn entry npc, cần backup và chuyển có kiểm soát cả config entry, entity registry, device identifiers và metadata HACS khi Core dừng; không sửa .storage lúc HA chạy. Nếu không cần giữ dữ liệu, có thể backup rồi gỡ entry npc bằng bản cũ trước khi cài evn; thao tác gỡ sẽ xóa dữ liệu theo chính sách đã công bố. Không tự nhận HACS download là đã di trú entry/data thành công. Các API và tên bảng/Store nội bộ cũ được giữ để tương thích dữ liệu.
