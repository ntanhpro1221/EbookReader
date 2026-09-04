import tomllib
from pathlib import Path


INTERNAL_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = INTERNAL_ROOT.parent


def test_one_click_startup_contract() -> None:
    start_path = INTERNAL_ROOT / "Ebook Reader.vbs"
    start_bytes = start_path.read_bytes()
    assert not start_bytes.startswith(b"\xef\xbb\xbf")
    assert start_bytes.isascii()
    start = start_bytes.decode("utf-8")
    assert not (PROJECT_ROOT / "START.bat").exists()
    assert not (PROJECT_ROOT / "START.vbs").exists()
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
    assert "shell.Run command, 1, False" in start
    assert '$SetupMarker = Join-Path $RuntimeRoot ".setup_complete"' in launcher
    assert '[switch]$SetupConsole' not in launcher
    assert "Start-SetupConsole" not in launcher
    assert '$SetupScript = Join-Path $PSScriptRoot "setup_windows.ps1"' in launcher
    assert '$ShortcutScript = Join-Path $PSScriptRoot "install_windows_shortcut.ps1"' in launcher
    assert '$AppScript = Join-Path $InternalRoot "app.py"' in launcher
    assert '$Pythonw = Join-Path $RuntimeRoot ".venv\\Scripts\\pythonw.exe"' in launcher
    assert 'import ebook_reader.gui' in launcher
    assert "runtime_contract_errors" in launcher
    assert "sys.path.insert(0" in launcher
    assert '$ErrorActionPreference = "Continue"' in launcher
    assert "$ErrorActionPreference = $previousErrorAction" in launcher
    assert 'Start-Process -FilePath $Pythonw' in launcher
    assert "-PassThru" in launcher
    assert "Wait-AppWindow" in launcher
    assert "MainWindowHandle" in launcher
    assert '$StartupReadyFile = Join-Path $RuntimeRoot ".gui_ready_$PID"' in launcher
    assert '$env:EBOOK_READER_READY_FILE = $StartupReadyFile' in launcher
    assert "Test-Path -LiteralPath $ReadyFile -PathType Leaf" in launcher
    assert "$Process.ExitCode -eq 0" in launcher
    assert "Đang khởi động Ebook Reader..." in launcher
    assert "Ebook Reader vẫn đang khởi động..." in launcher
    assert "Install-AppShortcuts" in launcher
    assert '& $Python $AppScript' not in launcher
    assert "Lần chạy đầu hoặc môi trường cần được sửa." in launcher
    assert "KHÔNG THỂ KHỞI ĐỘNG EBOOK READER." in launcher
    assert '$StartupLog = Join-Path $LogsRoot "startup.log"' in launcher
    assert "Start-Transcript -Path $StartupLog -Append" in launcher
    assert "Stop-StartupLogging" in launcher
    assert "[Console]::ReadKey($true)" in launcher
    assert "cửa sổ sẽ không tự đóng" in launcher
    assert "& $SetupScript -NoPause -DependenciesOnly" in launcher
    assert "Dữ liệu project và các checkpoint audiobook được giữ nguyên." in launcher
    assert "Đang mở Ebook Reader..." not in launcher
    assert '[switch]$NoPause' in setup
    assert '[switch]$DependenciesOnly' in setup
    assert "if ($DependenciesOnly)" in setup
    assert setup.index('Ensure-WingetPackage "git" "Git.Git" "Git"') < setup.index(
        "if ($DependenciesOnly)"
    )
    assert setup.index("if ($DependenciesOnly)") < setup.index(
        'Ensure-WingetPackage "uv" "astral-sh.uv" "uv"'
    )
    assert "REPAIR DEPENDENCY HOÀN TẤT" in setup
    assert 'Set-Content -Encoding UTF8 $markerTemp' in setup
    assert 'Move-Item -Force -LiteralPath $markerTemp -Destination $SetupMarker' in setup
    assert 'uv venv --python 3.11 --clear' not in setup
    assert "--no-build-isolation -e $InternalRoot" in setup
    assert "Set-Location $InternalRoot" not in setup
    assert 'if (-not $NoPause)' in setup
    assert "function Invoke-NativeChecked" in setup
    assert ' & $Python -m pytest ' not in setup
    assert 'Ensure-WingetPackage "uv"' in setup
    assert 'Ensure-WingetPackage "git"' in setup
    assert 'Ensure-WingetPackage "ollama"' in setup
    assert 'Ensure-WingetPackage "ffmpeg"' in setup
    assert "--silent --disable-interactivity" in setup
    assert "--force-reinstall torch==2.11.0 torchaudio==2.11.0 torchvision==0.26.0" in setup
    assert "--index-url https://download.pytorch.org/whl/cu128" in setup
    assert 'ollama pull qwen3:8b' in setup
    assert "snapshot_download" in setup
    assert "revision='$Wav2Vec2Revision'" in setup
    assert "revision='$TimmBackboneRevision'" in setup
    assert '$AppName = "Ebook Reader"' in shortcut
    assert '$Launcher = Join-Path $ProjectRoot "_internal\\Ebook Reader.vbs"' in shortcut
    assert '$RootShortcutPath = Join-Path $ProjectRoot "$AppName.lnk"' in shortcut
    assert '$StartMenuShortcutPath = Join-Path $ProgramsRoot "$AppName.lnk"' in shortcut
    assert "$Shortcut.TargetPath = $Launcher" in shortcut
    assert '$Shortcut.Arguments = ""' in shortcut
    assert "wscript.exe" not in shortcut.lower()
    assert '"_internal\\ebook_reader\\assets\\ebook_reader.ico"' in shortcut
    assert "$Shortcut.IconLocation = $IconLocation" in shortcut
    project = tomllib.loads((INTERNAL_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert project["project"]["dependencies"] == [
        "PySide6==6.11.2",
        "requests==2.34.2",
        "psutil==7.2.2",
        "numpy==2.4.6",
        "scipy==1.17.1",
        "soundfile==0.14.0",
        "pyloudnorm==0.2.0",
        "pyworld==0.3.5",
        "imageio-ffmpeg==0.6.0",
        "openai-whisper==20250625",
        "faster-whisper==1.2.1",
        "ctranslate2==4.8.2",
        "torch==2.11.0",
        "torchaudio==2.11.0",
        "torchvision==0.26.0",
        "huggingface-hub==1.29.0",
        "librosa==0.11.0",
        "timm==1.0.29",
        "transformers==5.16.1",
        "utmosv2 @ git+https://github.com/sarulab-speech/UTMOSv2.git@cc2700db57bb83ee13dc31ebe1b868c254e15d09",
        "vieneu==3.3.0",
        "sea-g2p==0.9.1",
        "praat-parselmouth==0.4.7",
    ]
    assert 'VieNeuEngine' in setup
    assert 'required-set(e.voices)' in setup
    assert "whisper.load_model('turbo'" in setup
    # asr.engine defaults to "faster" and its loader refuses to download mid-run, so setup
    # has to fetch the CTranslate2 weights too - a different artifact from the .pt above.
    assert "from faster_whisper import WhisperModel" in setup
    assert "torchvision==0.26.0" in setup
    assert "fold0_s42_best_model.pth" in setup
    assert "506474f2b33dc77c234d668cc419be1861899cad" in setup
    assert "C8149D988E4BBF3F347E6966B5D769DE347A5F8C59FFCA1DC4BD4BF5B8585E57" in setup
    assert "0b5b8e868dd84f03fd87d01f9c4ff0f080fecfe8" in setup
    assert "ea9abc143ea2b9d8e1ec1de277bce02149b9cf0e" in setup
    assert "UTMOSv2 base cache revisions locked" in setup
    assert "cache_ready_v1.json" in setup
    assert "UTMOSv2 pinned offline smoke-load passed" in setup
    assert "UTMOSv2 pinned cache integrity passed" in setup
    assert "perceptual_cache_check" in setup
    assert "create_model(pretrained=True" in setup
