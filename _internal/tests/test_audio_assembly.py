from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from e_book_reader.audio_io import (
    AudioQualityError,
    atomic_write_wav,
    assemble_chapter_atomic,
    combine_full_book_atomic,
    verify_mp3,
    validate_audio_array,
)
from e_book_reader.config import build_settings


def test_real_ffmpeg_chapter_assembly_is_atomic_and_decodable(tmp_path: Path) -> None:
    settings = build_settings(overrides={"tts": {"min_seconds_per_100_chars": 0.2}})
    sample_rate = int(settings["tts"]["sample_rate"])
    entries: list[tuple[Path, int]] = []
    for index, frequency in enumerate((220, 330), start=1):
        timeline = np.arange(int(sample_rate * 0.8), dtype=np.float32) / sample_rate
        audio = 0.12 * np.sin(2 * np.pi * frequency * timeline)
        wav = tmp_path / f"{index}.wav"
        atomic_write_wav(
            wav,
            audio,
            sample_rate,
            "Đây là một câu thử nghiệm đủ dài.",
            settings,
        )
        entries.append((wav, 300 if index == 1 else 0))

    output = tmp_path / "chapter_001.mp3"
    checksum = assemble_chapter_atomic(
        entries,
        output,
        settings,
        title="Chương 1",
        book_title="Sách thử",
        track=1,
        work_dir=tmp_path / "silence",
    )

    assert len(checksum) == 64
    assert verify_mp3(output) == (True, "ok")
    assert not list(tmp_path.rglob("*.part.*"))


def test_real_ffmpeg_full_book_copy_is_atomic_and_decodable(tmp_path: Path) -> None:
    settings = build_settings(overrides={"tts": {"min_seconds_per_100_chars": 0.2}})
    sample_rate = int(settings["tts"]["sample_rate"])
    timeline = np.arange(int(sample_rate * 0.8), dtype=np.float32) / sample_rate
    audio = 0.12 * np.sin(2 * np.pi * 260 * timeline)
    wav = tmp_path / "source.wav"
    atomic_write_wav(wav, audio, sample_rate, "Một câu thử nghiệm đủ dài.", settings)

    chapters: list[Path] = []
    for track in (1, 2):
        chapter = tmp_path / f"chapter_{track:03d}.mp3"
        assemble_chapter_atomic(
            [(wav, 0)],
            chapter,
            settings,
            title=f"Chương {track}",
            book_title="Sách thử",
            track=track,
            work_dir=tmp_path / "silence",
        )
        chapters.append(chapter)

    output = tmp_path / "full_book.mp3"
    checksum = combine_full_book_atomic(chapters, output, "Sách thử")

    assert len(checksum) == 64
    assert verify_mp3(output) == (True, "ok")
    assert not list(tmp_path.rglob("*.part.*"))


def test_stereo_audio_is_rejected_instead_of_flattened() -> None:
    settings = build_settings(overrides={"tts": {"min_seconds_per_100_chars": 0.2}})
    stereo = np.zeros((48_000, 2), dtype=np.float32)

    with pytest.raises(AudioQualityError, match="mono"):
        validate_audio_array(stereo, "Một câu đủ dài để kiểm tra.", settings, 48_000)


def test_full_book_failure_cleans_temporary_files(tmp_path: Path, monkeypatch) -> None:
    chapter = tmp_path / "chapter.mp3"
    chapter.write_bytes(b"ID3" + b"x" * 5000)
    output = tmp_path / "full.mp3"
    monkeypatch.setattr(
        "e_book_reader.audio_io.run_hidden",
        lambda *_args, **_kwargs: SimpleNamespace(returncode=1, stderr="boom"),
    )

    with pytest.raises(AudioQualityError, match="assembly failed"):
        combine_full_book_atomic([chapter], output, "Book")

    assert not list(tmp_path.rglob("*.part.*"))
