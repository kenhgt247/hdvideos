# Video Vẽ Tay – Du Học Hải Dương (bản web)

Nhân viên mở trang web trên điện thoại, dán kịch bản, bấm **Tạo video**. Máy của GitHub dựng video (giọng VieNeu, dự phòng giọng Microsoft) rồi lưu ở mục *Releases* của repo này (riêng tư). Video cũ tự xoá sau 60 ngày.

- `engine/` – bộ máy vẽ (giống app Windows)
- `render.py` – dựng 1 video trên máy GitHub
- `process_uploads.py` – tách nền ảnh tải lên Kho hình / Nhân vật
- `web/` – trang web (Cloudflare Worker)
- `.github/workflows/` – dựng video, xử lý ảnh, đăng web, dọn video cũ

## Mã bí mật cần có (Settings → Secrets and variables → Actions)
| Tên | Là gì |
|---|---|
| `GH_PAT` | Mã GitHub (fine-grained) chỉ cho repo hdvideos: Actions, Contents = Read and write |
| `CF_API_TOKEN` | Mã Cloudflare, mẫu "Edit Cloudflare Workers" |
| `APP_PASSWORD` | Mật khẩu nhân viên dùng để vào trang web |

Sau khi thêm, vào **Actions → Dang trang web → Run workflow** để đăng web.
