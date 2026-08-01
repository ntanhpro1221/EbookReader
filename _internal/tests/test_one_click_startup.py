from pathlib import Path


INTERNAL_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = INTERNAL_ROOT.parent


def test_one_click_startup_contract() -> None:
    start = (PROJECT_ROOT / "START.bat").read_text(encoding="utf-8")
    setup = (INTERNAL_ROOT / "scripts" / "setup_windows.ps1").read_text(encoding="utf-8")

    assert 'set "INTERNAL_ROOT=%~dp0_internal"' in start
    assert 'set "RUNTIME_ROOT=%~dp0_internal\\runtime"' in start
    assert '.setup_complete_0.2.0-alpha.8' in start
    assert 'scripts\\setup_windows.ps1' in start
    assert 'set "APP_SCRIPT=%INTERNAL_ROOT%\\app.py"' in start
    assert 'import e_book_reader' in start
    assert '[switch]$NoPause' in setup
    assert 'Set-Content -Encoding UTF8 $SetupMarker' in setup
    assert '--no-build-isolation -e ".[dev]"' in setup
    assert 'if (-not $NoPause)' in setup
    assert "function Invoke-NativeChecked" in setup
    assert 'Invoke-NativeChecked { & $Python -m pytest }' in setup
