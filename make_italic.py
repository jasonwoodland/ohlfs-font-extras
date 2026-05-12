#!/usr/bin/env python3
"""Generate italic and bold-italic OTFs using an aliased bitmap skew.

Each pixel row is shifted right by row // SKEW columns (floor division).
Descenders (negative rows) shift left, ascenders shift right, baseline stays fixed.

SKEW=4 → 1px per 4 rows → arctan(0.25) ≈ 14°.
"""
from __future__ import annotations

from pathlib import Path

from make_bold import (
    PIXEL,
    attach,
    bold_grid,
    empty_charstring,
    extract_subpaths,
    glyph_bbox_pixels,
    grid_to_runs,
    load_font,
    rasterize,
    rename_font,
    runs_to_charstring,
    strip_legacy_bitmap_tables,
    update_cff_top,
)

SKEW = 4          # shift 1 pixel right per SKEW rows above baseline
ITALIC_ANGLE = -14  # degrees (negative = slants right)

SRC = Path("/Users/jason/Library/Fonts/Ohlfs-Light.otf")
DST_ITALIC = Path(__file__).resolve().parent / "Ohlfs-Italic.otf"
DST_BOLD_ITALIC = Path(__file__).resolve().parent / "Ohlfs-Bold-Italic.otf"


def italic_grid(
    grid: dict[tuple[int, int], bool], skew: int = SKEW
) -> dict[tuple[int, int], bool]:
    """Shift each pixel right by (row+1) // skew columns (aliased bitmap italic).

    The +1 offsets the step boundaries 1px below the baseline so the first
    rightward step begins at row 3 rather than row 4.
    """
    return {(col + (row + 1) // skew, row): True for col, row in grid}


def apply_italic_skew(font, skew: int = SKEW, bold: bool = False) -> None:
    """Replace every glyph outline with a skewed (and optionally bold) version."""
    cs_index = font["CFF "].cff.topDictIndex[0].CharStrings
    glyph_order = font.getGlyphOrder()
    hmtx = font["hmtx"].metrics

    for name in glyph_order:
        cs = cs_index[name]
        subpaths = extract_subpaths(cs)
        subpaths = [sp for sp in subpaths if len(sp) >= 3]
        adv = hmtx[name][0]

        if not subpaths:
            cs_index[name] = attach(empty_charstring(adv), cs)
            hmtx[name] = (adv, 0)
            continue

        bbox = glyph_bbox_pixels(subpaths)
        if bbox is None:
            cs_index[name] = attach(empty_charstring(adv), cs)
            hmtx[name] = (adv, 0)
            continue

        grid = rasterize(subpaths, bbox)
        grid = italic_grid(grid, skew)
        if bold:
            grid = bold_grid(grid)
        runs = grid_to_runs(grid)
        cs_index[name] = attach(runs_to_charstring(runs, adv), cs)
        lsb = min(col_start for col_start, _, _ in runs) * PIXEL if runs else 0
        hmtx[name] = (adv, lsb)


def mark_italic(font) -> None:
    os2 = font["OS/2"]
    os2.usWeightClass = 400
    fs = os2.fsSelection
    fs |= 1 << 0     # ITALIC
    fs &= ~(1 << 6)  # clear REGULAR
    os2.fsSelection = fs
    font["post"].italicAngle = ITALIC_ANGLE
    font["head"].macStyle |= 1 << 1  # italic


def mark_bold_italic(font) -> None:
    os2 = font["OS/2"]
    os2.usWeightClass = 700
    fs = os2.fsSelection
    fs |= (1 << 0) | (1 << 5)  # ITALIC + BOLD
    fs &= ~(1 << 6)              # clear REGULAR
    os2.fsSelection = fs
    font["post"].italicAngle = ITALIC_ANGLE
    head = font["head"]
    head.macStyle |= (1 << 0) | (1 << 1)  # bold + italic


def _build(
    src: Path, dst: Path,
    family: str, subfamily: str, full: str, ps_name: str,
    skew: int = SKEW, bold: bool = False,
) -> None:
    font = load_font(src)
    apply_italic_skew(font, skew=skew, bold=bold)
    update_cff_top(font, ps_name, full, family, subfamily)
    rename_font(font, family=family, subfamily=subfamily, full=full, ps_name=ps_name)
    if bold:
        mark_bold_italic(font)
    else:
        mark_italic(font)
    strip_legacy_bitmap_tables(font)
    dst.parent.mkdir(parents=True, exist_ok=True)
    font.save(str(dst))
    print(f"Wrote {dst} ({dst.stat().st_size} bytes)")


def italic_otf(
    src: Path, dst: Path,
    family: str = "Ohlfs", subfamily: str = "Italic",
    full: str | None = None, ps_name: str | None = None,
    skew: int = SKEW,
) -> None:
    full = full or f"{family} {subfamily}"
    ps_name = ps_name or f"{family.replace(' ', '')}-{subfamily.replace(' ', '')}"
    _build(src, dst, family, subfamily, full, ps_name, skew=skew, bold=False)


def bold_italic_otf(
    src: Path, dst: Path,
    family: str = "Ohlfs", subfamily: str = "Bold Italic",
    full: str | None = None, ps_name: str | None = None,
    skew: int = SKEW,
) -> None:
    full = full or f"{family} {subfamily}"
    ps_name = ps_name or f"{family.replace(' ', '')}-{subfamily.replace(' ', '')}"
    _build(src, dst, family, subfamily, full, ps_name, skew=skew, bold=True)


def main() -> None:
    italic_otf(SRC, DST_ITALIC, family="Ohlfs", subfamily="Italic",
               full="Ohlfs Italic", ps_name="Ohlfs-Italic")
    bold_italic_otf(SRC, DST_BOLD_ITALIC, family="Ohlfs", subfamily="Bold Italic",
                    full="Ohlfs Bold Italic", ps_name="Ohlfs-BoldItalic")


if __name__ == "__main__":
    main()
