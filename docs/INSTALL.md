# Cài đặt, nâng cấp và khôi phục

## Chuẩn bị

- Home Assistant từ 2026.10.0; tài khoản EVN CPC miền Trung có mã bắt đầu PC.
- Kết nối HTTPS từ HA đến dịch vụ CPC; dung lượng trống để lưu SQLite và PDF lịch sử.
- Tạo backup HA có thể tải về trước khi cài hoặc nâng cấp.
- Bản 2026.10.28.3 là bản chuẩn bị; chưa nghiệm thu cài mới hoặc nâng cấp thực tế.

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
2. Chép riêng thư mục custom_components/npc vào thư mục cấu hình HA, thành custom_components/npc/manifest.json. Không chép lồng thêm một cấp npc.
3. Khởi động lại HA rồi thêm tích hợp như bước 5–7 phía trên.

Không cần add-on EVN để cài mới. Không xóa add-on hoặc dữ liệu của hệ thống cũ chỉ để thử bản này.

## Nâng cấp từ bản cũ

Domain vẫn là npc; không cài song song hai integration cùng domain. Sao lưu toàn thư mục npc hiện có, dữ liệu evnvn, kho đăng nhập legacy nếu có và backup HA. Giữ thông tin phiên bản trước nâng cấp.

Cài phiên bản mới qua HACS, hoặc thay nguyên thư mục mã npc khi cài thủ công để tránh sót module cũ. Không xóa evnvn, PDF, credentials hay HA Store. Khởi động lại HA, kiểm tra entry loaded, entity ID, số liệu và WebUI. Chờ lịch sử chạy nền thay vì thêm lại liên tục. Nâng cấp từ mọi biến thể upstream chưa được kiểm chứng.

## Khôi phục

Nếu bản mới lỗi, dùng HACS Redownload chọn bản đã chạy tốt, hoặc khôi phục nguyên thư mục mã từ backup rồi restart. Nếu dữ liệu đã được thay đổi schema hoặc lỗi vẫn còn, khôi phục backup HA tương ứng bằng chức năng chính thức. Chỉ hạ mã không bảo đảm tương thích dữ liệu đã nâng cấp. Không sửa trực tiếp .storage khi HA đang chạy.

## Nguồn quy cách

- https://www.hacs.xyz/docs/publish/integration/
- https://www.hacs.xyz/docs/use/repositories/dashboard/
- https://www.hacs.xyz/docs/faq/private_repositories/
