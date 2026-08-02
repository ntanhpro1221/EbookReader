# Thành phần bên thứ ba

Project không đóng gói model weights trong source ZIP. Lần cài đầu tải các dependency/model về `_internal/runtime` và mỗi thành phần giữ giấy phép riêng.

Các thành phần chính:

- Qwen3 qua Ollama;
- VieNeu / `vieneu`;
- OpenAI Whisper;
- PyTorch và torchaudio;
- PyWORLD và WORLD vocoder;
- pyloudnorm;
- PySide6;
- FFmpeg / imageio-ffmpeg;
- NumPy, SoundFile, psutil, requests và huggingface-hub.

Khi phát hành binary hoặc phân phối kèm model cache, người bảo trì phải kiểm tra phiên bản thực tế được đóng gói và giữ LICENSE/NOTICE tương ứng của từng dependency/model.
