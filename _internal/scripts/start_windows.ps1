$ErrorActionPreference = "Stop"

$utf8 = New-Object System.Text.UTF8Encoding($false)
[Console]::InputEncoding = $utf8
[Console]::OutputEncoding = $utf8
$OutputEncoding = $utf8
try {
    $Host.UI.RawUI.WindowTitle = "E Book Reader"
} catch {
    # Một số host không hỗ trợ đổi tiêu đề; việc mở app vẫn tiếp tục bình thường.
}

$InternalRoot = Split-Path -Parent $PSScriptRoot
$ProjectRoot = Split-Path -Parent $InternalRoot
$RuntimeRoot = Join-Path $InternalRoot "runtime"
$SetupMarker = Join-Path $RuntimeRoot ".setup_complete"
$Python = Join-Path $RuntimeRoot ".venv\Scripts\python.exe"
$SetupScript = Join-Path $PSScriptRoot "setup_windows.ps1"
$AppScript = Join-Path $InternalRoot "app.py"

Set-Location $ProjectRoot

$env:PYTHONUTF8 = "1"
$env:E_BOOK_READER_RUNTIME = $RuntimeRoot
$env:HF_HOME = Join-Path $RuntimeRoot "models\huggingface"
$env:HF_HUB_CACHE = Join-Path $env:HF_HOME "hub"
$env:TORCH_HOME = Join-Path $RuntimeRoot "models\torch"

function Test-AppRuntime {
    if (-not (Test-Path -LiteralPath $SetupMarker -PathType Leaf)) {
        return $false
    }
    if (-not (Test-Path -LiteralPath $Python -PathType Leaf)) {
        return $false
    }
    & $Python -c "import e_book_reader.gui" *> $null
    return $LASTEXITCODE -eq 0
}

function Wait-BeforeClose {
    Read-Host "Nhấn Enter để đóng"
}

Write-Host "============================================================"
Write-Host "                    E BOOK READER"
Write-Host "============================================================"

if (-not (Test-AppRuntime)) {
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
        Write-Host "Không thể tải hoặc chuẩn bị thành phần cần thiết."
        Write-Host "Không có project audiobook nào bị thay đổi."
        Write-Host "Hãy kiểm tra kết nối Internet và dung lượng SSD, sau đó mở lại START.bat."
        Write-Host "Chi tiết: $($_.Exception.Message)" -ForegroundColor DarkGray
        Wait-BeforeClose
        exit 1
    }
}

Write-Host "Đang mở E Book Reader..."
try {
    & $Python $AppScript
    $appExit = $LASTEXITCODE
} catch {
    Write-Host ""
    Write-Host "Không thể mở E Book Reader." -ForegroundColor Red
    Write-Host "Chi tiết: $($_.Exception.Message)" -ForegroundColor DarkGray
    Wait-BeforeClose
    exit 1
}

if ($appExit -ne 0) {
    Write-Host ""
    Write-Host "E Book Reader đã đóng với mã lỗi $appExit." -ForegroundColor Red
    Write-Host "Thông tin kỹ thuật nằm trong thư mục _internal."
    Wait-BeforeClose
}
exit $appExit
