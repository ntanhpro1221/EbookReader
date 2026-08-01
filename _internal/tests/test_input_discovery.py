from __future__ import annotations

from e_book_reader.io_utils import discover_txt_files


def test_folder_import_is_direct_txt_only_and_natural_sorted(tmp_path) -> None:
    (tmp_path / "10.txt").write_text("ten", encoding="utf-8")
    (tmp_path / "2.TXT").write_text("two", encoding="utf-8")
    (tmp_path / "1.txt").write_text("one", encoding="utf-8")
    (tmp_path / "notes.md").write_text("ignore", encoding="utf-8")
    nested = tmp_path / "nested"
    nested.mkdir()
    (nested / "3.txt").write_text("nested", encoding="utf-8")

    files = discover_txt_files(tmp_path)

    assert [path.name for path in files] == ["1.txt", "2.TXT", "10.txt"]
