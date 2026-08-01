from pathlib import Path


INTERNAL_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = INTERNAL_ROOT.parent


def test_one_click_startup_contract() -> None:
    start_bytes = (PROJECT_ROOT / "START.bat").read_bytes()
    assert not start_bytes.startswith(b"\xef\xbb\xbf")
    start = start_bytes.decode("utf-8")
    setup_path = INTERNAL_ROOT / "scripts" / "setup_windows.ps1"
    setup_bytes = setup_path.read_bytes()
    assert setup_bytes.startswith(b"\xef\xbb\xbf")
    setup = setup_bytes.decode("utf-8-sig")

    assert 'set "INTERNAL_ROOT=%~dp0_internal"' in start
    assert 'set "RUNTIME_ROOT=%~dp0_internal\\runtime"' in start
    assert r'set "SETUP_MARKER=%RUNTIME_ROOT%\.setup_complete"' in start
    assert 'scripts\\setup_windows.ps1' in start
    assert 'set "APP_SCRIPT=%INTERNAL_ROOT%\\app.py"' in start
    assert 'import e_book_reader.gui' in start
    assert "Lần chạy đầu hoặc môi trường cần được sửa." in start
    assert "Đang mở E Book Reader..." in start
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
    assert "snapshot_download('openbmb/VoxCPM2'" in setup
    assert 'Vieneu(max_batch_size=1)' in setup
    assert "whisper.load_model('turbo'" in setup
