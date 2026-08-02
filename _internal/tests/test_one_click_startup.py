import tomllib
from pathlib import Path


INTERNAL_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = INTERNAL_ROOT.parent


def test_one_click_startup_contract() -> None:
    start_path = INTERNAL_ROOT / "START.vbs"
    start_bytes = start_path.read_bytes()
    assert not start_bytes.startswith(b"\xef\xbb\xbf")
    assert start_bytes.isascii()
    start = start_bytes.decode("utf-8")
    assert not (PROJECT_ROOT / "START.bat").exists()
    assert not (PROJECT_ROOT / "START.vbs").exists()
    assert not (PROJECT_ROOT / "E Book Reader.vbs").exists()
    assert (PROJECT_ROOT / "Ebook Reader.lnk").is_file()

    launcher_path = INTERNAL_ROOT / "scripts" / "start_windows.ps1"
    launcher_bytes = launcher_path.read_bytes()
    assert launcher_bytes.startswith(b"\xef\xbb\xbf")
    launcher = launcher_bytes.decode("utf-8-sig")

    setup_path = INTERNAL_ROOT / "scripts" / "setup_windows.ps1"
    setup_bytes = setup_path.read_bytes()
    assert setup_bytes.startswith(b"\xef\xbb\xbf")
    setup = setup_bytes.decode("utf-8-sig")

    shortcut_path = INTERNAL_ROOT / "scripts" / "install_windows_shortcut.ps1"
    shortcut = shortcut_path.read_text(encoding="utf-8")

    assert 'scripts\\start_windows.ps1' in start
    assert "shell.Run command, 0, False" in start
    assert '$SetupMarker = Join-Path $RuntimeRoot ".setup_complete"' in launcher
    assert '[switch]$SetupConsole' in launcher
    assert '$SetupScript = Join-Path $PSScriptRoot "setup_windows.ps1"' in launcher
    assert '$ShortcutScript = Join-Path $PSScriptRoot "install_windows_shortcut.ps1"' in launcher
    assert '$AppScript = Join-Path $InternalRoot "app.py"' in launcher
    assert '$Pythonw = Join-Path $RuntimeRoot ".venv\\Scripts\\pythonw.exe"' in launcher
    assert 'import e_book_reader.gui' in launcher
    assert 'Start-Process -FilePath "powershell.exe"' in launcher
    assert '-WindowStyle Normal' in launcher
    assert 'Start-Process -FilePath $Pythonw' in launcher
    assert "Install-AppShortcuts" in launcher
    assert '& $Python $AppScript' not in launcher
    assert "Lần chạy đầu hoặc môi trường cần được sửa." in launcher
    assert "CÀI ĐẶT KHÔNG HOÀN TẤT." in launcher
    assert "Đang mở Ebook Reader..." not in launcher
    assert '[switch]$NoPause' in setup
    assert 'Set-Content -Encoding UTF8 $markerTemp' in setup
    assert 'Move-Item -Force -LiteralPath $markerTemp -Destination $SetupMarker' in setup
    assert 'uv venv --python 3.11 --clear' not in setup
    assert '--no-build-isolation -e "."' in setup
    assert 'if (-not $NoPause)' in setup
    assert "function Invoke-NativeChecked" in setup
    assert ' & $Python -m pytest ' not in setup
    assert 'Ensure-WingetPackage "uv"' in setup
    assert 'Ensure-WingetPackage "ollama"' in setup
    assert 'Ensure-WingetPackage "ffmpeg"' in setup
    assert 'pip install torch==2.8.0 torchaudio==2.8.0' in setup
    assert 'ollama pull qwen3:8b' in setup
    assert "snapshot_download" not in setup
    assert '$AppName = "Ebook Reader"' in shortcut
    assert '$Launcher = Join-Path $ProjectRoot "_internal\\START.vbs"' in shortcut
    assert '$RootShortcutPath = Join-Path $ProjectRoot "$AppName.lnk"' in shortcut
    assert '$StartMenuShortcutPath = Join-Path $ProgramsRoot "$AppName.lnk"' in shortcut
    assert "$Shortcut.TargetPath = $Launcher" in shortcut
    assert '$Shortcut.Arguments = ""' in shortcut
    assert "wscript.exe" not in shortcut.lower()
    assert '"_internal\\e_book_reader\\assets\\e_book_reader.ico"' in shortcut
    assert "$Shortcut.IconLocation = $IconLocation" in shortcut
    project = tomllib.loads((INTERNAL_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert project["project"]["dependencies"] == [
        "PySide6==6.8.0",
        "requests==2.32.3",
        "psutil==6.0.0",
        "numpy==1.26.4",
        "soundfile==0.13.1",
        "imageio-ffmpeg==0.6.0",
        "openai-whisper==20250625",
        "vieneu==3.2.3",
    ]
    assert 'VieNeuEngine' in setup
    assert 'required-set(e.voices)' in setup
    assert "whisper.load_model('turbo'" in setup
