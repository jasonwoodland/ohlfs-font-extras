#!/usr/bin/env python3
"""Build Ohlfs-Extra.otf and Ohlfs-Extra-Bold.otf.

Pipeline:

  1. Parse glyphs-extras.txt → list of (name, codepoint, advance, pixel grid)
  2. Load Ohlfs-Light.otf, inject each extra glyph (CFF charstring, cmap entry,
     hmtx entry, glyph order, maxp count), rename to "Ohlfs Extra Regular",
     write Ohlfs-Extra.otf.
  3. Re-load Ohlfs-Extra.otf and run the standard 1-px bold smear over every
     glyph (originals + extras), rename to "Ohlfs Extra Bold", write
     Ohlfs-Extra-Bold.otf.
"""
from __future__ import annotations

from pathlib import Path

from fontTools.ttLib import TTFont

from make_bold import (
    PIXEL,
    attach,
    bold_otf,
    empty_charstring,
    grid_to_runs,
    load_font,
    rename_font,
    runs_to_charstring,
    strip_legacy_bitmap_tables,
    update_cff_top,
)

ROOT = Path("/Users/jason/Developer/ohlfs-bold")
SRC = Path("/Users/jason/Library/Fonts/Ohlfs-Light.otf")
EXTRA_FILES = [
    ROOT / "glyphs-extras.txt",   # all hand-designed extras
]
DST_REGULAR = ROOT / "Ohlfs-Extra.otf"
DST_BOLD = ROOT / "Ohlfs-Extra-Bold.otf"

DEFAULT_ADV = 800


# ---------------------------------------------------------------------------
# Parser for the bitmap text format
# ---------------------------------------------------------------------------

def _parse_grid_row(line: str, line_no: int) -> list[bool]:
    """A grid row is 22 chars representing 11 columns × 2 chars per pixel.

    Cols are -1, 0, 1, ..., 9 (in that order). A pixel is "on" if either of
    its two chars is '#'."""
    code = line.split(";", 1)[0].strip()
    if len(code) != 22:
        raise ValueError(
            f"line {line_no}: grid row must be 22 chars, got {len(code)}: {code!r}"
        )
    cells: list[bool] = []
    for col_idx in range(11):
        a, b = code[col_idx * 2], code[col_idx * 2 + 1]
        cells.append(a == "#" or b == "#")
    return cells


def parse_extras(path: Path) -> list[tuple[str, int | None, int, dict[tuple[int, int], bool]]]:
    """Return list of (name, codepoint, advance, pixel_grid)."""
    out: list[tuple[str, int | None, int, dict[tuple[int, int], bool]]] = []
    lines = path.read_text().splitlines()
    i = 0
    while i < len(lines):
        raw = lines[i]
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            i += 1
            continue
        if not stripped.startswith("glyph "):
            i += 1
            continue

        parts = stripped.split()
        if len(parts) < 3:
            raise ValueError(f"line {i+1}: malformed glyph header: {raw!r}")
        name = parts[1]
        cp_str = parts[2]
        cp: int | None = None
        if cp_str.startswith("U+"):
            cp = int(cp_str[2:], 16)
        elif cp_str != "-":
            raise ValueError(f"line {i+1}: codepoint must be 'U+XXXX' or '-': {cp_str!r}")
        adv = DEFAULT_ADV
        for p in parts[3:]:
            if p.startswith("adv="):
                adv = int(p.split("=", 1)[1])

        # Read 16 grid rows. Skip pure blank/comment lines between them.
        grid: dict[tuple[int, int], bool] = {}
        rows_read = 0
        i += 1
        while rows_read < 16 and i < len(lines):
            rline = lines[i]
            if not rline.strip() or rline.lstrip().startswith("#"):
                i += 1
                continue
            row_cells = _parse_grid_row(rline, i + 1)
            y = 12 - rows_read
            for col_idx, on in enumerate(row_cells):
                col = col_idx - 1   # col_idx 0 → col -1
                if on:
                    grid[(col, y)] = True
            rows_read += 1
            i += 1
        if rows_read != 16:
            raise ValueError(f"glyph {name!r}: expected 16 grid rows, got {rows_read}")
        out.append((name, cp, adv, grid))
    return out


# ---------------------------------------------------------------------------
# Inject parsed glyphs into a loaded font
# ---------------------------------------------------------------------------

def inject_glyphs(font: TTFont, glyphs) -> None:
    top = font["CFF "].cff.topDictIndex[0]
    cs_index = top.CharStrings
    hmtx = font["hmtx"].metrics
    glyph_order = list(font.getGlyphOrder())
    cmap_subtables = [t for t in font["cmap"].tables if t.isUnicode()]

    # Template for private/globalSubrs. Use any existing glyph.
    template = next(iter(cs_index.values()))

    for name, cp, adv, grid in glyphs:
        if name in cs_index.charStrings:
            print(f"  warn: {name!r} already exists; skipping")
            continue

        runs = grid_to_runs(grid) if grid else []
        if runs:
            cs = runs_to_charstring(runs, adv)
            lsb = min(col_start for col_start, _, _ in runs) * PIXEL
        else:
            cs = empty_charstring(adv)
            lsb = 0
        attach(cs, template)

        # CharStrings.__setitem__ only replaces existing entries — to add a
        # new glyph we append to the underlying INDEX, the name map, and the
        # CFF charset (which defines glyph order on save).
        new_idx = len(cs_index.charStringsIndex.items)
        cs_index.charStringsIndex.items.append(cs)
        cs_index.charStrings[name] = new_idx
        top.charset.append(name)

        hmtx[name] = (adv, lsb)
        glyph_order.append(name)
        if cp is not None:
            for sub in cmap_subtables:
                sub.cmap[cp] = name

    font.setGlyphOrder(glyph_order)
    font["maxp"].numGlyphs = len(glyph_order)


# ---------------------------------------------------------------------------
# Mark a font as the "Regular" weight (clears bold flags)
# ---------------------------------------------------------------------------

def mark_regular(font: TTFont, weight_class: int = 400) -> None:
    os2 = font["OS/2"]
    os2.usWeightClass = weight_class
    fs = os2.fsSelection
    fs &= ~(1 << 5)   # clear BOLD
    fs |= 1 << 6      # set REGULAR
    fs &= ~(1 << 0)   # clear ITALIC
    os2.fsSelection = fs

    font["head"].macStyle &= ~(1 << 0)   # clear bold


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------

def build_extra_regular() -> Path:
    print(f"[1/2] Building {DST_REGULAR.name}")
    glyphs: list = []
    for path in EXTRA_FILES:
        parsed = parse_extras(path)
        glyphs.extend(parsed)
        print(f"  parsed {len(parsed)} glyphs from {path.name}")

    font = load_font(SRC)
    inject_glyphs(font, glyphs)

    family = "Ohlfs Extra"
    subfamily = "Regular"
    full = "Ohlfs Extra"
    ps_name = "Ohlfs-Extra"

    update_cff_top(font, ps_name=ps_name, full=full, family=family, weight="Regular")
    rename_font(font, family=family, subfamily=subfamily, full=full, ps_name=ps_name)
    mark_regular(font)
    strip_legacy_bitmap_tables(font)

    DST_REGULAR.parent.mkdir(parents=True, exist_ok=True)
    font.save(str(DST_REGULAR))
    print(f"  wrote {DST_REGULAR} ({DST_REGULAR.stat().st_size} bytes)")
    return DST_REGULAR


def build_extra_bold(src: Path) -> Path:
    print(f"[2/2] Building {DST_BOLD.name}")
    bold_otf(
        src=src,
        dst=DST_BOLD,
        family="Ohlfs Extra",
        subfamily="Bold",
        full="Ohlfs Extra Bold",
        ps_name="Ohlfs-Extra-Bold",
    )
    return DST_BOLD


def main() -> None:
    regular = build_extra_regular()
    build_extra_bold(regular)


if __name__ == "__main__":
    main()
