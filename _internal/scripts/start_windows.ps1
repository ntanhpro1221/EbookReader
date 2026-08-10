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
$LogsRoot = Join-Path $RuntimeRoot "logs"
$StartupLog = Join-Path $LogsRoot "startup.log"
$script:RuntimeCheckDetails = ""
$script:TranscriptStarted = $false

Set-Location $ProjectRoot

$env:PYTHONUTF8 = "1"
$env:EBOOK_READER_RUNTIME = $RuntimeRoot
$env:HF_HOME = Join-Path $RuntimeRoot "models\huggingface"
$env:HF_HUB_CACHE = Join-Path $env:HF_HOME "hub"
$env:HF_HUB_DISABLE_XET = "1"
$env:HF_HUB_DISABLE_SYMLINKS_WARNING = "1"
$env:TORCH_HOME = Join-Path $RuntimeRoot "models\torch"

function Test-AppRuntime {
    $script:RuntimeCheckDetails = ""
    if (-not (Test-Path -LiteralPath $SetupMarker -PathType Leaf)) {
        $script:RuntimeCheckDetails = "Thiếu marker cài đặt: $SetupMarker"
        return $false
    }
    if (-not (Test-Path -LiteralPath $Python -PathType Leaf)) {
        $script:RuntimeCheckDetails = "Thiếu runtime Python: $Python"
        return $false
    }
    if (-not (Test-Path -LiteralPath $Pythonw -PathType Leaf)) {
        $script:RuntimeCheckDetails = "Thiếu runtime pythonw: $Pythonw"
        return $false
    }
    $previousErrorAction = $ErrorActionPreference
    try {
        # Windows PowerShell 5.1 có thể biến stderr của native process thành terminating error.
        # Thu traceback lại để launcher tự phân loại repair thay vì thoát trước khi đọc exit code.
        $ErrorActionPreference = "Continue"
        $checkOutput = & $Python -c "import sys; from pathlib import Path; sys.path.insert(0, r'''$InternalRoot'''); from ebook_reader.runtime_contract import runtime_contract_errors; errors=runtime_contract_errors(Path(r'''$RuntimeRoot''')); assert not errors, '\n'.join(errors); import ebook_reader.gui" 2>&1
        $checkExitCode = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $previousErrorAction
    }
    if ($checkExitCode -ne 0) {
        $script:RuntimeCheckDetails = ($checkOutput | Out-String).Trim()
        return $false
    }
    return $true
}

function Wait-BeforeClose {
    Write-Host "Nhấn phím bất kỳ để đóng; cửa sổ sẽ không tự đóng." -ForegroundColor Yellow
    while ($true) {
        try {
            [void][Console]::ReadKey($true)
            return
        } catch {
            Start-Sleep -Seconds 1
        }
    }
}

function Start-StartupLogging {
    New-Item -ItemType Directory -Force -Path $LogsRoot | Out-Null
    try {
        Start-Transcript -Path $StartupLog -Append | Out-Null
        $script:TranscriptStarted = $true
    } catch {
        $script:TranscriptStarted = $false
    }
}

function Stop-StartupLogging {
    if (-not $script:TranscriptStarted) {
        return
    }
    try {
        Stop-Transcript | Out-Null
    } catch {
        # Không để lỗi đóng transcript che mất lỗi khởi động gốc.
    }
    $script:TranscriptStarted = $false
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

function Invoke-Launcher {
    Show-StartupHeader
    Install-AppShortcuts
    Write-Host "Đang kiểm tra môi trường..."
    $runtimeReady = Test-AppRuntime

    if (-not $runtimeReady) {
        $canRepairDependencies = (
            (Test-Path -LiteralPath $SetupMarker -PathType Leaf) -and
            (Test-Path -LiteralPath $Python -PathType Leaf) -and
            (Test-Path -LiteralPath $Pythonw -PathType Leaf)
        )
        if ($canRepairDependencies) {
            Write-Host ""
            Write-Host "Môi trường hoặc cache model đã cũ; đang repair runtime đã khóa."
            Write-Host "Dữ liệu project và các checkpoint audiobook được giữ nguyên."
            if ($script:RuntimeCheckDetails) {
                Write-Host "Phát hiện: $script:RuntimeCheckDetails" -ForegroundColor DarkGray
            }
            & $SetupScript -NoPause -DependenciesOnly
            if ($LASTEXITCODE -ne 0) {
                throw "Repair dependency trả về mã lỗi $LASTEXITCODE."
            }
            if (-not (Test-AppRuntime)) {
                throw "Môi trường vẫn chưa sẵn sàng sau repair dependency.`n$script:RuntimeCheckDetails"
            }
        } else {
            Write-Host ""
            Write-Host "Lần chạy đầu hoặc môi trường cần được sửa."
            Write-Host "Chương trình sẽ tự động cài đặt và tải model cần thiết."
            Write-Host "Quá trình này cần Internet và có thể sử dụng nhiều dung lượng SSD."
            Write-Host ""
            & $SetupScript -NoPause
            if ($LASTEXITCODE -ne 0) {
                throw "Trình cài đặt trả về mã lỗi $LASTEXITCODE."
            }
            if (-not (Test-AppRuntime)) {
                throw "Môi trường vẫn chưa sẵn sàng sau khi cài đặt.`n$script:RuntimeCheckDetails"
            }
        }
    }

    Write-Host "[OK] Môi trường sẵn sàng."
    Start-App
}

$launcherExitCode = 0
Start-StartupLogging
try {
    Invoke-Launcher
} catch {
    $launcherExitCode = 1
    Write-Host ""
    Write-Host "KHÔNG THỂ KHỞI ĐỘNG EBOOK READER." -ForegroundColor Red
    Write-Host "Không có project audiobook nào bị thay đổi."
    Write-Host "Chi tiết: $($_.Exception.Message)" -ForegroundColor Red
    Write-Host "Log khởi động: $StartupLog" -ForegroundColor Yellow
} finally {
    Stop-StartupLogging
}

if ($launcherExitCode -ne 0) {
    Wait-BeforeClose
    exit $launcherExitCode
}
exit 0
