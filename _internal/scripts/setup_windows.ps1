param(
    [switch]$NoPause,
    [switch]$DependenciesOnly
)

$ErrorActionPreference = "Stop"
$InternalRoot = Split-Path -Parent $PSScriptRoot
$RuntimeRoot = Join-Path $InternalRoot "runtime"
$SetupMarker = Join-Path $RuntimeRoot ".setup_complete"
$VenvRoot = Join-Path $RuntimeRoot ".venv"
$Python = Join-Path $VenvRoot "Scripts\python.exe"
$ModelsRoot = Join-Path $RuntimeRoot "models"
$SetupSchemaVersion = 2
$PerceptualCacheSchemaVersion = 1
$UtmosSourceCommit = "cc2700db57bb83ee13dc31ebe1b868c254e15d09"
$UtmosRevision = "506474f2b33dc77c234d668cc419be1861899cad"
$UtmosCheckpointSha256 = "C8149D988E4BBF3F347E6966B5D769DE347A5F8C59FFCA1DC4BD4BF5B8585E57"
$Wav2Vec2Revision = "0b5b8e868dd84f03fd87d01f9c4ff0f080fecfe8"
$TimmBackboneRevision = "ea9abc143ea2b9d8e1ec1de277bce02149b9cf0e"
$UtmosRoot = Join-Path $ModelsRoot "utmosv2"
$UtmosCheckpoint = Join-Path $UtmosRoot "fold0_s42_best_model.pth"
$PerceptualReadyMarker = Join-Path $UtmosRoot "cache_ready_v1.json"

New-Item -ItemType Directory -Force -Path $RuntimeRoot | Out-Null

$env:PYTHONUTF8 = "1"
$env:EBOOK_READER_RUNTIME = $RuntimeRoot
$env:HF_HOME = Join-Path $ModelsRoot "huggingface"
$env:HF_HUB_CACHE = Join-Path $env:HF_HOME "hub"
$env:HF_HUB_DISABLE_XET = "1"
$env:HF_HUB_DISABLE_SYMLINKS_WARNING = "1"
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
        winget install --exact --id $PackageId --silent --disable-interactivity --accept-package-agreements --accept-source-agreements
    } "Cài $DisplayName bằng winget"
    Refresh-Path
    if (-not (Get-Command $Command -ErrorAction SilentlyContinue)) {
        throw "Đã chạy winget nhưng vẫn không tìm thấy $DisplayName ($Command)."
    }
}

function Install-AppDependencies {
    Write-Host "Cài Ebook Reader và các dependency Python..."
    Invoke-NativeChecked {
        & $Python -m pip install --no-build-isolation -e $InternalRoot
    } "Cài Ebook Reader"
    & $Python -c "import importlib.metadata as m, json; direct=json.loads(m.distribution('utmosv2').read_text('direct_url.json') or '{}'); vcs=direct.get('vcs_info', {}); source=direct.get('url', '').removeprefix('git+').rstrip('/').removesuffix('.git').casefold(); expected='https://github.com/sarulab-speech/UTMOSv2.git'.rstrip('/').removesuffix('.git').casefold(); assert source == expected, source; assert vcs.get('commit_id', '').casefold() == '$UtmosSourceCommit'.casefold()" 2>$null
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Cài lại UTMOSv2 từ commit chính thức đã khóa..."
        Invoke-NativeChecked {
            & $Python -m pip install --force-reinstall --no-deps "utmosv2 @ git+https://github.com/sarulab-speech/UTMOSv2.git@$UtmosSourceCommit"
        } "Khóa source UTMOSv2"
    }
    Invoke-NativeChecked { & $Python -m pip check } "Kiểm tra dependency"
}

function Test-PytorchCudaStack {
    & $Python -c "import torch, torchaudio, torchvision; assert torch.__version__.startswith('2.8.0+cu128'), torch.__version__; assert torchaudio.__version__.startswith('2.8.0+cu128'), torchaudio.__version__; assert torchvision.__version__.startswith('0.23.0'), torchvision.__version__; assert torch.version.cuda == '12.8', torch.version.cuda" 2>$null
    return $LASTEXITCODE -eq 0
}

function Install-PytorchCudaStack {
    if (Test-PytorchCudaStack) {
        Write-Host "[OK] PyTorch CUDA 12.8"
        return
    }
    Write-Host "Cài/repair PyTorch CUDA 12.8 cho RTX 50 Laptop..."
    Invoke-NativeChecked {
        & $Python -m pip install --upgrade --force-reinstall torch==2.11.0 torchaudio==2.11.0 torchvision==0.26.0 --index-url https://download.pytorch.org/whl/cu128
    } "Cài PyTorch CUDA 12.8"
    if (-not (Test-PytorchCudaStack)) {
        throw "PyTorch/torchaudio không phải CUDA 12.8 hoặc torchvision không tương thích."
    }
}

function Write-SetupMarker {
    $markerPayload = [ordered]@{
        schema_version = $SetupSchemaVersion
        completed_at = (Get-Date).ToString("o")
        python = $Python
        internal_root = $InternalRoot
        perceptual_ready_marker = $PerceptualReadyMarker
    }
    $markerTemp = "$SetupMarker.part"
    $markerPayload | ConvertTo-Json | Set-Content -Encoding UTF8 $markerTemp
    Move-Item -Force -LiteralPath $markerTemp -Destination $SetupMarker
}

function Install-PerceptualQaAssets {
    New-Item -ItemType Directory -Force -Path $UtmosRoot | Out-Null
    Remove-Item -Force -LiteralPath $PerceptualReadyMarker -ErrorAction SilentlyContinue
    Write-Host "Tải checkpoint UTMOSv2 và chuẩn bị cache perceptual QA..."
    $PreviousHfOffline = $env:HF_HUB_OFFLINE
    $PreviousTransformersOffline = $env:TRANSFORMERS_OFFLINE
    try {
        $env:HF_HUB_OFFLINE = "0"
        $env:TRANSFORMERS_OFFLINE = "0"
        Invoke-NativeChecked {
            & $Python -c "from huggingface_hub import hf_hub_download; from pathlib import Path; import hashlib; target=Path(r'$UtmosCheckpoint'); downloaded=Path(hf_hub_download(repo_id='sarulab-speech/UTMOSv2', filename='fold0_s42_best_model.pth', revision='$UtmosRevision', local_dir=r'$UtmosRoot')); assert downloaded.resolve()==target.resolve(), (downloaded,target); handle=target.open('rb'); actual=hashlib.file_digest(handle, 'sha256').hexdigest().upper(); handle.close(); assert actual=='$UtmosCheckpointSha256', actual; print('UTMOSv2 checkpoint:', target)"
        } "Tải checkpoint UTMOSv2"
        Invoke-NativeChecked {
            & $Python -c "from huggingface_hub import snapshot_download; snapshot_download(repo_id='facebook/wav2vec2-base', revision='$Wav2Vec2Revision', cache_dir=r'$env:HF_HUB_CACHE', allow_patterns=['config.json','preprocessor_config.json','pytorch_model.bin']); snapshot_download(repo_id='timm/tf_efficientnetv2_s.in21k_ft_in1k', revision='$TimmBackboneRevision', cache_dir=r'$env:HF_HUB_CACHE', allow_patterns=['model.safetensors']); print('UTMOSv2 pinned base snapshots prepared')"
        } "Tải snapshot nền UTMOSv2 đã khóa"
        Invoke-NativeChecked {
            & $Python -c "from pathlib import Path; hub=Path(r'$env:HF_HUB_CACHE'); refs=[(hub/'models--facebook--wav2vec2-base'/'refs'/'main','$Wav2Vec2Revision'),(hub/'models--timm--tf_efficientnetv2_s.in21k_ft_in1k'/'refs'/'main','$TimmBackboneRevision')]; [(p.parent.mkdir(parents=True,exist_ok=True),p.write_text(rev,encoding='utf-8')) for p,rev in refs]; assert all(p.read_text(encoding='utf-8').strip()==rev for p,rev in refs); print('UTMOSv2 base cache revisions locked')"
        } "Khóa revision cache nền UTMOSv2"

        $env:HF_HUB_OFFLINE = "1"
        $env:TRANSFORMERS_OFFLINE = "1"
        Invoke-NativeChecked {
            & $Python -c "from utmosv2 import create_model; m=create_model(pretrained=True, config='fusion_stage3', fold=0, checkpoint_path=r'$UtmosCheckpoint', seed=42, device='cpu'); del m; print('UTMOSv2 pinned offline smoke-load passed')"
        } "Kiểm tra cache UTMOSv2 offline"
    } finally {
        if ($null -eq $PreviousHfOffline) {
            Remove-Item Env:HF_HUB_OFFLINE -ErrorAction SilentlyContinue
        } else {
            $env:HF_HUB_OFFLINE = $PreviousHfOffline
        }
        if ($null -eq $PreviousTransformersOffline) {
            Remove-Item Env:TRANSFORMERS_OFFLINE -ErrorAction SilentlyContinue
        } else {
            $env:TRANSFORMERS_OFFLINE = $PreviousTransformersOffline
        }
    }

    $markerPayload = [ordered]@{
        schema_version = $PerceptualCacheSchemaVersion
        completed_at = (Get-Date).ToString("o")
        checkpoint_revision = $UtmosRevision
        checkpoint_sha256 = $UtmosCheckpointSha256
        wav2vec2_revision = $Wav2Vec2Revision
        timm_backbone_revision = $TimmBackboneRevision
        checkpoint_path = $UtmosCheckpoint
        model_config = "fusion_stage3"
        fold = 0
        seed = 42
        hf_home = $env:HF_HOME
    }
    $markerTemp = "$PerceptualReadyMarker.part"
    $markerPayload | ConvertTo-Json | Set-Content -Encoding UTF8 $markerTemp
    Move-Item -Force -LiteralPath $markerTemp -Destination $PerceptualReadyMarker
    Invoke-NativeChecked {
        & $Python -c "from pathlib import Path; from ebook_reader.runtime_contract import perceptual_cache_check; result=perceptual_cache_check(Path(r'$RuntimeRoot')); assert result['ok'], result['detail']; print('UTMOSv2 pinned cache integrity passed')"
    } "Kiểm tra integrity cache UTMOSv2"
}

Ensure-WingetPackage "git" "Git.Git" "Git"

if ($DependenciesOnly) {
    if (-not (Test-Path -LiteralPath $Python -PathType Leaf)) {
        throw "Không thể repair dependency vì runtime Python chưa tồn tại."
    }
    Write-Host "=== Ebook Reader - repair dependency Python ===" -ForegroundColor Cyan
    Write-Host "Xác minh dependency, PyTorch CUDA và cache model; giữ nguyên dữ liệu sách."
    Install-PytorchCudaStack
    Install-AppDependencies
    Install-PerceptualQaAssets
    Write-SetupMarker
    Write-Host "REPAIR DEPENDENCY HOÀN TẤT" -ForegroundColor Green
    return
}

Write-Host "=== Ebook Reader - cài đặt Windows ===" -ForegroundColor Cyan
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
Install-PytorchCudaStack

Install-AppDependencies

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

Write-Host "Tải và smoke-load VieNeu..."
Invoke-NativeChecked {
    & $Python -c "from ebook_reader.character_registry import VIENEU_PRESETS; from ebook_reader.config import build_settings; from ebook_reader.tts import VieNeuEngine; s=build_settings(); e=VieNeuEngine(s, print); e.load(); required={p['name'] for p in VIENEU_PRESETS}; missing=required-set(e.voices); assert not missing, f'VieNeu presets missing: {sorted(missing)}'; print('VieNeu voices:', len(e.voices)); e.unload(); print('VieNeu ready')"
} "Smoke-load VieNeu"

Write-Host "Tải Whisper Turbo..."
Invoke-NativeChecked {
    & $Python -c "import whisper; m=whisper.load_model('turbo', device='cpu', download_root=r'$WhisperRoot'); del m; print('Whisper Turbo ready')"
} "Tải Whisper Turbo"

Install-PerceptualQaAssets

Write-Host "Chạy system check..."
Invoke-NativeChecked { & $Python (Join-Path $PSScriptRoot "check_system.py") } "Chạy system check"

Write-SetupMarker

Write-Host ""
Write-Host "CÀI ĐẶT HOÀN TẤT" -ForegroundColor Green
Write-Host "Ebook Reader sẽ được mở tự động."
if (-not $NoPause) {
    Read-Host "Nhấn Enter để đóng"
}
