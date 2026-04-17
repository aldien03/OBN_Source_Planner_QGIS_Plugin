"""
SPS column layout specification.

SPS (Shell Point Set) files are fixed-width text files with columns at
specific character positions. Multiple revisions and vendor variants exist;
this module declares a data-driven spec so new formats can be added by
registering a new SpsColumnSpec instance rather than changing code.

Verified formats (as of Phase 3):
- SPS_1_0:          1990 SEG SPS001 format. H00 declares 'SPS001,01.10.90'.
                    Seen in: Production_SX_Preplot_Valhall_1.1.s01 (TGS variant).
- SPS_2_1:          Shell-published SPS 2.1 standard. Cleanly parses most
                    modern files (PXGEO .s01, SAE Heimdal .sps — both declare
                    'SPS 2.1' in H00).
- SPS_2_1_DIRECTION: SPS 2.1 with an extra 'previous shooting direction'
                    column at positions 80-86.
                    Seen in: D1v1_MartinLindge_260410_sailline.sps.

Adding a new vendor variant: construct an SpsColumnSpec and append to
SPS_SPECS. If the variant has columns at positions > 66 that aren't among
the mandatory four fields, you usually do NOT need a new spec — SPS_2_1
already ignores such columns.
"""

from dataclasses import dataclass, field
from typing import Callable, Optional


def _parse_numeric_id(s: str) -> int:
    """Parse line/SP identifiers that may be decimal-formatted.

    Martin Linge writes '2431.0'; PXGEO writes '1006'. Both are valid
    SPS line identifiers. int() alone would fail on the first; float()
    alone would accept junk like '1.5' which is not a valid line id.
    """
    s = s.strip()
    try:
        return int(s)
    except ValueError:
        return int(float(s))  # raises ValueError if junk — caller catches


@dataclass(frozen=True)
class SpsColumnSpec:
    """Declarative column layout for a fixed-width SPS variant.

    Slices are 0-indexed Python slice objects. Widths should include a
    bit of padding when the field may be right-justified with spaces,
    since all fields are .strip()'d before parsing.

    Mandatory fields: line_num, sp, easting, northing.
    Optional fields default to None (not present in this variant).
    """
    name: str
    description: str
    line_num: slice
    sp: slice
    easting: slice
    northing: slice
    depth: Optional[slice] = None
    direction: Optional[slice] = None       # previous shooting direction, degrees
    source_code: Optional[slice] = None     # e.g. '1A2' for source 1, airgun 2
    min_length: int = 65                    # lines shorter than this are skipped
    encoding: str = "latin-1"
    header_markers: tuple = ("H",)          # lines starting with any of these are headers
    record_markers: tuple = ("S",)          # lines starting with any of these are data
    id_parser: Callable[[str], int] = field(default=_parse_numeric_id)


# --- Known specs ---------------------------------------------------------

SPS_1_0 = SpsColumnSpec(
    name="SPS 1.0",
    description=(
        "Original SEG SPS format (1990). H00 typically contains "
        "'SPS001,01.10.90' or similar. Uses 4-character line/SP fields, "
        "unlike SPS 2.1's 10-character fields."
    ),
    line_num=slice(1, 5),       # e.g. '1189' (4 chars, no decimal)
    sp=slice(21, 25),           # e.g. '1588'
    source_code=slice(25, 28),  # e.g. '1A1'
    easting=slice(47, 55),      # e.g. '519081.0'
    northing=slice(56, 65),     # e.g. '6234817.9'
    depth=slice(68, 71),        # e.g. '0.0'
    min_length=65,
)

SPS_2_1 = SpsColumnSpec(
    name="SPS 2.1",
    description=(
        "Shell-published SPS 2.1 standard. H00 declares 'SPS 2.1'. "
        "Mandatory fields at canonical positions. Known to parse Martin Linge, "
        "PXGEO (.s01 headerless variant), and SAE Heimdal base data. Any "
        "vendor-specific extra columns beyond position 65 are ignored."
    ),
    line_num=slice(1, 11),      # 10-char right-justified (int or decimal)
    sp=slice(11, 21),           # 10-char right-justified
    source_code=slice(23, 26),  # e.g. '1A2'
    easting=slice(46, 56),      # 10-char right-justified
    northing=slice(56, 66),     # 10-char right-justified
    depth=slice(66, 72),        # 6-char
    min_length=65,
)

SPS_2_1_DIRECTION = SpsColumnSpec(
    name="SPS 2.1 + direction",
    description=(
        "SPS 2.1 with 'previous shooting direction' (degrees, math or "
        "compass convention — caller decides) in a vendor extension at "
        "positions 80-86. Verified against Martin Linge "
        "D1v1_MartinLindge_260410_sailline.sps where values are 76.8 / 256.8 "
        "(line pair alternating direction by 180°)."
    ),
    line_num=slice(1, 11),
    sp=slice(11, 21),
    source_code=slice(23, 26),
    easting=slice(46, 56),
    northing=slice(56, 66),
    depth=slice(66, 72),
    direction=slice(79, 86),    # 7 chars — handles ' 76.8' and '256.8'
    min_length=85,
)


# Registry used by detect_spec(). Order matters: if two specs parse the same
# file cleanly, the FIRST match wins. Put more-specific specs first.
SPS_SPECS: dict = {
    SPS_2_1_DIRECTION.name: SPS_2_1_DIRECTION,
    SPS_2_1.name:           SPS_2_1,
    SPS_1_0.name:           SPS_1_0,
}
