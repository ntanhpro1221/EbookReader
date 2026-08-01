param(
    [switch]$NoPause
)

$ErrorActionPreference = "Stop"
$InternalRoot = Split-Path -Parent $PSScriptRoot
$RuntimeRoot = Join-Path $InternalRoot "runtime"
$SetupMarker = Join-Path $RuntimeRoot ".setup_complete"
$VenvRoot = Join-Path $RuntimeRoot ".venv"
$Python = Join-Path $VenvRoot "Scripts\python.exe"
$ModelsRoot = Join-Path $RuntimeRoot "models"

New-Item -ItemType Directory -Force -Path $RuntimeRoot | Out-Null
Set-Location $InternalRoot

$env:PYTHONUTF8 = "1"
$env:E_BOOK_READER_RUNTIME = $RuntimeRoot
$env:HF_HOME = Join-Path $ModelsRoot "huggingface"
$env:HF_HUB_CACHE = Join-Path $env:HF_HOME "hub"
$env:TORCH_HOME = Join-Path $ModelsRoot "torch"

function Invoke-NativeChecked([scriptblock]$Command, [string]$Label) {
    & $Command
    if ($LASTEXITCODE -ne 0) {
        throw "$Label thất bại với exit code $LASTEXITCODE."
    }
}

function Refresh-Path {
    $machine = [Environment]::GetEnvironmentVariable("Path", "Machine")
    $user = [Environment]::GetEnvironmentVariable("Path", "User")
    $env:Path = "$machine;$user"
}

function Ensure-WingetPackage([string]$Command, [string]$PackageId, [string]$DisplayName) {
    if (Get-Command $Command -ErrorAction SilentlyContinue) {
        Write-Host "[OK] $DisplayName"
        return
    }
    if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
        throw "Không tìm thấy winget. Hãy cài App Installer từ Microsoft Store."
    }
    Write-Host "Đang cài $DisplayName..."
    Invoke-NativeChecked {
        winget install --exact --id $PackageId --accept-package-agreements --accept-source-agreements
    } "Cài $DisplayName bằng winget"
    Refresh-Path
    if (-not (Get-Command $Command -ErrorAction SilentlyContinue)) {
        throw "Đã chạy winget nhưng vẫn không tìm thấy $DisplayName ($Command)."
    }
}

Write-Host "=== E Book Reader - cài đặt Windows ===" -ForegroundColor Cyan
Write-Host "Môi trường và model được lưu gọn trong _internal\runtime."
Write-Host "Máy nên đang cắm sạc và SSD nên còn tối thiểu 30-40 GB."

Ensure-WingetPackage "uv" "astral-sh.uv" "uv"

Ensure-WingetPackage "ollama" "Ollama.Ollama" "Ollama"
Ensure-WingetPackage "ffmpeg" "Gyan.FFmpeg" "FFmpeg"

if (-not (Test-Path -LiteralPath $Python -PathType Leaf)) {
    Write-Host "Tạo môi trường Python 3.11..."
    Invoke-NativeChecked { uv venv --python 3.11 --seed $VenvRoot } "Tạo Python venv"
} else {
    Write-Host "Tái sử dụng môi trường Python hiện có; không xóa runtime của sách đang chạy."
    Invoke-NativeChecked {
        & $Python -c "import sys; assert sys.version_info[:2] == (3, 11), sys.version"
    } "Kiểm tra Python venv"
}

Invoke-NativeChecked { & $Python -m pip install --upgrade pip setuptools wheel } "Cập nhật pip/setuptools/wheel"
Write-Host "Cài PyTorch CUDA 12.8 cho RTX 50 Laptop..."
Invoke-NativeChecked {
    & $Python -m pip install torch==2.8.0 torchaudio==2.8.0 --index-url https://download.pytorch.org/whl/cu128
} "Cài PyTorch CUDA 12.8"

Write-Host "Cài E Book Reader và các engine..."
Invoke-NativeChecked {
    & $Python -m pip install --no-build-isolation -e "."
} "Cài E Book Reader"
Invoke-NativeChecked { & $Python -m pip check } "Kiểm tra dependency"

New-Item -ItemType Directory -Force -Path $env:HF_HOME | Out-Null
$WhisperRoot = Join-Path $ModelsRoot "whisper"
New-Item -ItemType Directory -Force -Path $WhisperRoot | Out-Null

Write-Host "Kiểm tra CUDA..."
Invoke-NativeChecked {
    & $Python -c "import torch; assert torch.cuda.is_available(), 'PyTorch không nhận CUDA'; print('GPU:', torch.cuda.get_device_name(0)); print('VRAM GB:', round(torch.cuda.get_device_properties(0).total_memory/1024**3, 1)); print('Torch:', torch.__version__, 'CUDA:', torch.version.cuda)"
} "Kiểm tra CUDA"

Write-Host "Tải Qwen3 8B qua Ollama..."
try {
    & ollama list | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "Ollama server chưa chạy" }
} catch {
    Start-Process -FilePath "ollama" -ArgumentList "serve" -WindowStyle Hidden
    Start-Sleep -Seconds 4
}
Invoke-NativeChecked { & ollama pull qwen3:8b } "Tải Qwen3 8B"
Write-Host "Tải Qwen3 4B cho profile Nhanh..."
Invoke-NativeChecked { & ollama pull qwen3:4b } "Tải Qwen3 4B"

Write-Host "Tải VoxCPM2..."
Invoke-NativeChecked {
    & $Python -c "from huggingface_hub import snapshot_download; snapshot_download('openbmb/VoxCPM2', revision='bffb3df5a29440629464e5e839f4d214c8714c3d'); print('VoxCPM2 ready')"
} "Tải VoxCPM2"

Write-Host "Tải và smoke-load VieNeu..."
Invoke-NativeChecked {
    & $Python -c "from vieneu import Vieneu; t=Vieneu(max_batch_size=1); print('VieNeu voices:', len(list(t.list_preset_voices()))); del t; print('VieNeu ready')"
} "Smoke-load VieNeu"

Write-Host "Tải Whisper Turbo..."
Invoke-NativeChecked {
    & $Python -c "import whisper; m=whisper.load_model('turbo', device='cpu', download_root=r'$WhisperRoot'); del m; print('Whisper Turbo ready')"
} "Tải Whisper Turbo"

Write-Host "Chạy system check..."
Invoke-NativeChecked { & $Python (Join-Path $PSScriptRoot "check_system.py") } "Chạy system check"

$markerPayload = [ordered]@{
    completed_at = (Get-Date).ToString("o")
    python = $Python
    internal_root = $InternalRoot
}
$markerTemp = "$SetupMarker.part"
$markerPayload | ConvertTo-Json | Set-Content -Encoding UTF8 $markerTemp
Move-Item -Force -LiteralPath $markerTemp -Destination $SetupMarker

Write-Host ""
Write-Host "CÀI ĐẶT HOÀN TẤT" -ForegroundColor Green
Write-Host "E Book Reader sẽ được mở tự động."
if (-not $NoPause) {
    Read-Host "Nhấn Enter để đóng"
}
