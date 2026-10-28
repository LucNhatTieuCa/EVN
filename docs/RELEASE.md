# Chuẩn bị phát hành

Source by SmartBlackHome - Custom by LucNhatTieuCa

Phiên bản hiện tại: 2026.10.28.6; domain evn. Mã phiên bản này đã được kiểm tra trên Home Assistant 2026.10.2; gói không kèm dữ liệu vận hành.

## Trước khi upload

1. Đích đã chốt: LucNhatTieuCa/EVN (public theo yêu cầu chủ hệ thống ngày 28/10/2026). Khi đổi đích, chạy `python3 tools/set_repository.py OWNER/REPO` để điền URL và codeowner thực. Lệnh chỉ sửa metadata local.
2. Chạy `python3 -m unittest discover -s tests -v` và `python3 tools/check_package.py`. Chế độ `--preparation` cho phép thiếu metadata, không chứng minh sẵn sàng phát hành.
3. Rà diff và toàn bộ commits dự định push; không đưa dữ liệu vận hành hoặc hồ sơ workspace vào Git. Rà cả các commit mới dự định push.
4. Chạy CI HACS/hassfest trên repo đích; kiểm thử cài mới HA sạch, nâng cấp, restart giữa batch và phục hồi backup. Ghi riêng kết quả từng mục.
5. Chủ hệ thống đã yêu cầu công khai repo EVN ngày 28/10/2026 để dùng HACS.
6. Giữ ghi nguồn và giấy phép vendor. Chưa có LICENSE xác minh cho mã kế thừa; không tự gán MIT hoặc giấy phép khác. Dòng ghi nguồn không thay cho giấy phép tái phân phối.

## Phạm vi bản đầu

CPC, tự tìm mã liên kết, sensor và EVN Monitor; lưu lịch sử/PDF theo checkpoint, hàng đợi request dùng chung, đối chiếu Electric tùy chọn. Không hỗ trợ tất cả miền EVN; không cam kết lịch sử/PDF mà nhà cung cấp không trả về.

Các test ngoại tuyến dùng boundary HA/HTTP giả lập; không thay thế nghiệm thu Home Assistant thật. Commit SHA và trạng thái CI xem trực tiếp trên GitHub. Chưa có nghiệm thu HA sạch hoặc phát hành release.

## Phạm vi CI

Workflow kiểm tra custom repository. HACS Action bỏ riêng check `license` vì chưa xác minh được giấy phép nguồn kế thừa; giữ giấy phép vendor và ghi nguồn, không tự gán giấy phép OSI. Mỗi run hiện cảnh báo và ghi giới hạn này trong job summary. CI xanh không xác nhận giấy phép hoặc điều kiện đưa vào hacs/default. Các check khác, gồm topics, vẫn chạy.

Quy cách action: https://www.hacs.xyz/docs/publish/action/ .

Trường categories chưa được khai báo do image hassfest hiện tại từ chối trường này; HACS có thể cảnh báo thiếu category. Đây là metadata tùy chọn của custom integration, không ảnh hưởng chức năng.

## Thay đổi 2026.10.28.4

Xóa entry xóa dữ liệu theo mã; xóa mã cuối dọn toàn bộ runtime data. Unload/reload không xóa. Chờ worker/poll dừng trước khi xóa SQLite. Registry và Recorder được dọn theo đúng entity sở hữu; giữ sensor vật lý, dữ liệu mã còn lại và backup ngoài runtime. Đã kiểm thử gỡ thật bốn entry trên HAOS 2026.10.2; chi tiết số lượng được ghi trong báo cáo quản trị ngoài repo.

## 2026.10.28.5

Thư mục HACS và domain đổi npc → evn. Form đăng nhập hiển thị LucNhatTieuCa; ghi nguồn thống nhất Source by SmartBlackHome - Custom by LucNhatTieuCa. Cần chuyển domain có kiểm soát cho bản npc đã cấu hình; đọc INSTALL.md. Không đổi biểu giá, lịch gọi API hay dữ liệu điện trong lần đổi tên.

Tải lịch sử chạy bằng background task, không chặn bootstrap của HA. Checkpoint giữ khi lỗi HTTP; trạng thái ghi mã HTTP an toàn và xóa lỗi cũ khi batch thành công. Đây không phải cam kết nhà cung cấp luôn trả đủ PDF/lịch sử.


## 2026.10.28.6

Thêm khung tiến trình đồng bộ và hai sensor chẩn đoán cho mỗi mã khách hàng. Hiển thị số PDF đã lưu/tổng/còn thiếu, phần trăm đã lưu, số bản ghi tháng/ngày và lý do/thời điểm thử lại. PDF chưa được EVN cung cấp không tính là đã tải; tổng chưa biết không được gán0hoặc100%. Tiến trình chỉ đọc dữ liệu tại HA, không tăng truy vấn EVN.

Dữ liệu lịch sử cập nhật lên sensor sau từng đợt, không chờ PDF hoàn tất. Phát dữ liệu cache không reset lịch poll4giờ. Giữ64entityID hiện có khi nâng cấp; thêm8sensor chẩn đoán trên bộ4mã đã kiểm tra. MigrationSQLite chỉ thêm cột tiến trình.

Đã qua33test ngoại tuyến, packagecheck, kiểm traCore/API/database/entityIDs và giao diện desktop/mobile trên HA2026.10.2. Các ảnh README vẫn là dữ liệu minh họa. Việc tải toàn bộ PDF phụ thuộc dữ liệu và giới hạn máy chủ; không coi khởi tạo hoàn tất khi còn tài liệu thiếu. Không phải bằng chứng kiểm thử mọi phiên bảnHA hoặc khôi phục backup.

Khung tiến trình tự ẩn sau khi xử lý xong các dữ liệu có thể tải của mã đang xem; không ẩn khi đang tải, chờ lượt, tạm nghỉ hoặc chưa biết tổng. Các sensor chẩn đoán được giữ.
