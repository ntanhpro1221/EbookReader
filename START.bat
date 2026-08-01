@echo off
setlocal EnableExtensions
chcp 65001 >nul
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0_internal\scripts\start_windows.ps1"
exit /b %ERRORLEVEL%
