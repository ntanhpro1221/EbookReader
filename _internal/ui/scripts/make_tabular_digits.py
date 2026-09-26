"""Chữ số đều độ rộng cho Be Vietnam Pro.

Bản Be Vietnam Pro (fontsource) không có tính năng `tnum` và chữ số rộng khác nhau ("1" = 385, "4" = 710 đơn vị),
nên `font-variant-numeric: tabular-nums` không làm gì: đồng hồ trình phát nhảy vị trí mỗi giây, cột số lệch nhau.
Script này cắt riêng 10 chữ số của chính font ấy, đặt mọi chữ số cùng độ rộng (bằng chữ số rộng nhất) và căn giữa
nét - ra một font nhỏ dùng qua `unicode-range` chỉ cho chữ số, còn chữ cái vẫn là Be Vietnam Pro gốc.

    runtime/.venv/Scripts/python.exe ui/scripts/make_tabular_digits.py
"""
from __future__ import annotations

from pathlib import Path

from fontTools import subset
from fontTools.pens.recordingPen import DecomposingRecordingPen
from fontTools.pens.transformPen import TransformPen
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.ttLib import TTFont

UI = Path(__file__).resolve().parents[1]
SOURCE = UI / "node_modules" / "@fontsource" / "be-vietnam-pro" / "files"
TARGET = UI / "src" / "assets" / "fonts"
DIGITS = "0123456789"
FAMILY = "Be Vietnam Pro Digits"


def make(weight: int) -> Path:
    font = TTFont(SOURCE / f"be-vietnam-pro-latin-{weight}-normal.woff")
    options = subset.Options()
    options.layout_features = []
    options.name_IDs = [1, 2, 4, 6]
    options.notdef_outline = True
    subsetter = subset.Subsetter(options)
    subsetter.populate(unicodes=[ord(ch) for ch in DIGITS])
    subsetter.subset(font)

    cmap = font.getBestCmap()
    names = [cmap[ord(ch)] for ch in DIGITS]
    widest = max(font["hmtx"][name][0] for name in names)
    glyph_set = font.getGlyphSet()
    glyf = font["glyf"]
    for name in names:
        advance, _lsb = font["hmtx"][name]
        shift = (widest - advance) / 2
        recording = DecomposingRecordingPen(glyph_set)
        glyph_set[name].draw(recording)
        pen = TTGlyphPen(None)
        recording.replay(TransformPen(pen, (1, 0, 0, 1, shift, 0)))
        glyph = pen.glyph()
        glyph.recalcBounds(glyf)
        glyf[name] = glyph
        font["hmtx"][name] = (widest, getattr(glyph, "xMin", 0))

    for record in font["name"].names:
        if record.nameID in (1, 4):
            record.string = FAMILY if record.nameID == 1 else f"{FAMILY} {weight}"
        elif record.nameID == 6:
            record.string = f"BeVietnamProDigits-{weight}"
    font.flavor = "woff"
    TARGET.mkdir(parents=True, exist_ok=True)
    out = TARGET / f"be-vietnam-pro-digits-{weight}.woff"
    font.save(out)
    return out


if __name__ == "__main__":
    for weight in (400, 500, 600, 700):
        path = make(weight)
        check = TTFont(path)
        widths = {check["hmtx"][check.getBestCmap()[ord(ch)]][0] for ch in DIGITS}
        print(f"{path.name}: {path.stat().st_size} byte, độ rộng chữ số = {sorted(widths)}")
