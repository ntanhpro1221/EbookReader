from pathlib import Path
import re


INTERNAL_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = INTERNAL_ROOT.parent


def test_root_is_user_focused() -> None:
    assert {item.name for item in PROJECT_ROOT.iterdir()} == {
        "START.bat",
        "README.md",
        "_internal",
    }
    assert (INTERNAL_ROOT / "AGENTS.md").is_file()


def test_technical_name_is_consistent() -> None:
    assert PROJECT_ROOT.name == "e_book_reader"
    assert (INTERNAL_ROOT / "e_book_reader" / "__init__.py").is_file()
    legacy_package = "e" + "book_reader"
    assert not (INTERNAL_ROOT / legacy_package).exists()


def test_temporary_prototype_names_are_absent() -> None:
    forbidden = ["Book" + "VoiceStudio", "Novel" + "2MP3"]
    allowed_suffixes = {".py", ".md", ".toml", ".ps1", ".bat"}
    for path in PROJECT_ROOT.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in allowed_suffixes:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        for term in forbidden:
            assert term.lower() not in text.lower(), f"legacy term found in {path}"
        legacy_package = "e" + "book_reader"
        pattern = rf"(?<![a-z0-9_]){re.escape(legacy_package)}(?![a-z0-9_])"
        assert re.search(pattern, text, re.I) is None
