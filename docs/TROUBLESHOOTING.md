# Xử lý lỗi và báo lỗi

| Hiện tượng | Kiểm tra / thao tác |
|---|---|
| HACS không nhận repo | URL đúng, repo public, loại Integration; manifest đủ documentation/issue_tracker/codeowners. |
| Không tìm thấy EVN VN trong Thêm tích hợp | Đã restart HA, đủ phiên bản, đúng custom_components/npc/manifest.json; xem log custom_components.npc. |
| Đăng nhập thất bại | Thử ứng dụng CPC chính thức; xử lý CAPTCHA/đổi mật khẩu ở đó. Chỉ CPC được hỗ trợ. Không thử lặp liên tục khi bị giới hạn. |
| HTTP 429 / dữ liệu chậm | Chờ cooldown và lịch cập nhật; không restart liên tục để ép gọi API. |
| PDF chưa đủ | Xem số tải/chưa được cung cấp/đang chờ; lịch sử tải theo batch. EVN có thể không còn cung cấp PDF cũ. |
| Tiền dự tính trống | Kiểm tra có hóa đơn và biểu giá/VAT phù hợp; không coi trống là 0 đồng. |
| Electric không có khung hoặc sai đối chiếu | Chọn sensor phù hợp và kiểm tra mốc gốc, đơn vị, thời điểm; không lấy hiệu hai công tơ khác nhau. |
| WebUI cũ sau nâng cấp | Tải lại trang hoặc xóa cache trình duyệt; đối chiếu phiên bản integration. |

Dữ liệu tài chính/PDF yêu cầu phiên HA xác thực. File giao diện tĩnh và ping được phục vụ không cần đăng nhập. Tài khoản HA có quyền đọc các API này có thể thấy dữ liệu điện; chưa có phân quyền riêng theo từng mã khách hàng.

Khi báo lỗi, cung cấp phiên bản HA/Core, phiên bản integration, cách cài, bước tái hiện, thời điểm kèm múi giờ và log tối thiểu. Che mã khách hàng, tên, địa chỉ, token, mật khẩu, số hóa đơn và dữ liệu tài chính. Không đính kèm database, credentials, PDF thật hay backup HA. Kiểm tra log trước khi gửi vì mã khách hàng có thể xuất hiện trong cảnh báo.
