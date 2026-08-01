@echo off
setlocal EnableExtensions
chcp 65001 >nul
cd /d "%~dp0"

title E Book Reader
set "PROJECT_ROOT=%~dp0"
set "INTERNAL_ROOT=%~dp0_internal"
set "RUNTIME_ROOT=%~dp0_internal\runtime"
set "PYTHONUTF8=1"
set "E_BOOK_READER_RUNTIME=%RUNTIME_ROOT%"
set "HF_HOME=%RUNTIME_ROOT%\models\huggingface"
set "HF_HUB_CACHE=%RUNTIME_ROOT%\models\huggingface\hub"
set "TORCH_HOME=%RUNTIME_ROOT%\models\torch"
set "SETUP_MARKER=%RUNTIME_ROOT%\.setup_complete"
set "PYTHON_EXE=%RUNTIME_ROOT%\.venv\Scripts\python.exe"
set "SETUP_SCRIPT=%INTERNAL_ROOT%\scripts\setup_windows.ps1"
set "APP_SCRIPT=%INTERNAL_ROOT%\app.py"

echo ============================================================
echo                     E BOOK READER
echo ============================================================

if not exist "%SETUP_MARKER%" goto :RUN_SETUP
if not exist "%PYTHON_EXE%" goto :RUN_SETUP

"%PYTHON_EXE%" -c "import e_book_reader.gui" >nul 2>&1
if errorlevel 1 goto :RUN_SETUP

goto :LAUNCH

:RUN_SETUP
echo Lần chạy đầu hoặc môi trường cần được sửa.
echo Chương trình sẽ tự động cài đặt và tải model cần thiết.
echo Quá trình này cần Internet và có thể sử dụng nhiều dung lượng SSD.
echo.

powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%SETUP_SCRIPT%" -NoPause
if errorlevel 1 goto :SETUP_FAILED

if not exist "%SETUP_MARKER%" goto :SETUP_FAILED
if not exist "%PYTHON_EXE%" goto :SETUP_FAILED

:LAUNCH
echo Đang mở E Book Reader...
"%PYTHON_EXE%" "%APP_SCRIPT%"
set "APP_EXIT=%ERRORLEVEL%"
if not "%APP_EXIT%"=="0" (
    echo.
    echo E Book Reader đã đóng với mã lỗi %APP_EXIT%.
    echo Thông tin kỹ thuật nằm trong thư mục _internal.
    echo Nhấn phím bất kỳ để đóng...
    pause >nul
)
exit /b %APP_EXIT%

:SETUP_FAILED
echo.
echo CÀI ĐẶT KHÔNG HOÀN TẤT.
echo Không có project audiobook nào bị thay đổi.
echo Kiểm tra Internet, dung lượng SSD và lỗi bên trên, sau đó mở lại START.bat.
echo Nhấn phím bất kỳ để đóng...
pause >nul
exit /b 1
