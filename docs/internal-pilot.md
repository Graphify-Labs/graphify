# Graphify Pilot nội bộ

Một tiến trình web, một hàng đợi xử lý tuần tự, một file SQLite và một thư mục dữ liệu trên server Linux. Admin cấp tài khoản từ màn hình **Quản trị máy chủ**. Mỗi tài khoản có danh sách dự án riêng. Admin thấy số dự án, số job chờ, đang chạy và bị lỗi, đồng thời có thể đặt lại mật khẩu, khóa hoặc mở khóa tài khoản.

## Chạy trên server

Từ thư mục checkout, chạy bằng một tài khoản dịch vụ Linux thông thường. Tạo thư mục dữ liệu thuộc tài khoản đó và chỉ cấp quyền cho tài khoản đó. Ví dụ dùng thư mục riêng dưới home của tài khoản dịch vụ.

```bash
python3 -m venv .venv
.venv/bin/pip install '.[mcp]'
.venv/bin/python -m graphify.pilot --data-dir ~/graphify-data init-admin admin
.venv/bin/python -m graphify.pilot --data-dir ~/graphify-data serve
```

Mở `http://127.0.0.1:8000` để thử trên chính máy server. Lệnh tạo admin hỏi mật khẩu qua terminal. Có thể cài `'.[mcp,svg]'` thay cho `'.[mcp]'` nếu cần xuất SVG.

Qua proxy nội bộ, chạy ứng dụng ở loopback và đặt URL nội bộ thực tế vào `--origin`.

```bash
.venv/bin/python -m graphify.pilot --data-dir ~/graphify-data serve \
    --origin https://graphify.intra
```

Tại proxy, dùng chứng chỉ HTTPS mà máy trong công ty tin cậy. Forward các route web và `/mcp/` tới `http://127.0.0.1:8000`, giữ `Host` theo đúng `--origin`, giữ `Authorization` và các header MCP. Đặt giới hạn upload của proxy tối thiểu 50 MiB và timeout đủ cho truy vấn. Firewall giới hạn truy cập proxy theo subnet công ty hoặc VPN.

Ví dụ cấu hình bên trong virtual host HTTPS hiện có của Nginx.

```nginx
location / {
    client_max_body_size 50m;
    proxy_pass http://127.0.0.1:8000;
    proxy_set_header Host graphify.intra;
    proxy_set_header X-Forwarded-For $remote_addr;
    proxy_set_header X-Forwarded-Proto https;
    proxy_set_header Authorization $http_authorization;
    proxy_buffering off;
    proxy_read_timeout 90s;
}
```

Để thử nhanh trên một subnet tin cậy khi chưa có proxy, dùng IP LAN thực của server. HTTP gửi mật khẩu và token trên mạng dưới dạng không mã hóa, vì vậy dùng tài khoản và repo thử nghiệm cho cách này.

```bash
.venv/bin/python -m graphify.pilot --data-dir ~/graphify-data serve \
    --host 192.168.1.10 --origin http://192.168.1.10:8000
```

Khi chạy lâu dài, đưa lệnh `serve` vào trình quản lý dịch vụ của server. Dùng một tiến trình, có tự khởi động lại và giới hạn tài nguyên ở cấp dịch vụ hoặc máy ảo. Nếu dùng systemd, đặt `User` là tài khoản dịch vụ, `Restart=on-failure`, `NoNewPrivileges=true` và cấu hình giới hạn bộ nhớ, CPU và dung lượng phân vùng phù hợp với dữ liệu thử nghiệm.

## Cách thử

1. Admin đăng nhập, mở **Quản trị máy chủ** và tạo hai tài khoản.
2. Đăng nhập bằng từng tài khoản, mở **Tải repo lên** và chọn một ZIP mã nguồn. Lệnh dưới đây tạo ZIP mẫu từ fixture có sẵn trong repo.

   ```bash
   git archive -o /tmp/graphify-demo.zip HEAD:worked/example/raw
   ```

3. Khi dự án báo **Sẵn sàng**, chọn một nút trong **Đồ thị**, thử **Truy vấn** và mở báo cáo. Các nút phổ biến hiển thị ngay trong UI, còn truy vấn chạy trên toàn bộ graph. Giao diện pilot không tải JavaScript từ mạng ngoài. Các bản HTML xuất theo định dạng gốc của Graphify có thể cần CDN cho thư viện trực quan hóa.
4. Mở **Kết nối MCP**, tạo token và bấm **Thử kết nối**. Cấu hình agent với URL dự án, transport Streamable HTTP và header `Authorization` trong mẫu. Dùng agent có đường mạng tới server để hỏi về nút hoặc đường liên kết. Token có hiệu lực 30 ngày, giới hạn vào một dự án và có thể thu hồi hoặc thay thế. Việc khóa tài khoản hoặc đặt lại mật khẩu thu hồi các phiên web và token của tài khoản.
5. Xác nhận tài khoản thứ hai chỉ thấy dự án của mình. Thử thu hồi token MCP của một dự án rồi gọi lại bằng token cũ.

## Dữ liệu và giới hạn

- Dữ liệu nằm trong thư mục `--data-dir`. SQLite giữ tài khoản, phiên, dự án, trạng thái job và mã băm token. Thư mục `projects/` giữ snapshot mã nguồn và kết quả Graphify theo từng dự án. ZIP tải lên được gỡ sau khi giải nén. Để sao lưu đơn giản, dừng tiến trình rồi sao lưu cả thư mục. Xóa dự án trong UI sẽ xóa snapshot, đồ thị và token của dự án.
- Mỗi tài khoản có tối đa 10 dự án. Giới hạn là 50 MiB ZIP, 250 MiB sau giải nén, 16 MiB mỗi file, 15.000 mục và 64 MiB cho `graph.json`. File đặc biệt, đường dẫn thoát ra ngoài thư mục và symlink bị từ chối. Metadata Git, kết quả Graphify có sẵn và file dạng `.env` bị loại bỏ. Chỉ cấp tài khoản cho nhóm thử nghiệm tin cậy. Bộ phân tích đọc các file trong ZIP và không chạy script của repo.
- Pilot phân tích mã nguồn và cấu trúc Markdown cục bộ. Web hỗ trợ truy vấn, giải thích nút, tìm đường, phân tích ảnh hưởng, đọc mục Markdown, hub, benchmark, chẩn đoán liên kết, báo cáo, đồ thị và xuất file. Các tích hợp cần dịch vụ hoặc thông tin xác thực khác như phân tích ngữ nghĩa bằng LLM, import Git qua mạng, GitHub PR, đọc database sống và đẩy dữ liệu vào graph database vẫn dùng CLI riêng.
