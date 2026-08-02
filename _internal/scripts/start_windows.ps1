param(
    [switch]$SetupConsole
)

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

Set-Location $ProjectRoot

$env:PYTHONUTF8 = "1"
$env:E_BOOK_READER_RUNTIME = $RuntimeRoot
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
    & $Python -c "import e_book_reader.gui" *> $null
    return $LASTEXITCODE -eq 0
}

function Wait-BeforeClose {
    Read-Host "Nhấn Enter để đóng"
}

function Start-SetupConsole {
    $arguments = @(
        "-NoLogo"
        "-NoProfile"
        "-ExecutionPolicy"
        "Bypass"
        "-File"
        "`"$PSCommandPath`""
        "-SetupConsole"
    )
    Start-Process -FilePath "powershell.exe" -ArgumentList $arguments -WorkingDirectory $ProjectRoot -WindowStyle Normal
}

function Start-App {
    Start-Process -FilePath $Pythonw -ArgumentList "`"$AppScript`"" -WorkingDirectory $ProjectRoot
}

function Install-AppShortcuts {
    try {
        & $ShortcutScript -ProjectRoot $ProjectRoot | Out-Null
    } catch {
        # Shortcut là tiện ích tích hợp Windows; lỗi tạo shortcut không được chặn app khởi động.
    }
}

Install-AppShortcuts
$runtimeReady = Test-AppRuntime

if (-not $runtimeReady -and -not $SetupConsole) {
    Start-SetupConsole
    exit 0
}

if (-not $runtimeReady) {
    Write-Host "============================================================"
    Write-Host "                    EBOOK READER"
    Write-Host "============================================================"
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
}

try {
    Start-App
} catch {
    if ($SetupConsole) {
        Write-Host ""
        Write-Host "Không thể mở Ebook Reader." -ForegroundColor Red
        Write-Host "Chi tiết: $($_.Exception.Message)" -ForegroundColor DarkGray
        Wait-BeforeClose
    }
    exit 1
}
exit 0
