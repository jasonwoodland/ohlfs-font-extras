#!/usr/bin/env python3
"""Dump every glyph in Ohlfs-Light.otf as an editable ASCII bitmap.

Format per glyph:

    glyph <name> <codepoint or '-'> [adv=1100]
    +------------+        <- top of cell (y=12, above ascender)
    |............|
    |............|        <- 16 rows total
    |....##......|
    |..........  |        <- baseline marker shown after row y=0
    |............|        <- y=-3 row at the bottom
    +------------+

Each row is 12 columns wide, covering pixel x=-1 .. x=10. Column 0 is the
LSB origin. The 4 columns x=-1 and x=8..10 are for overhangs (italics,
combining diacritics, box-drawing extensions). `#` = on pixel, `.` = off.
"""
from __future__ import annotations

from pathlib import Path

from fontTools.ttLib import TTFont
from fontTools.pens.recordingPen import RecordingPen

PIXEL = 100
COL_MIN, COL_MAX = -1, 9            # 11 cols (Light advance is 8px → cols 0..7 + overhang)
ROW_MIN, ROW_MAX = -3, 12           # 16 rows
DEFAULT_ADV = 800                   # Light cell width
SRC = Path("/Users/jason/Library/Fonts/Ohlfs-Light.otf")
OUT = Path("/Users/jason/Developer/ohlfs-bold/glyphs.txt")
MISSING_OUT = Path("/Users/jason/Developer/ohlfs-bold/missing.txt")


def extract_subpaths(charstring):
    pen = RecordingPen()
    charstring.draw(pen)
    subs, cur = [], []
    for op, args in pen.value:
        if op == "moveTo":
            if cur:
                subs.append(cur)
            cur = [args[0]]
        elif op == "lineTo":
            cur.append(args[0])
        elif op in ("closePath", "endPath"):
            if cur:
                subs.append(cur)
            cur = []
    if cur:
        subs.append(cur)
    return [s for s in subs if len(s) >= 3]


def inside(x: float, y: float, subs) -> bool:
    ins = False
    for poly in subs:
        n = len(poly)
        j = n - 1
        for i in range(n):
            xi, yi = poly[i]
            xj, yj = poly[j]
            if ((yi > y) != (yj > y)) and (
                x < (xj - xi) * (y - yi) / (yj - yi) + xi
            ):
                ins = not ins
            j = i
    return ins


def render(charstring) -> list[str]:
    subs = extract_subpaths(charstring)
    rows: list[str] = []
    for r in range(ROW_MAX, ROW_MIN - 1, -1):
        line = ""
        for c in range(COL_MIN, COL_MAX + 1):
            cx = c * PIXEL + PIXEL / 2
            cy = r * PIXEL + PIXEL / 2
            line += "##" if inside(cx, cy, subs) else ".."
        rows.append(line)
    return rows


# Reverse-cmap: glyph name -> codepoint (best one)
def build_reverse_cmap(font: TTFont) -> dict[str, int]:
    rev: dict[str, int] = {}
    for cp, name in font.getBestCmap().items():
        if name not in rev:
            rev[name] = cp
    return rev


def main() -> None:
    font = TTFont(str(SRC))
    cs_index = font["CFF "].cff.topDictIndex[0].CharStrings
    hmtx = font["hmtx"].metrics
    rev = build_reverse_cmap(font)

    out: list[str] = []
    out.append("# Ohlfs glyph source — one glyph per record.")
    out.append("# Grid: 11 cols (x=-1..9) × 16 rows (y=12 top .. y=-3 bottom).")
    out.append("# Default advance is 800 (8 px). Cols 0..7 are the cell; col -1 is")
    out.append("# left overhang (e.g. 'm', 'h'); cols 8..9 are right overhang/diacritics.")
    out.append("# Baseline is between the row labelled 'y=0' and 'y=-1'.")
    out.append("# '#' = on pixel, '.' = off.")
    out.append("#")
    out.append("# Editing rules:")
    out.append("#   - Keep the 'glyph' line intact: name codepoint [adv=N]")
    out.append("#   - Use 'U+XXXX' for an encoded glyph or '-' for un-encoded")
    out.append("#   - 16 grid rows must follow, each 22 chars wide (2 chars per pixel)")
    out.append("#   - Inline ';' comments after a row are ignored on parse")
    out.append("")
    out.append("# col index:  -1 0 1 2 3 4 5 6 7 8 9")
    out.append("#             |  |             |   |")
    out.append("#             overhang  advance |   right overhang")
    out.append("#                       boundary→ col 8")
    out.append("")

    glyph_order = font.getGlyphOrder()

    for name in glyph_order:
        if name == ".notdef":
            continue
        cs = cs_index[name]
        adv, lsb = hmtx[name]
        cp = rev.get(name)
        cp_str = f"U+{cp:04X}" if cp is not None else "-"
        adv_str = f" adv={adv}" if adv != DEFAULT_ADV else ""
        out.append(f"glyph {name} {cp_str}{adv_str}")
        rows = render(cs)
        for r_idx, row in enumerate(rows):
            y = ROW_MAX - r_idx          # y=12 .. y=-3
            tag = ""
            if y == 12:
                tag = "  ; y=12 (top, above ascent)"
            elif y == 11:
                tag = "  ; y=11"
            elif y == 0:
                tag = "  ; y=0 (baseline row — pixels here sit on baseline)"
            elif y == -1:
                tag = "  ; y=-1 (first row below baseline)"
            elif y == -3:
                tag = "  ; y=-3 (bottom)"
            out.append(f"  {row}{tag}")
        out.append("")

    OUT.write_text("\n".join(out))
    print(f"Wrote {OUT} ({len(glyph_order)-1} glyphs, {OUT.stat().st_size} bytes)")

    write_missing_report(font)


def write_missing_report(font: TTFont) -> None:
    """Write a coverage report of common Unicode ranges relevant to a terminal font."""
    cmap = font.getBestCmap()
    have = set(cmap.keys())

    # (label, start, end_inclusive)
    ranges = [
        ("ASCII",                                0x0020, 0x007E),
        ("Latin-1 Supplement",                   0x00A0, 0x00FF),
        ("Latin Extended-A",                     0x0100, 0x017F),
        ("Latin Extended-B",                     0x0180, 0x024F),
        ("IPA Extensions",                       0x0250, 0x02AF),
        ("Spacing Modifier Letters",             0x02B0, 0x02FF),
        ("Combining Diacriticals",               0x0300, 0x036F),
        ("Greek and Coptic",                     0x0370, 0x03FF),
        ("Cyrillic",                             0x0400, 0x04FF),
        ("General Punctuation",                  0x2000, 0x206F),
        ("Superscripts and Subscripts",          0x2070, 0x209F),
        ("Currency Symbols",                     0x20A0, 0x20CF),
        ("Letterlike Symbols",                   0x2100, 0x214F),
        ("Number Forms",                         0x2150, 0x218F),
        ("Arrows",                               0x2190, 0x21FF),
        ("Mathematical Operators",               0x2200, 0x22FF),
        ("Miscellaneous Technical",              0x2300, 0x23FF),
        ("Box Drawing",                          0x2500, 0x257F),
        ("Block Elements",                       0x2580, 0x259F),
        ("Geometric Shapes",                     0x25A0, 0x25FF),
        ("Miscellaneous Symbols",                0x2600, 0x26FF),
        ("Dingbats",                             0x2700, 0x27BF),
        ("Supplemental Arrows-A",                0x27F0, 0x27FF),
        ("Supplemental Arrows-B",                0x2900, 0x297F),
        ("Misc Mathematical Symbols-B",          0x2980, 0x29FF),
        ("Supplemental Math Operators",          0x2A00, 0x2AFF),
        ("Misc Symbols and Arrows",              0x2B00, 0x2BFF),
        ("Powerline Symbols (PUA)",              0xE0A0, 0xE0B7),
        ("Nerd Font Devicons (PUA)",             0xE700, 0xE7C5),
        ("Nerd Font FontAwesome (PUA)",          0xF000, 0xF2E0),
        ("Alphabetic Presentation Forms",        0xFB00, 0xFB4F),
    ]

    lines: list[str] = []
    lines.append("# Coverage report — Ohlfs-Light.otf")
    lines.append("# '✓' present, '·' missing.")
    lines.append("")

    summary: list[tuple[str, int, int]] = []
    for label, start, end in ranges:
        total = end - start + 1
        present = sum(1 for cp in range(start, end + 1) if cp in have)
        summary.append((label, present, total))

    width = max(len(s[0]) for s in summary)
    lines.append("Summary")
    lines.append("-------")
    for label, present, total in summary:
        bar_total = 30
        filled = round(bar_total * present / total) if total else 0
        bar = "█" * filled + "░" * (bar_total - filled)
        lines.append(f"  {label.ljust(width)}  {bar}  {present:4d}/{total:<4d}")

    lines.append("")
    lines.append("Per-block detail")
    lines.append("================")
    for label, start, end in ranges:
        total = end - start + 1
        present = sum(1 for cp in range(start, end + 1) if cp in have)
        if present == total:
            lines.append(f"\n## {label}  U+{start:04X}–U+{end:04X}  (complete)")
            continue
        lines.append(f"\n## {label}  U+{start:04X}–U+{end:04X}  ({present}/{total})")
        # Group by row of 16
        for row_start in range(start & ~0xF, end + 1, 16):
            row_label = f"U+{row_start:04X}: "
            cells = []
            for cp in range(row_start, row_start + 16):
                if cp < start or cp > end:
                    cells.append("  ")
                    continue
                if cp in have:
                    try:
                        ch = chr(cp)
                        if ch.isprintable() and not ch.isspace():
                            cells.append(f" {ch}")
                        else:
                            cells.append(" ✓")
                    except ValueError:
                        cells.append(" ✓")
                else:
                    cells.append(" ·")
            lines.append(row_label + "".join(cells))

    lines.append("")
    lines.append("Recommended additions for a terminal/programming font")
    lines.append("=====================================================")
    recs = [
        ("Box drawing — single + double + heavy lines",   range(0x2500, 0x2580)),
        ("Block elements — shading + half-blocks",        range(0x2580, 0x25A0)),
        ("Triangles + arrows for Powerline",              [0xE0A0, 0xE0A1, 0xE0A2,
                                                           0xE0B0, 0xE0B1, 0xE0B2, 0xE0B3]),
        ("Basic arrows (← ↑ → ↓ ↔ ↕)",                    [0x2190, 0x2191, 0x2192,
                                                           0x2193, 0x2194, 0x2195]),
        ("Geometric shapes (▶ ◀ ● ○ ■ □)",                [0x25B6, 0x25C0, 0x25CF,
                                                           0x25CB, 0x25A0, 0x25A1]),
        ("Math ops (≠ ≤ ≥ ≈ ∞ ∑ ∫)",                     [0x2260, 0x2264, 0x2265,
                                                           0x2248, 0x221E, 0x2211, 0x222B]),
    ]
    for label, codepoints in recs:
        cps = list(codepoints)
        missing = [cp for cp in cps if cp not in have]
        lines.append(f"\n  {label}")
        lines.append(f"    {len(missing)}/{len(cps)} missing")
        if missing:
            preview = ", ".join(f"U+{cp:04X}" for cp in missing[:8])
            if len(missing) > 8:
                preview += f", … (+{len(missing) - 8} more)"
            lines.append(f"    {preview}")

    MISSING_OUT.write_text("\n".join(lines))
    print(f"Wrote {MISSING_OUT}")


if __name__ == "__main__":
    main()
