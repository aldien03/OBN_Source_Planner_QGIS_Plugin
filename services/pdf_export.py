"""
48-hour Lookahead PDF export — Phase 17.

Two layers of public API:

1. Pure-Python helpers (no QGIS): `compute_output_filename`,
   `render_header_text`, `LookaheadRow`, `PdfExportConfig`,
   `sanitize_filename_fragment`. These are unit-tested in
   `test/test_pdf_export.py` without a QGIS runtime.

2. QGIS-dependent helpers: `rows_from_optimized_path_layer`,
   `build_lookahead_layout`, `export_pdf`. These are smoke-tested in
   17b against the live plugin.

Design notes:
- Optimized_Path carries timing + sequence; Generated_Survey_Lines
  carries Operation/FGSP/LGSP. Join on (LineNum, SubLineId).
  Optimized_Path.SubLineId was added in 17a (_visualize_optimized_path
  in obn_planner_dockwidget.py).
- Page-1 map layers + extent are supplied by the preview dialog,
  not derived automatically here.
"""
from __future__ import annotations

import glob
import os
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional, Tuple


# --- Filename logic ---------------------------------------------------------

_FILENAME_RE = re.compile(
    r"^(\d{4}_\d{2}_\d{2}) - (.+)_48hrLookahead_V(\d+)\.(\d+)\.pdf$"
)
_ILLEGAL_FILENAME_CHARS_RE = re.compile(r'[\\/:*?"<>|]')


def sanitize_filename_fragment(text: str) -> str:
    """Strip filesystem-illegal characters from a survey/vessel/project
    name so it can be interpolated into a filename. Empty / whitespace
    input -> 'Survey' as a safe fallback."""
    cleaned = _ILLEGAL_FILENAME_CHARS_RE.sub("_", text or "").strip()
    return cleaned or "Survey"


def compute_output_filename(
    date_str: str,
    survey_name: str,
    output_dir: str,
) -> str:
    """Return the next version slot for this (date, survey) pair.

    First export in a day/survey -> V1.0. Subsequent exports bump the
    minor version: V1.1, V1.2, ... V1.n. The major version is fixed at
    1 for now; a future phase may add an explicit 'new major version'
    button if users want V2.0/V3.0 semantics.

    Arguments:
      date_str: "YYYY_MM_DD" (from QDate.currentDate().toString("yyyy_MM_dd")).
      survey_name: user-entered survey name; sanitized internally.
      output_dir: filesystem path to scan for existing PDFs.
    """
    survey = sanitize_filename_fragment(survey_name)
    pattern = f"{date_str} - {survey}_48hrLookahead_V*.pdf"
    existing = glob.glob(os.path.join(output_dir, pattern))
    max_minor = -1
    for p in existing:
        m = _FILENAME_RE.match(os.path.basename(p))
        if m and m.group(1) == date_str and m.group(2) == survey:
            if int(m.group(3)) == 1:
                max_minor = max(max_minor, int(m.group(4)))
    next_minor = max_minor + 1 if max_minor >= 0 else 0
    return f"{date_str} - {survey}_48hrLookahead_V1.{next_minor}.pdf"


# --- Header template --------------------------------------------------------

_PLACEHOLDER_KEYS = ("vessel", "project", "hours", "date", "survey")


def render_header_text(
    template: str,
    *,
    vessel: str = "",
    project: str = "",
    hours: int = 48,
    date_str: str = "",
    survey: str = "",
) -> str:
    """Expand {vessel}, {project}, {hours}, {date}, {survey} in a
    user-supplied template. Unknown placeholders are left literal so
    typos in the template surface visibly in the PDF rather than
    raising an exception at render time."""
    if not template:
        return ""
    values = {
        "vessel": vessel,
        "project": project,
        "hours": str(hours),
        "date": date_str,
        "survey": survey,
    }
    out = template
    for key in _PLACEHOLDER_KEYS:
        out = out.replace("{" + key + "}", values[key])
    return out


# --- Row model --------------------------------------------------------------

@dataclass(frozen=True)
class LookaheadRow:
    """One row of the sequence-table on the PDF, representing a single
    line or sub-line in acquisition order."""
    seq_order: int          # raw SeqOrder from Optimized_Path (includes turns)
    line_seq: int           # 1-based line-only acquisition counter (1,2,3,...)
    line_num: int
    sub_line_id: Optional[int]
    operation: str          # Production / Test / Reshoot / Infill
    fgsp: int
    lgsp: int
    heading_deg: float
    eta_sol: datetime
    eta_eol: datetime
    day_month: str          # "dd-MMM" (locale-independent English month abbr)


# --- Config -----------------------------------------------------------------

@dataclass(frozen=True)
class PdfExportConfig:
    survey_name: str
    vessel_name: str
    project_name: str
    hours: int = 48
    header_template: str = "{vessel} {hours}Hrs Look Ahead \u2014 {project}"
    logo_vessel_path: Optional[str] = None
    logo_company_path: Optional[str] = None
    logo_client_path: Optional[str] = None
    show_north_arrow: bool = True
    show_scale_bar: bool = True
    show_legend: bool = True
    # Phase 17d.2: grid_style supersedes the bool show_coord_grid.
    # One of "off", "light" (default), "normal". Kept show_coord_grid
    # alongside for back-compat with 17b code paths that haven't been
    # migrated; when grid_style != "off" it overrides show_coord_grid.
    show_coord_grid: bool = True
    grid_style: str = "light"
    # Start value for the PDF table's Seq column; matches the dock's
    # "First Line Seq." spinbox so the PDF aligns with the Edit Plan
    # dialog's sequence numbers (e.g. 1000, 1001, 1002, ...).
    start_sequence_number: int = 1
    # {layer_id: display_name} — applied to the legend on the map page
    # without mutating the main project's layer tree.
    layer_display_names: dict = field(default_factory=dict)
    # Phase 17d.2: legend group-heading overrides.
    # {group_node_name: display_name_or_empty}. Empty-string value
    # flattens the group (drops the heading, keeps children).
    group_display_names: dict = field(default_factory=dict)
    # Phase 17d.3: per-layer opt-out from the legend (while staying
    # visible on the map). Set of layer_id strings.
    hidden_from_legend: set = field(default_factory=set)
    # Phase 17d.5: explicit legend row order as a list of layer_ids.
    # Empty list = use the project layer tree's native order.
    legend_order: list = field(default_factory=list)


# --- QGIS-dependent helpers -------------------------------------------------
#
# Imported lazily so that services/pdf_export.py is importable in a
# pure-Python test runner without QGIS installed.


def _qgis_core():
    from qgis import core as qgis_core  # type: ignore
    return qgis_core


def _place(item, qc, x_mm: float, y_mm: float, w_mm: float, h_mm: float):
    """Move+resize a layout item in millimetres.

    Avoids QgsLayoutRect (not exposed in all PyQGIS builds) by using
    attemptMove(QgsLayoutPoint) + attemptResize(QgsLayoutSize) — the
    stable public API across QGIS 3.x.
    """
    mm = qc.QgsUnitTypes.LayoutMillimeters
    item.attemptMove(qc.QgsLayoutPoint(x_mm, y_mm, mm))
    item.attemptResize(qc.QgsLayoutSize(w_mm, h_mm, mm))


def _place_logo_centered(layout, qc, path, *, slot_x: float, slot_y: float,
                         slot_w: float, slot_h: float):
    """Place a logo image centered in its slot, preserving aspect ratio.

    Phase 17d.2: all logos go through this helper so the three brand
    slots (vessel / company / client) share a single sizing policy.
    QgsLayoutItemPicture.Zoom preserves the image's aspect ratio and
    fits it inside the slot — narrower images appear centered
    horizontally, shorter images appear centered vertically. No
    stretching. Missing / invalid paths silently skip.
    """
    if not path or not os.path.isfile(path):
        return None
    pic = qc.QgsLayoutItemPicture(layout)
    pic.setPicturePath(path)
    try:
        pic.setResizeMode(qc.QgsLayoutItemPicture.Zoom)
    except AttributeError:
        pass
    try:
        pic.setPictureAnchor(qc.QgsLayoutItemPicture.MiddleFrame)
    except AttributeError:
        pass
    layout.addLayoutItem(pic)
    _place(pic, qc, slot_x, slot_y, slot_w, slot_h)
    return pic


_MONTH_ABBR_EN = (
    "Jan", "Feb", "Mar", "Apr", "May", "Jun",
    "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
)


def _format_day_month(dt: datetime) -> str:
    return f"{dt.day:02d}-{_MONTH_ABBR_EN[dt.month - 1]}"


def _qdt_to_datetime(value) -> Optional[datetime]:
    """Accept either a python datetime or a QDateTime and return a
    python datetime. None-safe."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    to_py = getattr(value, "toPyDateTime", None)
    if to_py is not None:
        return to_py()
    return None


def _read_int(feature, field_name):
    try:
        v = feature[field_name]
    except (KeyError, IndexError):
        return None
    if v is None:
        return None
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def _read_str(feature, field_name, default=""):
    try:
        v = feature[field_name]
    except (KeyError, IndexError):
        return default
    if v is None:
        return default
    return str(v)


def _read_float(feature, field_name):
    try:
        v = feature[field_name]
    except (KeyError, IndexError):
        return 0.0
    if v is None:
        return 0.0
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def rows_from_optimized_path_layer(
    optimized_path_layer,
    generated_lines_layer,
    start_sequence_number: int = 1,
) -> List[LookaheadRow]:
    """Read Optimized_Path line-features in SeqOrder and join
    Generated_Survey_Lines on (LineNum, SubLineId) to pull
    Operation/FGSP/LGSP.

    `start_sequence_number` sets the first value of the line_seq field
    (matches the dock's First Line Seq. spinbox and the Edit Plan
    dialog's seq numbering).

    Fallback rules when a join misses:
    - If SubLineId is NULL on the Optimized_Path feature, look up by
      LineNum alone; if multiple sub-lines exist, use the lowest
      SubLineId (logs as a caller warning opportunity).
    - If no match at all, row is skipped — simulated line that has no
      corresponding row in Generated_Survey_Lines is not something we
      can describe in the PDF.
    """
    gen_by_key = {}
    gen_by_line = {}
    for f in generated_lines_layer.getFeatures():
        ln = _read_int(f, "LineNum")
        sl = _read_int(f, "SubLineId")
        if ln is None:
            continue
        op = _read_str(f, "Operation", default="Production")
        fg = _read_int(f, "FGSP") or 0
        lg = _read_int(f, "LGSP") or 0
        entry = (op, fg, lg)
        if sl is not None:
            gen_by_key[(ln, sl)] = entry
        gen_by_line.setdefault(ln, []).append((sl if sl is not None else 0, entry))

    opt_features = [
        f for f in optimized_path_layer.getFeatures()
        if _read_str(f, "SegmentType") == "Line"
    ]
    opt_features.sort(key=lambda f: _read_int(f, "SeqOrder") or 0)

    rows: List[LookaheadRow] = []
    line_counter = int(start_sequence_number) - 1
    for f in opt_features:
        ln = _read_int(f, "LineNum")
        sl = _read_int(f, "SubLineId")
        if ln is None:
            continue

        entry = None
        if sl is not None:
            entry = gen_by_key.get((ln, sl))
        if entry is None:
            candidates = gen_by_line.get(ln) or []
            if candidates:
                candidates.sort(key=lambda t: t[0])
                entry = candidates[0][1]
        if entry is None:
            continue
        op, fg, lg = entry

        eta_sol = _qdt_to_datetime(f["StartTime"])
        eta_eol = _qdt_to_datetime(f["EndTime"])
        if eta_sol is None or eta_eol is None:
            continue

        line_counter += 1
        rows.append(LookaheadRow(
            seq_order=_read_int(f, "SeqOrder") or 0,
            line_seq=line_counter,
            line_num=ln,
            sub_line_id=sl,
            operation=op,
            fgsp=fg,
            lgsp=lg,
            heading_deg=_read_float(f, "Heading"),
            eta_sol=eta_sol,
            eta_eol=eta_eol,
            day_month=_format_day_month(eta_sol),
        ))

    return rows


# --- Layout assembly --------------------------------------------------------

_A4_LANDSCAPE_W_MM = 297.0
_A4_LANDSCAPE_H_MM = 210.0
# Phase 17d.2: title band shrunk 26 -> 18 so ~8 mm returns to the
# map body. Date moves out of the header into the footer (already
# says "Generated <date>"), avoiding the need for a header-row date
# slot that competed with the logos.
_TITLE_BAND_H_MM = 18.0
_MARGIN_MM = 10.0
_LOGO_SLOT_W_MM = 28.0
_LOGO_SLOT_H_MM = 14.0   # 14 mm slot inside an 18 mm band leaves 2 mm top + 2 mm bottom
_LEFT_MAP_GUTTER_MM = 18.0   # room for grid annotations on the left
_RIGHT_LEGEND_GUTTER_MM = 60.0

# (display_name, row_attribute, width_mm, align) — align: 'L' left, 'C' center, 'R' right.
# Phase 17d.1: all columns center-aligned per user feedback ("Just
# formatting. Make it center."). Sub-line identity is implicit in the
# FGSP/LGSP pair — Line column stays a bare LineNum ("2495", not
# "2495-1") so the chief does not see duplicated sub-line notation.
_TABLE_COLUMNS = (
    ("Seq",         "line_seq",    16.0, "C"),
    ("Line",        "line_num",    22.0, "C"),
    ("Operation",   "operation",   30.0, "C"),
    ("FGSP",        "fgsp",        22.0, "C"),
    ("LGSP",        "lgsp",        22.0, "C"),
    ("HDG\u00b0",   "heading_deg", 20.0, "C"),
    ("ETA SOL",     "eta_sol",     28.0, "C"),
    ("ETA EOL",     "eta_eol",     28.0, "C"),
    ("Day/Month",   "day_month",   26.0, "C"),
)


_HALIGN = {"L": 0x01, "R": 0x02, "C": 0x04}   # Qt.AlignLeft/Right/HCenter
_VALIGN_CENTER = 0x80                          # Qt.AlignVCenter


def _cell_text(row: LookaheadRow, key: str) -> str:
    if key == "line_seq":
        return str(row.line_seq)
    if key == "line_num":
        # Phase 17d.1: always bare LineNum. Do NOT append sub_line_id.
        return str(row.line_num)
    if key == "heading_deg":
        return f"{row.heading_deg:.0f}"
    if key in ("eta_sol", "eta_eol"):
        dt: datetime = getattr(row, key)
        return dt.strftime("%H:%M")
    return str(getattr(row, key))


def build_lookahead_layout(
    project,
    visible_layers: list,
    map_extent,
    rows: List[LookaheadRow],
    config: PdfExportConfig,
    date_str: str,
    map_crs=None,
):
    """Build a QgsPrintLayout for the 48h lookahead PDF.

    Page 1 = overview map (caller supplies visible_layers + extent from
             the preview dialog).
    Page 2+ = 9-column sequence table, auto-paginated.

    The layout is owned by the caller; the caller is responsible for
    passing it to `export_pdf`.
    """
    qc = _qgis_core()

    layout = qc.QgsPrintLayout(project)
    layout.initializeDefaults()
    layout.setName("OBN Planner \u2014 48h Lookahead")

    mm = qc.QgsUnitTypes.LayoutMillimeters
    page_collection = layout.pageCollection()
    page_collection.page(0).setPageSize(
        qc.QgsLayoutSize(_A4_LANDSCAPE_W_MM, _A4_LANDSCAPE_H_MM, mm)
    )

    header_text = render_header_text(
        config.header_template,
        vessel=config.vessel_name,
        project=config.project_name,
        hours=config.hours,
        date_str=date_str,
        survey=config.survey_name,
    )

    _add_title_band(layout, page_index=0, header_text=header_text,
                    date_str=date_str, config=config)
    _add_map_item(layout, page_index=0, layers=visible_layers,
                  extent=map_extent, config=config, map_crs=map_crs)

    _add_table_pages(layout, rows=rows, header_text=header_text,
                     date_str=date_str, config=config)

    # Add a footer to every page — includes any pages auto-created by
    # the manual-table's ExtendToNextPage. Phase 17d.6: hardcode the
    # page count directly in each footer text instead of relying on
    # [% @layout_pagecount %] — the expression rendered literally in
    # 3.34 / 3.40 live tests, leaving "Page 1 of" truncated.
    try:
        total_pages = layout.pageCollection().pageCount()
    except Exception:  # noqa: BLE001
        total_pages = 0
    for page_idx in range(total_pages):
        try:
            _add_footer(layout, page_index=page_idx,
                        date_str=date_str,
                        page_num=page_idx + 1, total_pages=total_pages)
        except Exception:  # noqa: BLE001
            pass

    return layout


def _page_y_offset(layout, page_index: int) -> float:
    """Absolute y-offset (mm) of a given page in the layout scene.

    Uses the page's own scene position rather than summing heights,
    because QGIS inserts a 10mm gap between pages. Summing heights
    puts items into the inter-page gap instead of on-page.
    """
    try:
        page = layout.pageCollection().page(page_index)
        return float(page.pos().y())
    except Exception:  # noqa: BLE001
        return page_index * (_A4_LANDSCAPE_H_MM + 10.0)


def _add_title_band(layout, *, page_index: int, header_text: str,
                    date_str: str, config: PdfExportConfig):
    """Header layout (18 mm band).

    Slots from left to right:
      - Vessel logo:  (_MARGIN_MM .. +_LOGO_SLOT_W_MM)
      - Title:        centered between vessel logo and company+client
                      logos, 14 pt bold, both axes centered
      - Company logo: right column, below title-row top
      - Client logo:  far-right column

    Date is NOT on the header — it lives in the footer ("Generated
    <date> • Page N of M") to avoid competing with the logos inside
    an 18 mm band.
    """
    qc = _qgis_core()
    page_y = _page_y_offset(layout, page_index)

    logo_y = page_y + (_TITLE_BAND_H_MM - _LOGO_SLOT_H_MM) / 2.0

    # Vessel logo (left)
    _place_logo_centered(
        layout, qc, config.logo_vessel_path,
        slot_x=_MARGIN_MM, slot_y=logo_y,
        slot_w=_LOGO_SLOT_W_MM, slot_h=_LOGO_SLOT_H_MM,
    )

    # Right column: client (far-right) + company (just left of client)
    client_x = _A4_LANDSCAPE_W_MM - _MARGIN_MM - _LOGO_SLOT_W_MM
    company_x = client_x - _LOGO_SLOT_W_MM - 4.0
    _place_logo_centered(
        layout, qc, config.logo_company_path,
        slot_x=company_x, slot_y=logo_y,
        slot_w=_LOGO_SLOT_W_MM, slot_h=_LOGO_SLOT_H_MM,
    )
    _place_logo_centered(
        layout, qc, config.logo_client_path,
        slot_x=client_x, slot_y=logo_y,
        slot_w=_LOGO_SLOT_W_MM, slot_h=_LOGO_SLOT_H_MM,
    )

    # Title centered between the left-logo column and the right-logo column
    title_x = _MARGIN_MM + _LOGO_SLOT_W_MM + 6.0
    title_w = max(20.0, company_x - title_x - 6.0)

    title = qc.QgsLayoutItemLabel(layout)
    title.setText(header_text)
    try:
        font = title.font()
        font.setPointSizeF(14.0)
        font.setBold(True)
        title.setFont(font)
    except AttributeError:
        pass
    try:
        title.setHAlign(0x04)  # Qt.AlignHCenter
        title.setVAlign(0x80)  # Qt.AlignVCenter
    except AttributeError:
        pass
    layout.addLayoutItem(title)
    _place(title, qc, title_x, page_y, title_w, _TITLE_BAND_H_MM)

    # Thin horizontal rule at the bottom of the header band — built
    # from a QgsLayoutItemShape rectangle with a grey fill and no stroke.
    try:
        from qgis.PyQt.QtGui import QColor
        rule = qc.QgsLayoutItemShape(layout)
        try:
            rule.setShapeType(qc.QgsLayoutItemShape.Rectangle)
        except AttributeError:
            pass
        try:
            from qgis.core import QgsSimpleFillSymbolLayer, QgsFillSymbol
            fill = QgsSimpleFillSymbolLayer()
            fill.setColor(QColor(140, 140, 140))
            fill.setStrokeStyle(0)  # Qt.NoPen
            rule.setSymbol(QgsFillSymbol([fill]))
        except Exception:  # noqa: BLE001
            pass
        layout.addLayoutItem(rule)
        _place(rule, qc, _MARGIN_MM, page_y + _TITLE_BAND_H_MM - 0.4,
               _A4_LANDSCAPE_W_MM - 2 * _MARGIN_MM, 0.4)
    except Exception:  # noqa: BLE001
        pass


def _add_footer(layout, *, page_index: int, date_str: str,
                page_num: int, total_pages: int):
    """Small footer with generation date + page number, centered.

    Phase 17d.6: page count is hardcoded (not an expression) because
    `[% @layout_pagecount %]` rendered literally in QGIS 3.34 / 3.40
    when used on a raw QgsLayoutItemLabel — "Page 1 of" would come
    out with "?? " or a blank instead of the total count. Caller is
    responsible for passing the right total.
    """
    qc = _qgis_core()
    page_y = _page_y_offset(layout, page_index)
    footer_y = page_y + _A4_LANDSCAPE_H_MM - 7.0

    label = qc.QgsLayoutItemLabel(layout)
    label.setText(
        f"Generated {date_str.replace('_', '-')}  \u2022  "
        f"Page {page_num} of {total_pages}"
    )
    try:
        label.setMode(qc.QgsLayoutItemLabel.ModeFont)
    except AttributeError:
        pass
    try:
        font = label.font()
        font.setPointSize(8)
        label.setFont(font)
        label.setHAlign(_HALIGN["C"])
        label.setVAlign(_VALIGN_CENTER)
    except AttributeError:
        pass
    layout.addLayoutItem(label)
    _place(label, qc,
           _MARGIN_MM, footer_y,
           _A4_LANDSCAPE_W_MM - 2 * _MARGIN_MM, 5.0)


def _expand_extent_to_aspect(extent, target_aspect: float):
    """Expand (never crop) the extent so its aspect matches target.

    Preserves the center point. If target is wider than current, widen
    horizontally; if taller, extend vertically. Keeps the user's chosen
    framing fully visible in the PDF.
    """
    if extent is None or extent.width() <= 0 or extent.height() <= 0 \
            or target_aspect <= 0:
        return extent
    cur_aspect = extent.width() / extent.height()
    # QgsRectangle is mutable; mutate in place (caller expects same object).
    if cur_aspect < target_aspect:
        needed_w = extent.height() * target_aspect
        dx = (needed_w - extent.width()) / 2.0
        extent.setXMinimum(extent.xMinimum() - dx)
        extent.setXMaximum(extent.xMaximum() + dx)
    elif cur_aspect > target_aspect:
        needed_h = extent.width() / target_aspect
        dy = (needed_h - extent.height()) / 2.0
        extent.setYMinimum(extent.yMinimum() - dy)
        extent.setYMaximum(extent.yMaximum() + dy)
    return extent


def _add_map_item(layout, *, page_index: int, layers, extent,
                  config: PdfExportConfig, map_crs=None):
    qc = _qgis_core()
    mm = qc.QgsUnitTypes.LayoutMillimeters
    page_y = _page_y_offset(layout, page_index)
    body_y = page_y + _TITLE_BAND_H_MM + 2.0
    body_h = _A4_LANDSCAPE_H_MM - _TITLE_BAND_H_MM - 2.0 - _MARGIN_MM
    body_x = _MARGIN_MM + _LEFT_MAP_GUTTER_MM
    # Reserve right gutter for legend so they don't overlap the map.
    right_reserve = _RIGHT_LEGEND_GUTTER_MM if config.show_legend else 0.0
    body_w = (_A4_LANDSCAPE_W_MM - _MARGIN_MM - right_reserve) - body_x

    # Match the extent's aspect ratio to the map frame BEFORE assigning so
    # QgsLayoutItemMap.setExtent does not silently extend it further and
    # zoom out beyond what the user framed in the preview canvas.
    if extent is not None and body_w > 0 and body_h > 0:
        from qgis.core import QgsRectangle
        fitted = QgsRectangle(extent)
        _expand_extent_to_aspect(fitted, body_w / body_h)
    else:
        fitted = extent

    map_item = qc.QgsLayoutItemMap(layout)
    layout.addLayoutItem(map_item)
    _place(map_item, qc, body_x, body_y, body_w, body_h)

    # CRS must be set BEFORE setExtent so the extent values are
    # interpreted in the same coordinate system as the preview canvas.
    # Without this the map item defaults to the project CRS and, if the
    # two differ, the UTM-metre extent gets reinterpreted as degrees
    # (or vice versa) and the map zooms to a wildly wrong area.
    if map_crs is not None:
        try:
            map_item.setCrs(map_crs)
        except AttributeError:
            pass

    if fitted is not None:
        map_item.setExtent(fitted)
    if layers:
        map_item.setLayers(list(layers))

    # Phase 17d.2: grid style (off / light / normal). grid_style
    # overrides show_coord_grid when present; "off" disables the grid
    # entirely, "light" draws a faint grey reference, "normal" draws
    # a standard cartographic grid.
    grid_style = getattr(config, "grid_style", "light")
    grid_on = (grid_style != "off") and (
        config.show_coord_grid if grid_style == "light" else True
    )
    if grid_on and fitted is not None and fitted.width() > 0:
        try:
            grid = map_item.grid()
            grid.setEnabled(True)
            short = min(fitted.width(), fitted.height())
            step = _round_grid_step(short / 6.0)
            grid.setIntervalX(step)
            grid.setIntervalY(step)
            grid.setAnnotationEnabled(True)
            try:
                grid.setAnnotationPrecision(0 if step >= 10 else 2)
            except AttributeError:
                pass
            # Phase 17d.5: smaller, softer annotation font, and
            # restrict label placement to bottom + left only (matches
            # the reference Petrobras PDF and the user's request).
            try:
                from qgis.PyQt.QtGui import QColor, QFont
                ann_font = QFont()
                ann_font.setPointSizeF(7.0)
                # setAnnotationFont(QFont) -> QGIS 3.x; fall back to
                # setAnnotationTextFormat via QgsTextFormat if needed.
                try:
                    grid.setAnnotationFont(ann_font)
                except AttributeError:
                    try:
                        from qgis.core import QgsTextFormat
                        fmt = QgsTextFormat()
                        fmt.setFont(ann_font)
                        fmt.setSize(7.0)
                        fmt.setColor(QColor(100, 100, 100))
                        grid.setAnnotationTextFormat(fmt)
                    except Exception:  # noqa: BLE001
                        pass
                try:
                    grid.setAnnotationFontColor(QColor(100, 100, 100))
                except AttributeError:
                    pass
                # Hide top + right annotations; keep bottom + left.
                Mg = qc.QgsLayoutItemMapGrid
                hide_all = getattr(Mg, "HideAll", 3)
                show_all = getattr(Mg, "ShowAll", 0)
                try:
                    grid.setAnnotationDisplay(hide_all, Mg.Top)
                    grid.setAnnotationDisplay(hide_all, Mg.Right)
                    grid.setAnnotationDisplay(show_all, Mg.Bottom)
                    grid.setAnnotationDisplay(show_all, Mg.Left)
                except Exception:  # noqa: BLE001
                    pass
            except Exception:  # noqa: BLE001
                pass
            # Line style: light grey vs normal grey.
            try:
                from qgis.PyQt.QtGui import QColor
                if grid_style == "light":
                    grid.setGridLineColor(QColor(180, 180, 180, 180))
                    grid.setGridLineWidth(0.1)
                else:
                    grid.setGridLineColor(QColor(80, 80, 80))
                    grid.setGridLineWidth(0.2)
            except Exception:  # noqa: BLE001
                pass
        except Exception:  # noqa: BLE001
            pass

    if config.show_north_arrow:
        # Try to use a built-in QGIS north-arrow SVG; fall back to a
        # text label "N \u25b2" so the arrow is always present even
        # when no system SVG is resolvable.
        arrow_w, arrow_h = 16.0, 16.0
        arrow_x = body_x + body_w - arrow_w - 2.0
        arrow_y = body_y + 2.0
        svg_path = _resolve_north_arrow_svg(qc)
        if svg_path:
            try:
                pic = qc.QgsLayoutItemPicture(layout)
                pic.setPicturePath(svg_path)
                try:
                    pic.setNorthMode(qc.QgsLayoutItemPicture.GridNorth)
                    pic.setLinkedMap(map_item)
                except AttributeError:
                    pass
                try:
                    pic.setResizeMode(qc.QgsLayoutItemPicture.Zoom)
                except AttributeError:
                    pass
                layout.addLayoutItem(pic)
                _place(pic, qc, arrow_x, arrow_y, arrow_w, arrow_h)
            except Exception:  # noqa: BLE001
                _add_text_north(layout, qc, arrow_x, arrow_y, arrow_w, arrow_h)
        else:
            _add_text_north(layout, qc, arrow_x, arrow_y, arrow_w, arrow_h)

    if config.show_scale_bar:
        scale = qc.QgsLayoutItemScaleBar(layout)
        # Link the map BEFORE units / segments / applyDefaultSize so
        # the scale bar has a scale source when those methods fire.
        scale.setLinkedMap(map_item)
        try:
            scale.setStyle("Single Box")
        except Exception:  # noqa: BLE001
            pass
        # Phase 17d.2 (fixed 17d.5): force kilometres. Order matters —
        # applyDefaultSize() resets many derived properties, so it
        # must come BEFORE our segment-count + units overrides.
        try:
            scale.applyDefaultSize()
        except Exception:  # noqa: BLE001
            pass
        try:
            scale.setUnits(qc.QgsUnitTypes.DistanceKilometers)
            scale.setUnitLabel("km")
        except AttributeError:
            pass
        try:
            scale.setNumberOfSegments(4)
            scale.setNumberOfSegmentsLeft(0)
        except AttributeError:
            pass
        try:
            # Pick a reasonable segment width given the map scale.
            if fitted is not None and fitted.width() > 0:
                km_total = fitted.width() / 1000.0
                # aim for roughly km_total / 6 per segment, rounded nice
                raw = max(1.0, km_total / 6.0)
                scale.setUnitsPerSegment(_round_grid_step(raw))
        except Exception:  # noqa: BLE001
            pass
        # Phase 17d.6: compact scale bar — user feedback: previous
        # 4.5 mm + 8 pt was "too big and too distracting". Revert to
        # a slim reference strip.
        try:
            scale.setHeight(2.2)
            scale.setBoxContentSpace(0.5)
        except Exception:  # noqa: BLE001
            pass
        try:
            from qgis.PyQt.QtGui import QFont
            sb_font = QFont()
            sb_font.setPointSizeF(6.5)
            try:
                scale.setFont(sb_font)
            except AttributeError:
                try:
                    from qgis.core import QgsTextFormat
                    fmt = QgsTextFormat()
                    fmt.setFont(sb_font)
                    fmt.setSize(6.5)
                    scale.setTextFormat(fmt)
                except Exception:  # noqa: BLE001
                    pass
        except Exception:  # noqa: BLE001
            pass
        try:
            scale.update()
        except Exception:  # noqa: BLE001
            pass
        layout.addLayoutItem(scale)
        try:
            scale.attemptMove(qc.QgsLayoutPoint(
                body_x + 2.0, body_y + body_h - 10.0, mm))
        except Exception:  # noqa: BLE001
            pass

    if config.show_legend:
        legend = qc.QgsLayoutItemLegend(layout)
        legend.setLinkedMap(map_item)

        # filter-by-map invokes a code path that crashed in 3.40.5 when
        # combined with a custom layer tree. Our visible_layers list
        # already filters correctly via the cloned tree below, so we
        # turn off the Qt-side filter explicitly.
        try:
            legend.setLegendFilterByMapEnabled(False)
        except AttributeError:
            pass

        name_overrides = {
            k: v for k, v in (config.layer_display_names or {}).items() if v
        }
        group_overrides = config.group_display_names or {}
        hidden_from_legend = set(config.hidden_from_legend or ())
        try:
            project = layout.project()
        except AttributeError:
            project = None

        applied_custom_tree = False
        if project is not None:
            try:
                custom_tree = project.layerTreeRoot().clone()
                visible_ids = {l.id() for l in (layers or [])}

                # Step 1: remove layer nodes that aren't on the map OR
                # are opted out of the legend, and rename the rest.
                # Phase 17d.5: DO NOT collapse style subclasses — the
                # Optimized_Path direction colors (Line Low->High,
                # Line High->Low, Turn, Run-In) are the core
                # information on the 48-hr shooting plan. Let each
                # layer contribute its natural per-style legend rows.
                # If a layer is too noisy, use col-2 in the dialog to
                # hide the whole layer from the legend.
                for node in list(custom_tree.findLayers()):
                    lid = node.layerId()
                    keep_on_map = (not visible_ids) or (lid in visible_ids)
                    keep_in_legend = keep_on_map and (lid not in hidden_from_legend)
                    if not keep_in_legend:
                        parent = node.parent()
                        if parent is not None:
                            parent.removeChildNode(node)
                        continue
                    if lid in name_overrides:
                        try:
                            node.setUseLayerName(False)
                        except AttributeError:
                            pass
                        node.setName(name_overrides[lid])

                # Step 1.5 (Phase 17d.5/.6/.7): reorder top-level nodes
                # — BOTH groups AND standalone layers — to match the
                # user's explicit legend order.
                #
                # IMPORTANT: QgsLayerTreeGroup.removeChildNode() DELETES
                # the node (destructor runs). Re-adding the same Python
                # wrapper afterwards yields a dangling pointer and
                # QGIS silently drops it — that's what emptied the
                # legend in 17d.6. Fix: build a fresh tree with deep
                # clones, then swap it in as the new custom_tree.
                #
                # Keys in legend_order are prefixed "l:<layer_id>" or
                # "g:<group_name>". Legacy bare layer_ids (pre-17d.6)
                # are still accepted.
                legend_order = list(getattr(config, "legend_order", []) or [])
                if legend_order:
                    from qgis.core import (
                        QgsLayerTree,
                        QgsLayerTreeGroup,
                        QgsLayerTreeLayer,
                    )
                    top_by_key = {}
                    for ch in custom_tree.children():
                        if isinstance(ch, QgsLayerTreeLayer):
                            top_by_key["l:" + ch.layerId()] = ch
                        elif isinstance(ch, QgsLayerTreeGroup):
                            top_by_key["g:" + ch.name()] = ch
                    ordered = []
                    for key in legend_order:
                        candidates = [key]
                        if not (key.startswith("l:") or key.startswith("g:")):
                            candidates = ["l:" + key]
                        for k in candidates:
                            node = top_by_key.pop(k, None)
                            if node is not None:
                                ordered.append(node)
                                break
                    # Remaining nodes keep their natural order.
                    ordered.extend(top_by_key.values())

                    new_tree = QgsLayerTree()
                    for node in ordered:
                        try:
                            new_tree.addChildNode(node.clone())
                        except Exception:  # noqa: BLE001
                            pass
                    custom_tree = new_tree

                # Step 2: for each group node, either rename (non-empty
                # override) or flatten (empty override). Flattening:
                # move children up to the parent and remove the group.
                try:
                    groups = list(custom_tree.findGroups())
                except AttributeError:
                    groups = []
                for grp in groups:
                    name = grp.name()
                    if name not in group_overrides:
                        continue
                    new_name = group_overrides[name]
                    if new_name == "":
                        # Flatten: reparent children, drop the group.
                        parent = grp.parent()
                        if parent is None:
                            continue
                        for child in list(grp.children()):
                            grp.removeChildNode(child)
                            parent.addChildNode(child)
                        parent.removeChildNode(grp)
                    else:
                        grp.setName(new_name)

                # Ownership hand-off: setCustomLayerTree claims
                # ownership in C++ but PyQGIS /Transfer/ annotations
                # vary across versions. Pin on the layout so Python's
                # GC never frees it during render.
                try:
                    layout._pdf_export_custom_tree = custom_tree
                except Exception:  # noqa: BLE001
                    pass

                legend.setAutoUpdateModel(False)
                set_custom = getattr(legend, "setCustomLayerTree", None)
                if set_custom is not None:
                    set_custom(custom_tree)
                else:
                    legend.model().setRootGroup(custom_tree)
                applied_custom_tree = True
            except Exception:  # noqa: BLE001
                applied_custom_tree = False

        if not applied_custom_tree:
            legend.setAutoUpdateModel(True)

        try:
            legend.setResizeToContents(True)
        except AttributeError:
            pass
        # Phase 17d.6: "Legend" headline + compact entry fonts.
        # User feedback: the LAYER entries in the legend were too big.
        # Target sizes (tuned against the Petrobras reference PDF):
        #   Title        10 pt bold
        #   Group         7.5 pt bold
        #   Subgroup      7 pt bold
        #   SymbolLabel   6.5 pt
        # Also shrink the symbol swatches and tighten spacing so the
        # whole block reads as a reference strip, not a second panel.
        try:
            legend.setTitle("Legend")
            legend.setTitleAlignment(0x04)  # Qt.AlignHCenter
        except AttributeError:
            pass
        try:
            from qgis.PyQt.QtGui import QFont
            from qgis.core import QgsLegendStyle
            title_font = QFont()
            title_font.setPointSizeF(10.0)
            title_font.setBold(True)
            group_font = QFont()
            group_font.setPointSizeF(7.5)
            group_font.setBold(True)
            subgroup_font = QFont()
            subgroup_font.setPointSizeF(7.0)
            subgroup_font.setBold(True)
            item_font = QFont()
            item_font.setPointSizeF(6.5)
            try:
                legend.setTitleFont(title_font)
            except AttributeError:
                pass
            try:
                legend.setStyleFont(QgsLegendStyle.Title, title_font)
                legend.setStyleFont(QgsLegendStyle.Group, group_font)
                legend.setStyleFont(QgsLegendStyle.Subgroup, subgroup_font)
                legend.setStyleFont(QgsLegendStyle.SymbolLabel, item_font)
            except Exception:  # noqa: BLE001
                pass
            # Smaller symbol swatches (default is ~7 mm square).
            try:
                legend.setSymbolWidth(4.0)
                legend.setSymbolHeight(2.8)
            except AttributeError:
                pass
            # Tighter spacing between rows / between symbol + label.
            try:
                legend.setWmsLegendWidth(25.0)
                legend.setWmsLegendHeight(14.0)
            except AttributeError:
                pass
            try:
                legend.setBoxSpace(1.0)
                legend.setColumnSpace(1.5)
            except AttributeError:
                pass
        except Exception:  # noqa: BLE001
            pass

        layout.addLayoutItem(legend)
        try:
            legend_x = body_x + body_w + 2.0
            legend_w = max(20.0, _A4_LANDSCAPE_W_MM - _MARGIN_MM - legend_x)
            _place(legend, qc, legend_x, body_y, legend_w, body_h)
        except Exception:  # noqa: BLE001
            pass


def _resolve_north_arrow_svg(qc):
    """Return a usable path to a built-in north-arrow SVG, or None.

    Scans QGIS's configured SVG search paths for the common arrow
    names that ship with the installation (`NorthArrow_0X.svg`,
    `arrow_NN.svg`, `Arrow_NN.svg`).
    """
    try:
        from qgis.core import QgsApplication
        svg_paths = QgsApplication.svgPaths() or []
    except Exception:  # noqa: BLE001
        svg_paths = []
    candidates = (
        "arrows/NorthArrow_02.svg",
        "arrows/NorthArrow_01.svg",
        "arrows/NorthArrow_03.svg",
        "arrows/Arrow_02.svg",
        "arrows/Arrow_01.svg",
    )
    for base in svg_paths:
        for rel in candidates:
            full = os.path.join(base, rel)
            if os.path.isfile(full):
                return full
    return None


def _add_text_north(layout, qc, x: float, y: float, w: float, h: float):
    label = qc.QgsLayoutItemLabel(layout)
    label.setText("N\n\u25b2")
    try:
        font = label.font()
        font.setPointSize(14)
        font.setBold(True)
        label.setFont(font)
        label.setHAlign(_HALIGN["C"])
        label.setVAlign(_VALIGN_CENTER)
        label.setBackgroundEnabled(True)
        from qgis.PyQt.QtGui import QColor
        label.setBackgroundColor(QColor(255, 255, 255))
        label.setFrameEnabled(True)
        label.setFrameStrokeColor(QColor(60, 60, 60))
        label.setFrameStrokeWidth(qc.QgsLayoutMeasurement(
            0.3, qc.QgsUnitTypes.LayoutMillimeters))
    except Exception:  # noqa: BLE001
        pass
    layout.addLayoutItem(label)
    _place(label, qc, x, y, w, h)


def _round_grid_step(raw: float) -> float:
    """Round a grid step up to a 'nice' number (1/2/5 × 10^n).

    Works for both meters (UTM) and degrees. Input zero/negative returns 1.
    """
    if raw is None or raw <= 0:
        return 1.0
    import math
    exp = math.floor(math.log10(raw))
    base = 10.0 ** exp
    normalized = raw / base
    if normalized < 1.5:
        nice = 1.0
    elif normalized < 3.5:
        nice = 2.0
    elif normalized < 7.5:
        nice = 5.0
    else:
        nice = 10.0
    return nice * base


def _draw_table_fallback(layout, *, rows: List[LookaheadRow],
                         header_text: str, date_str: str,
                         config: PdfExportConfig):
    """Label-grid fallback when QgsLayoutItemManualTable cannot be
    instantiated (abstract in some PyQGIS builds).

    Paginates manually: fixed rows-per-page, title band + column
    header on every page. Not as crisp as the manual-table path but
    always works.
    """
    qc = _qgis_core()
    mm = qc.QgsUnitTypes.LayoutMillimeters

    try:
        from qgis.PyQt.QtGui import QColor
        header_bg = QColor(255, 248, 168)
        alt_bg = QColor(245, 245, 245)
        white = QColor(255, 255, 255)
        border = QColor(160, 160, 160)
    except Exception:  # noqa: BLE001
        header_bg = alt_bg = white = border = None

    total_w = sum(col_w for _n, _k, col_w, _a in _TABLE_COLUMNS)
    table_left = (_A4_LANDSCAPE_W_MM - total_w) / 2.0
    row_h = 6.5
    header_h = 8.0
    usable_h = _A4_LANDSCAPE_H_MM - _TITLE_BAND_H_MM - 4.0 - _MARGIN_MM - header_h
    rows_per_page = max(1, int(usable_h // row_h))
    n_pages = max(1, (len(rows) + rows_per_page - 1) // rows_per_page) if rows else 1

    page_collection = layout.pageCollection()
    for i in range(n_pages):
        page = qc.QgsLayoutItemPage(layout)
        page.setPageSize(
            qc.QgsLayoutSize(_A4_LANDSCAPE_W_MM, _A4_LANDSCAPE_H_MM, mm)
        )
        page_collection.addPage(page)
        page_idx = page_collection.pageCount() - 1
        _add_title_band(layout, page_index=page_idx,
                        header_text=header_text, date_str=date_str,
                        config=config)

        page_y = _page_y_offset(layout, page_idx)
        y0 = page_y + _TITLE_BAND_H_MM + 4.0

        # Column header row (repeats on every page).
        x_cursor = table_left
        for col_name, _key, col_w, align in _TABLE_COLUMNS:
            label = qc.QgsLayoutItemLabel(layout)
            label.setText(col_name)
            try:
                font = label.font()
                font.setBold(True)
                font.setPointSizeF(9.5)
                label.setFont(font)
                label.setHAlign(_HALIGN[align])
                label.setVAlign(_VALIGN_CENTER)
                label.setMarginX(1.5)
                label.setMarginY(0.8)
                if header_bg is not None:
                    label.setBackgroundEnabled(True)
                    label.setBackgroundColor(header_bg)
                if border is not None:
                    label.setFrameEnabled(True)
                    label.setFrameStrokeColor(border)
                    label.setFrameStrokeWidth(qc.QgsLayoutMeasurement(0.15, mm))
            except Exception:  # noqa: BLE001
                pass
            layout.addLayoutItem(label)
            _place(label, qc, x_cursor, y0, col_w, header_h)
            x_cursor += col_w

        # Data rows for this page.
        chunk = rows[i * rows_per_page:(i + 1) * rows_per_page]
        for row_idx, row in enumerate(chunk):
            x_cursor = table_left
            y_cursor = y0 + header_h + row_idx * row_h
            bg = alt_bg if (row_idx % 2 == 1) else white
            for _col_name, key, col_w, align in _TABLE_COLUMNS:
                cell = qc.QgsLayoutItemLabel(layout)
                cell.setText(_cell_text(row, key))
                try:
                    font = cell.font()
                    font.setPointSizeF(9.0)
                    cell.setFont(font)
                    cell.setHAlign(_HALIGN[align])
                    cell.setVAlign(_VALIGN_CENTER)
                    cell.setMarginX(1.5)
                    cell.setMarginY(0.5)
                    if bg is not None:
                        cell.setBackgroundEnabled(True)
                        cell.setBackgroundColor(bg)
                    if border is not None:
                        cell.setFrameEnabled(True)
                        cell.setFrameStrokeColor(border)
                        cell.setFrameStrokeWidth(qc.QgsLayoutMeasurement(0.1, mm))
                except Exception:  # noqa: BLE001
                    pass
                layout.addLayoutItem(cell)
                _place(cell, qc, x_cursor, y_cursor, col_w, row_h)
                x_cursor += col_w


def _add_table_pages(layout, *, rows: List[LookaheadRow],
                     header_text: str, date_str: str,
                     config: PdfExportConfig):
    """Render the sequence table using QgsLayoutItemManualTable.

    The table auto-paginates: one frame per page, column headers repeat
    on every page (QgsLayoutTable.AllFrames), rows split cleanly on row
    boundaries, and new pages are added automatically as needed. First
    table page gets the same big title band as the map page; subsequent
    table pages repeat only the column header, matching how daily plan
    reports normally look.
    """
    qc = _qgis_core()
    mm = qc.QgsUnitTypes.LayoutMillimeters

    try:
        from qgis.PyQt.QtGui import QColor
        header_bg = QColor(255, 248, 168)   # yellow
        alt_bg = QColor(245, 245, 245)
        border = QColor(160, 160, 160)
    except Exception:  # noqa: BLE001
        header_bg = alt_bg = border = None

    try:
        _add_manual_table(
            layout, qc=qc, rows=rows, header_text=header_text,
            date_str=date_str, config=config,
            header_bg=header_bg, alt_bg=alt_bg, border=border,
        )
    except Exception:  # noqa: BLE001
        import logging
        logging.getLogger("obn_planner").exception(
            "Manual-table render failed; falling back to label grid")
        _draw_table_fallback(
            layout, rows=rows, header_text=header_text,
            date_str=date_str, config=config,
        )
    return


def _add_manual_table(layout, *, qc, rows, header_text, date_str, config,
                     header_bg, alt_bg, border):
    """Render the table via QgsLayoutItemManualTable (factory-created).

    In PyQGIS, QgsLayoutItemManualTable is exposed as abstract — we
    construct it via the layout-item registry factory. Any exception
    here is caught by the caller which falls back to the label grid.
    """
    mm = qc.QgsUnitTypes.LayoutMillimeters

    # Instantiate via registry; the Python constructor is abstract.
    table = None
    from qgis.core import QgsApplication, QgsLayoutItemRegistry
    reg = QgsApplication.layoutItemRegistry()
    mf_id = getattr(QgsLayoutItemRegistry, "LayoutManualTable", None)
    if mf_id is not None:
        table = reg.createMultiFrame(int(mf_id), layout)
    if table is None:
        create_fn = getattr(qc.QgsLayoutItemManualTable, "create", None)
        if create_fn is not None:
            table = create_fn(layout)
    if table is None:
        raise RuntimeError("QgsLayoutItemManualTable could not be created")
    layout.addMultiFrame(table)

    # Columns: widths + default alignment.
    columns = []
    for col_name, _k, col_w, align in _TABLE_COLUMNS:
        col = qc.QgsLayoutTableColumn(col_name)
        col.setWidth(col_w)
        try:
            col.setHAlignment(_HALIGN[align])
            col.setVAlignment(_VALIGN_CENTER)
        except AttributeError:
            pass
        columns.append(col)
    table.setColumns(columns)

    # Headers (yellow background, bold).
    header_cells = []
    for col_name, _k, _w, align in _TABLE_COLUMNS:
        c = qc.QgsTableCell(col_name)
        try:
            if header_bg is not None:
                c.setBackgroundColor(header_bg)
            c.setHorizontalAlignment(_HALIGN[align])
            c.setVerticalAlignment(_VALIGN_CENTER)
        except AttributeError:
            pass
        header_cells.append(c)
    try:
        table.setHeaders(header_cells)
        table.setHeaderMode(qc.QgsLayoutTable.AllFrames)  # repeat each page
    except AttributeError:
        pass

    # Data cells with alternating row backgrounds.
    contents = []
    for row_idx, row in enumerate(rows):
        row_cells = []
        bg = alt_bg if (row_idx % 2 == 1) else None
        for col_name, key, _w, align in _TABLE_COLUMNS:
            c = qc.QgsTableCell(_cell_text(row, key))
            try:
                if bg is not None:
                    c.setBackgroundColor(bg)
                c.setHorizontalAlignment(_HALIGN[align])
                c.setVerticalAlignment(_VALIGN_CENTER)
            except AttributeError:
                pass
            row_cells.append(c)
        contents.append(row_cells)
    table.setTableContents(contents)

    # Visual styling: grid lines, padding, font.
    try:
        table.setShowGrid(True)
        if border is not None:
            table.setGridColor(border)
        table.setGridStrokeWidth(0.15)
        table.setCellMargin(1.5)
    except AttributeError:
        pass
    try:
        from qgis.PyQt.QtGui import QFont
        content_font = QFont()
        content_font.setPointSizeF(9.0)
        table.setContentFont(content_font)
        header_font = QFont()
        header_font.setPointSizeF(9.5)
        header_font.setBold(True)
        table.setHeaderFont(header_font)
    except Exception:  # noqa: BLE001
        pass

    # Add first page for the table + its big title band.
    page_collection = layout.pageCollection()
    page = qc.QgsLayoutItemPage(layout)
    page.setPageSize(
        qc.QgsLayoutSize(_A4_LANDSCAPE_W_MM, _A4_LANDSCAPE_H_MM, mm)
    )
    page_collection.addPage(page)
    first_table_page = page_collection.pageCount() - 1
    _add_title_band(layout, page_index=first_table_page,
                    header_text=header_text, date_str=date_str,
                    config=config)

    # First frame for the table on the first table page.
    total_w = sum(col_w for _n, _k, col_w, _a in _TABLE_COLUMNS)
    table_left = (_A4_LANDSCAPE_W_MM - total_w) / 2.0
    page_y = _page_y_offset(layout, first_table_page)
    body_y = page_y + _TITLE_BAND_H_MM + 4.0
    body_h = _A4_LANDSCAPE_H_MM - _TITLE_BAND_H_MM - 4.0 - _MARGIN_MM

    frame = qc.QgsLayoutFrame(layout, table)
    layout.addLayoutItem(frame)
    _place(frame, qc, table_left, body_y, total_w, body_h)
    table.addFrame(frame)

    # Auto-extend onto new pages as needed.
    try:
        table.setResizeMode(qc.QgsLayoutMultiFrame.ExtendToNextPage)
    except AttributeError:
        pass
    try:
        table.recalculateFrameSizes()
    except AttributeError:
        pass


def export_pdf(layout, output_path: str) -> Tuple[bool, Optional[str]]:
    """Render the layout to a PDF file. Returns (ok, error_message)."""
    qc = _qgis_core()
    exporter = qc.QgsLayoutExporter(layout)
    settings = qc.QgsLayoutExporter.PdfExportSettings()
    result = exporter.exportToPdf(output_path, settings)
    if result == qc.QgsLayoutExporter.Success:
        return True, None
    return False, f"QgsLayoutExporter error code {int(result)}"
