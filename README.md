# Screen Copilot (AI Desktop Companion) 🖥️✨

> **Your Hands-free Real-time AI Assistant for Anything on Your Screen.**  
> Hỗ trợ hỏi đáp thông minh trên mọi ứng dụng, trình duyệt web, tài liệu PDF, code và game thông qua nhận diện hình ảnh màn hình thời gian thực (Vision Multimodal) và đàm thoại giọng nói 1:1.

---

## 🚀 Tính năng nổi bật (Features)

- 👁️ **Screen Vision Intelligence:** Tự động chụp và phân tích cửa sổ đang chọn hoặc toàn màn hình bằng các mô hình Multimodal Vision LLM mới nhất.
- 🎙️ **Real-time 1:1 Voice Chat:** Chế độ đàm thoại trực tiếp rảnh tay; chỉ cần nói vào mic, hệ thống tự động nghe, phân tích hình ảnh và trả lời.
- 🔊 **Ultra Low-Latency Vietnamese TTS:** Giọng đọc tiếng Việt tự nhiên (`vi-VN-HoaiMyNeural`), tối ưu truyền tải trực tiếp trên RAM (phát âm thanh ngay trong <0.7s). Có nút bật/tắt đọc tiện lợi.
- 📊 **Rich Markdown & Native Table UI:** Hiển thị mượt mà định dạng văn bản Markdown và tự động vẽ bảng dữ liệu trực quan theo chuẩn Dark Theme hiện đại.
- 🪟 **Floating Semi-transparent Overlay:** Cửa sổ nổi trong suốt nằm trên cùng, hỗ trợ kéo thả, co giãn kích thước linh hoạt và phím tắt ẩn/hiện nhanh (`Alt + Q`).
- ⚡ **Siêu tối ưu băng thông:** Nén ảnh chuẩn WebP chất lượng cao giúp giảm tới 60% dung lượng payload gửi đi mà vẫn đảm bảo độ nét tuyệt đối cho OCR.

---

## 🛠️ Cài đặt (Installation)

### Yêu cầu:
- Python 3.10+ (Windows)
- Cài đặt các thư viện cần thiết:

```bash
pip install requests pillow mss SpeechRecognition edge-tts pygame pygetwindow
```

---

## 🎮 Khởi chạy (Usage)

Chạy trực tiếp file Python:
```bash
python overlay_copilot.py
```
Hoặc dùng file batch `start_copilot.bat` để chạy ngầm không hiện cửa sổ console màu đen.

- **Phím tắt:** Bấm `Alt + Q` để ẩn/hiện cửa sổ Copilot bất cứ lúc nào.
- **Chọn mục tiêu:** Chọn cửa sổ ứng dụng/web/game cụ thể hoặc để toàn màn hình Desktop.
