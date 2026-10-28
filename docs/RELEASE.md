# Chuẩn bị phát hành

Source by BlackSmartHome - Custom by honganhlqt

Phiên bản chuẩn bị: 2026.10.28.3; domain npc. Nguồn bàn giao: bản HACS preparation của project HA, không phải bản chụp trực tiếp từ HA đang chạy.

## Trước khi upload

1. Đích đã chốt: LucNhatTieuCa/EVN (public theo yêu cầu chủ hệ thống ngày 28/10/2026). Khi đổi đích, chạy `python3 tools/set_repository.py OWNER/REPO` để điền URL và codeowner thực. Lệnh chỉ sửa metadata local.
2. Chạy `python3 -m unittest discover -s tests -v` và `python3 tools/check_package.py`. Chế độ `--preparation` cho phép thiếu metadata, không chứng minh sẵn sàng phát hành.
3. Rà diff và toàn bộ commits dự định push; không đưa dữ liệu vận hành hoặc hồ sơ workspace vào Git. Gói này chưa có lịch sử Git để rà.
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
