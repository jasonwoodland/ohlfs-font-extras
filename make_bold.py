#!/usr/bin/env python3
"""Generate Ohlfs-Bold.otf from Ohlfs-Medium.otf by smearing each glyph 1 pixel right.

The Ohlfs OTF contains rectilinear pixel outlines on a 100-unit grid (UPM 1900).
We recover the bitmap of each glyph, OR it with a 1-pixel right shift, and
re-emit the outline as a set of axis-aligned rectangles (one per horizontal run).
"""
from __future__ import annotations

import sys
from pathlib import Path

from fontTools.ttLib import TTFont
from fontTools.pens.recordingPen import RecordingPen
from fontTools.pens.t2CharStringPen import T2CharStringPen

PIXEL = 100  # font units per pixel
SHIFT = PIXEL  # bold smear: 1 pixel to the right

SRC = Path("/Users/jason/Library/Fonts/Ohlfs-Light.otf")
DST = Path("/Users/jason/Developer/ohlfs-bold/Ohlfs-Bold.otf")


def extract_subpaths(charstring) -> list[list[tuple[int, int]]]:
    """Return list of closed subpaths (each a list of (x, y) points)."""
    pen = RecordingPen()
    charstring.draw(pen)
    subpaths: list[list[tuple[int, int]]] = []
    current: list[tuple[int, int]] = []
    for op, args in pen.value:
        if op == "moveTo":
            if current:
                subpaths.append(current)
            current = [args[0]]
        elif op == "lineTo":
            current.append(args[0])
        elif op == "closePath":
            if current:
                subpaths.append(current)
            current = []
        elif op == "endPath":
            if current:
                subpaths.append(current)
            current = []
        else:
            raise ValueError(f"Unexpected op {op} in pixel-font glyph")
    if current:
        subpaths.append(current)
    return subpaths


def point_in_subpaths(x: float, y: float, subpaths: list[list[tuple[int, int]]]) -> bool:
    """Even-odd point-in-polygon over union of all subpaths.

    Even-odd works correctly for CFF pixel glyphs whose outer/inner subpaths
    are wound oppositely (which they are in Ohlfs)."""
    inside = False
    for poly in subpaths:
        n = len(poly)
        if n < 2:
            continue
        j = n - 1
        for i in range(n):
            xi, yi = poly[i]
            xj, yj = poly[j]
            if ((yi > y) != (yj > y)) and (x < (xj - xi) * (y - yi) / (yj - yi) + xi):
                inside = not inside
            j = i
    return inside


def glyph_bbox_pixels(subpaths) -> tuple[int, int, int, int] | None:
    if not subpaths or all(len(p) == 0 for p in subpaths):
        return None
    xs = [p[0] for sp in subpaths for p in sp]
    ys = [p[1] for sp in subpaths for p in sp]
    return (min(xs) // PIXEL, min(ys) // PIXEL, max(xs) // PIXEL, max(ys) // PIXEL)


def rasterize(subpaths, bbox) -> dict[tuple[int, int], bool]:
    """Return a dict mapping (col, row) -> True for filled pixel cells."""
    x0, y0, x1, y1 = bbox
    grid: dict[tuple[int, int], bool] = {}
    for col in range(x0, x1):
        for row in range(y0, y1):
            cx = col * PIXEL + PIXEL / 2
            cy = row * PIXEL + PIXEL / 2
            if point_in_subpaths(cx, cy, subpaths):
                grid[(col, row)] = True
    return grid


def bold_grid(grid: dict[tuple[int, int], bool]) -> dict[tuple[int, int], bool]:
    """Return grid OR'd with itself shifted +1 in x."""
    out: dict[tuple[int, int], bool] = dict(grid)
    for (col, row) in grid:
        out[(col + 1, row)] = True
    return out


def grid_to_runs(grid: dict[tuple[int, int], bool]) -> list[tuple[int, int, int]]:
    """Merge filled pixels into horizontal runs per row.

    Returns list of (col_start, col_end_exclusive, row).
    """
    if not grid:
        return []
    rows: dict[int, list[int]] = {}
    for (col, row) in grid:
        rows.setdefault(row, []).append(col)
    runs: list[tuple[int, int, int]] = []
    for row, cols in rows.items():
        cols.sort()
        run_start = cols[0]
        prev = cols[0]
        for c in cols[1:]:
            if c == prev + 1:
                prev = c
            else:
                runs.append((run_start, prev + 1, row))
                run_start = c
                prev = c
        runs.append((run_start, prev + 1, row))
    return runs


def runs_to_charstring(runs, width: int):
    """Build a Type 2 CharString from a list of axis-aligned rectangles."""
    pen = T2CharStringPen(width, glyphSet=None)
    for col_start, col_end, row in runs:
        x0 = col_start * PIXEL
        x1 = col_end * PIXEL
        y0 = row * PIXEL
        y1 = (row + 1) * PIXEL
        # CCW rectangle: bottom-left, bottom-right, top-right, top-left
        pen.moveTo((x0, y0))
        pen.lineTo((x1, y0))
        pen.lineTo((x1, y1))
        pen.lineTo((x0, y1))
        pen.closePath()
    return pen.getCharString()


def empty_charstring(width: int):
    pen = T2CharStringPen(width, glyphSet=None)
    return pen.getCharString()


def rename_font(font: TTFont, family="Ohlfs", subfamily="Bold",
                full="Ohlfs Bold", ps_name="Ohlfs-Bold") -> None:
    name_table = font["name"]
    # Rewrite all common name records across all platforms/encodings/languages.
    # nameID: 1=family, 2=subfamily, 3=unique, 4=full, 6=psname,
    # 16=preferred family, 17=preferred subfamily.
    target = {
        1: family,
        2: subfamily,
        3: f"{family} {subfamily} 1.0",
        4: full,
        6: ps_name,
        16: family,
        17: subfamily,
    }
    for rec in list(name_table.names):
        if rec.nameID in target:
            try:
                rec.string = target[rec.nameID].encode(rec.getEncoding())
            except (UnicodeEncodeError, LookupError):
                rec.string = target[rec.nameID].encode("utf-16-be")
    # Ensure the canonical Win/Unicode records exist for IDs we care about.
    for nid, val in target.items():
        # Mac Roman
        name_table.setName(val, nid, 1, 0, 0)
        # Windows Unicode BMP English
        name_table.setName(val, nid, 3, 1, 0x409)


def mark_bold(font: TTFont) -> None:
    os2 = font["OS/2"]
    os2.usWeightClass = 700
    # fsSelection: bit 0 = ITALIC, bit 5 = BOLD, bit 6 = REGULAR, bit 7 = USE_TYPO_METRICS
    fs = os2.fsSelection
    fs |= 1 << 5  # BOLD
    fs &= ~(1 << 6)  # clear REGULAR
    os2.fsSelection = fs

    head = font["head"]
    # macStyle: bit 0 = bold
    head.macStyle |= 1 << 0


def patch_os2_version(src_path: Path) -> bytes | None:
    """Some Ohlfs OTFs claim OS/2 v5 but truncate the v5-only trailer.
    Read raw bytes and downgrade the version to 4 if so. Returns patched bytes
    (or None if no patch needed)."""
    font = TTFont(str(src_path), lazy=True)
    raw = font.reader["OS/2"]
    font.close()
    if len(raw) >= 2 and int.from_bytes(raw[:2], "big") == 5 and len(raw) < 100:
        return b"\x00\x04" + raw[2:]
    return None


def attach(new_cs, template_cs):
    """Copy private + globalSubrs from a template charstring onto a new one."""
    new_cs.private = template_cs.private
    new_cs.globalSubrs = template_cs.globalSubrs
    return new_cs


def load_font(src_path: Path) -> TTFont:
    """Load an Ohlfs OTF, working around the OS/2 v5 trailer bug."""
    font = TTFont(str(src_path))
    os2_patch = patch_os2_version(src_path)
    if os2_patch is not None:
        from fontTools.ttLib.tables.O_S_2f_2 import table_O_S_2f_2
        os2 = table_O_S_2f_2(tag="OS/2")
        os2.decompile(os2_patch, font)
        font["OS/2"] = os2
    return font


def apply_bold_smear(font: TTFont) -> None:
    """Replace every glyph's outline with a 1-pixel right-shift OR of itself."""
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
        bolded = bold_grid(grid)
        runs = grid_to_runs(bolded)
        cs_index[name] = attach(runs_to_charstring(runs, adv), cs)
        lsb = min(col_start for col_start, _, _ in runs) * PIXEL if runs else 0
        hmtx[name] = (adv, lsb)


def strip_legacy_bitmap_tables(font: TTFont) -> None:
    """Remove Apple/legacy bitmap tables that reference the original outlines."""
    for tag in ("bdat", "bloc", "BDF ", "FFTM"):
        if tag in font:
            del font[tag]


def update_cff_top(font: TTFont, ps_name: str, full: str, family: str,
                   weight: str) -> None:
    cff = font["CFF "].cff
    top = cff.topDictIndex[0]
    cff.fontNames[0] = ps_name
    if hasattr(top, "FullName"):
        top.FullName = full
    if hasattr(top, "FamilyName"):
        top.FamilyName = family
    if hasattr(top, "Weight"):
        top.Weight = weight


def bold_otf(src: Path, dst: Path,
             family: str = "Ohlfs", subfamily: str = "Bold",
             full: str | None = None, ps_name: str | None = None) -> None:
    """Read `src`, apply the bold smear and bold-weight metadata, write to `dst`."""
    full = full or f"{family} {subfamily}"
    ps_name = ps_name or f"{family.replace(' ', '')}-{subfamily}"
    font = load_font(src)
    apply_bold_smear(font)
    update_cff_top(font, ps_name, full, family, subfamily)
    rename_font(font, family=family, subfamily=subfamily, full=full, ps_name=ps_name)
    mark_bold(font)
    strip_legacy_bitmap_tables(font)
    dst.parent.mkdir(parents=True, exist_ok=True)
    font.save(str(dst))
    print(f"Wrote {dst} ({dst.stat().st_size} bytes)")


def main() -> None:
    bold_otf(SRC, DST, family="Ohlfs", subfamily="Bold",
             full="Ohlfs Bold", ps_name="Ohlfs-Bold")


if __name__ == "__main__":
    main()
