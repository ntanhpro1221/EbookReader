$ErrorActionPreference = "Stop"

$utf8 = New-Object System.Text.UTF8Encoding($false)
[Console]::InputEncoding = $utf8
[Console]::OutputEncoding = $utf8
$OutputEncoding = $utf8
try {
    $Host.UI.RawUI.WindowTitle = "Ebook Reader"
} catch {
    # Một số host không hỗ trợ đổi tiêu đề; việc mở app vẫn tiếp tục bình thường.
}

$InternalRoot = Split-Path -Parent $PSScriptRoot
$ProjectRoot = Split-Path -Parent $InternalRoot
$RuntimeRoot = Join-Path $InternalRoot "runtime"
$SetupMarker = Join-Path $RuntimeRoot ".setup_complete"
$Python = Join-Path $RuntimeRoot ".venv\Scripts\python.exe"
$Pythonw = Join-Path $RuntimeRoot ".venv\Scripts\pythonw.exe"
$SetupScript = Join-Path $PSScriptRoot "setup_windows.ps1"
$ShortcutScript = Join-Path $PSScriptRoot "install_windows_shortcut.ps1"
$AppScript = Join-Path $InternalRoot "app.py"
$StartupPollMilliseconds = 250
$StartupProgressIntervalSeconds = 5
$StartupWindowTimeoutSeconds = 180
$StartupReadyFile = Join-Path $RuntimeRoot ".gui_ready_$PID"

Set-Location $ProjectRoot

$env:PYTHONUTF8 = "1"
$env:EBOOK_READER_RUNTIME = $RuntimeRoot
$env:HF_HOME = Join-Path $RuntimeRoot "models\huggingface"
$env:HF_HUB_CACHE = Join-Path $env:HF_HOME "hub"
$env:HF_HUB_DISABLE_XET = "1"
$env:HF_HUB_DISABLE_SYMLINKS_WARNING = "1"
$env:TORCH_HOME = Join-Path $RuntimeRoot "models\torch"

function Test-AppRuntime {
    if (-not (Test-Path -LiteralPath $SetupMarker -PathType Leaf)) {
        return $false
    }
    if (-not (Test-Path -LiteralPath $Python -PathType Leaf)) {
        return $false
    }
    if (-not (Test-Path -LiteralPath $Pythonw -PathType Leaf)) {
        return $false
    }
    & $Python -c "import sys; sys.path.insert(0, r'''$InternalRoot'''); import ebook_reader.gui" *> $null
    return $LASTEXITCODE -eq 0
}

function Wait-BeforeClose {
    Read-Host "Nhấn Enter để đóng"
}

function Show-StartupHeader {
    Write-Host "============================================================"
    Write-Host "                    EBOOK READER"
    Write-Host "============================================================"
    Write-Host "Đang khởi động Ebook Reader..." -ForegroundColor Cyan
    Write-Host ""
}

function Wait-AppWindow(
    [System.Diagnostics.Process]$Process,
    [string]$ReadyFile
) {
    $startedAt = [DateTime]::UtcNow
    $deadline = $startedAt.AddSeconds($StartupWindowTimeoutSeconds)
    $nextProgress = $startedAt.AddSeconds($StartupProgressIntervalSeconds)

    while ([DateTime]::UtcNow -lt $deadline) {
        if (Test-Path -LiteralPath $ReadyFile -PathType Leaf) {
            return
        }
        if ($Process.HasExited) {
            if ($Process.ExitCode -eq 0) {
                return
            }
            throw "Tiến trình Ebook Reader đã kết thúc với exit code $($Process.ExitCode)."
        }
        $Process.Refresh()
        if ($Process.MainWindowHandle -ne [IntPtr]::Zero) {
            return
        }
        $now = [DateTime]::UtcNow
        if ($now -ge $nextProgress) {
            $elapsed = [int]($now - $startedAt).TotalSeconds
            Write-Host "Ebook Reader vẫn đang khởi động... ${elapsed}s"
            $nextProgress = $now.AddSeconds($StartupProgressIntervalSeconds)
        }
        Start-Sleep -Milliseconds $StartupPollMilliseconds
    }

    throw "Ebook Reader chưa hiển thị cửa sổ sau $StartupWindowTimeoutSeconds giây."
}

function Start-App {
    Write-Host "Đang nạp giao diện..."
    Remove-Item -Force -LiteralPath $StartupReadyFile -ErrorAction SilentlyContinue
    $env:EBOOK_READER_READY_FILE = $StartupReadyFile
    try {
        $process = Start-Process -FilePath $Pythonw -ArgumentList "`"$AppScript`"" -WorkingDirectory $ProjectRoot -PassThru
        Wait-AppWindow $process $StartupReadyFile
        Write-Host "Cửa sổ Ebook Reader đã sẵn sàng." -ForegroundColor Green
    } finally {
        Remove-Item -Force -LiteralPath $StartupReadyFile -ErrorAction SilentlyContinue
        Remove-Item Env:EBOOK_READER_READY_FILE -ErrorAction SilentlyContinue
    }
}

function Install-AppShortcuts {
    try {
        & $ShortcutScript -ProjectRoot $ProjectRoot | Out-Null
    } catch {
        # Shortcut là tiện ích tích hợp Windows; lỗi tạo shortcut không được chặn app khởi động.
    }
}

Show-StartupHeader
Install-AppShortcuts
Write-Host "Đang kiểm tra môi trường..."
$runtimeReady = Test-AppRuntime

if (-not $runtimeReady) {
    Write-Host ""
    Write-Host "Lần chạy đầu hoặc môi trường cần được sửa."
    Write-Host "Chương trình sẽ tự động cài đặt và tải model cần thiết."
    Write-Host "Quá trình này cần Internet và có thể sử dụng nhiều dung lượng SSD."
    Write-Host ""

    try {
        & $SetupScript -NoPause
        if ($LASTEXITCODE -ne 0) {
            throw "Trình cài đặt trả về mã lỗi $LASTEXITCODE."
        }
        if (-not (Test-AppRuntime)) {
            throw "Môi trường ứng dụng vẫn chưa sẵn sàng sau khi cài đặt."
        }
    } catch {
        Write-Host ""
        Write-Host "CÀI ĐẶT KHÔNG HOÀN TẤT." -ForegroundColor Red
        Write-Host "Quá trình chuẩn bị ứng dụng gặp lỗi."
        Write-Host "Không có project audiobook nào bị thay đổi."
        Write-Host "Hãy đọc dòng Chi tiết bên dưới, khắc phục nguyên nhân rồi mở lại Ebook Reader."
        Write-Host "Chi tiết: $($_.Exception.Message)" -ForegroundColor DarkGray
        Wait-BeforeClose
        exit 1
    }
} else {
    Write-Host "[OK] Môi trường sẵn sàng."
}

try {
    Start-App
} catch {
    Write-Host ""
    Write-Host "Không thể mở Ebook Reader." -ForegroundColor Red
    Write-Host "Chi tiết: $($_.Exception.Message)" -ForegroundColor DarkGray
    Wait-BeforeClose
    exit 1
}
exit 0
