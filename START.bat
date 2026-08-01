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
echo Lan chay dau hoac moi truong can duoc sua.
echo Chuong trinh se tu dong cai dat va tai model can thiet.
echo Qua trinh nay can Internet va co the su dung nhieu dung luong SSD.
echo.

powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%SETUP_SCRIPT%" -NoPause
if errorlevel 1 goto :SETUP_FAILED

if not exist "%SETUP_MARKER%" goto :SETUP_FAILED
if not exist "%PYTHON_EXE%" goto :SETUP_FAILED

:LAUNCH
echo Dang mo E Book Reader...
"%PYTHON_EXE%" "%APP_SCRIPT%"
set "APP_EXIT=%ERRORLEVEL%"
if not "%APP_EXIT%"=="0" (
    echo.
    echo E Book Reader da dong voi ma loi %APP_EXIT%.
    echo Thong tin ky thuat nam trong thu muc _internal.
    pause
)
exit /b %APP_EXIT%

:SETUP_FAILED
echo.
echo CAI DAT KHONG HOAN TAT.
echo Khong co project audiobook nao bi thay doi.
echo Kiem tra Internet, dung luong SSD va loi ben tren, sau do mo lai START.bat.
pause
exit /b 1
