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
    seq_order: int
    line_num: int
    sub_line_id: Optional[int]
    shoot_as: str           # v1: str(line_num) when sub_line_id is None,
                            #     else f"{line_num}-{sub_line_id}".
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
    show_coord_grid: bool = True


# --- QGIS-dependent helpers -------------------------------------------------
#
# Imported lazily so that services/pdf_export.py is importable in a
# pure-Python test runner without QGIS installed.


def _qgis_core():
    from qgis import core as qgis_core  # type: ignore
    return qgis_core


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
) -> List[LookaheadRow]:
    """Read Optimized_Path line-features in SeqOrder and join
    Generated_Survey_Lines on (LineNum, SubLineId) to pull
    Operation/FGSP/LGSP.

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

        if sl is not None and sl != 0:
            shoot_as = f"{ln}-{sl}"
        else:
            shoot_as = str(ln)

        rows.append(LookaheadRow(
            seq_order=_read_int(f, "SeqOrder") or 0,
            line_num=ln,
            sub_line_id=sl,
            shoot_as=shoot_as,
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
_TITLE_BAND_H_MM = 22.0
_MARGIN_MM = 10.0

_TABLE_COLUMNS = (
    ("Line",        "line_num",    14.0),
    ("Shoot As",    "shoot_as",    28.0),
    ("Operation",   "operation",   28.0),
    ("FGSP",        "fgsp",        20.0),
    ("LGSP",        "lgsp",        20.0),
    ("HDG\u00b0",   "heading_deg", 18.0),
    ("ETA SOL",     "eta_sol",     28.0),
    ("ETA EOL",     "eta_eol",     28.0),
    ("Day/Month",   "day_month",   24.0),
)


def _cell_text(row: LookaheadRow, key: str) -> str:
    if key == "line_num":
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
    layout.setName("OBN Planner — 48h Lookahead")

    page_collection = layout.pageCollection()
    page_collection.page(0).setPageSize(
        qc.QgsLayoutSize(_A4_LANDSCAPE_W_MM, _A4_LANDSCAPE_H_MM, qc.QgsUnitTypes.LayoutMillimeters)
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
                  extent=map_extent, config=config)

    _add_table_pages(layout, rows=rows, header_text=header_text,
                     date_str=date_str, config=config)

    return layout


def _add_title_band(layout, *, page_index: int, header_text: str,
                    date_str: str, config: PdfExportConfig):
    qc = _qgis_core()
    page_y = layout.pageCollection().page(page_index).pos().y() \
        if hasattr(layout.pageCollection().page(page_index), "pos") else 0.0

    title = qc.QgsLayoutItemLabel(layout)
    title.setText(header_text)
    try:
        font = title.font()
        font.setPointSize(14)
        font.setBold(True)
        title.setFont(font)
    except AttributeError:
        pass
    title.attemptSetSceneRect(qc.QgsLayoutRect(
        _MARGIN_MM, page_y + 4.0,
        _A4_LANDSCAPE_W_MM - 2 * _MARGIN_MM, _TITLE_BAND_H_MM - 6.0,
        qc.QgsUnitTypes.LayoutMillimeters,
    ))
    layout.addLayoutItem(title)

    date_label = qc.QgsLayoutItemLabel(layout)
    date_label.setText(date_str.replace("_", "-"))
    try:
        font = date_label.font()
        font.setPointSize(10)
        date_label.setFont(font)
    except AttributeError:
        pass
    date_label.attemptSetSceneRect(qc.QgsLayoutRect(
        _A4_LANDSCAPE_W_MM - 60.0, page_y + 4.0, 50.0, 6.0,
        qc.QgsUnitTypes.LayoutMillimeters,
    ))
    try:
        date_label.setHAlign(0x02)  # Qt.AlignRight
    except AttributeError:
        pass
    layout.addLayoutItem(date_label)

    _add_logos(layout, page_index=page_index, config=config)


def _add_logos(layout, *, page_index: int, config: PdfExportConfig):
    qc = _qgis_core()
    slots = [
        (config.logo_vessel_path,  _MARGIN_MM),
        (config.logo_company_path, _A4_LANDSCAPE_W_MM / 2 - 15.0),
        (config.logo_client_path,  _A4_LANDSCAPE_W_MM - 40.0),
    ]
    page_y = 0.0
    for path, x in slots:
        if not path or not os.path.isfile(path):
            continue
        pic = qc.QgsLayoutItemPicture(layout)
        pic.setPicturePath(path)
        pic.attemptSetSceneRect(qc.QgsLayoutRect(
            x, page_y + 2.0, 30.0, _TITLE_BAND_H_MM - 4.0,
            qc.QgsUnitTypes.LayoutMillimeters,
        ))
        layout.addLayoutItem(pic)


def _add_map_item(layout, *, page_index: int, layers, extent,
                  config: PdfExportConfig):
    qc = _qgis_core()
    body_y = _TITLE_BAND_H_MM + 2.0
    body_h = _A4_LANDSCAPE_H_MM - body_y - _MARGIN_MM
    body_x = _MARGIN_MM
    body_w = _A4_LANDSCAPE_W_MM - 2 * _MARGIN_MM

    map_item = qc.QgsLayoutItemMap(layout)
    map_item.attemptSetSceneRect(qc.QgsLayoutRect(
        body_x, body_y, body_w, body_h,
        qc.QgsUnitTypes.LayoutMillimeters,
    ))
    if extent is not None:
        map_item.setExtent(extent)
    if layers:
        map_item.setLayers(list(layers))
    layout.addLayoutItem(map_item)

    if config.show_coord_grid:
        try:
            grid = map_item.grid()
            grid.setEnabled(True)
            grid.setIntervalX(0.1)
            grid.setIntervalY(0.1)
            grid.setAnnotationEnabled(True)
        except AttributeError:
            pass

    if config.show_scale_bar:
        scale = qc.QgsLayoutItemScaleBar(layout)
        scale.setStyle("Single Box")
        scale.setLinkedMap(map_item)
        scale.applyDefaultSize()
        scale.attemptMove(qc.QgsLayoutPoint(
            body_x + 2.0, body_y + body_h - 12.0,
            qc.QgsUnitTypes.LayoutMillimeters,
        ))
        layout.addLayoutItem(scale)

    if config.show_legend:
        legend = qc.QgsLayoutItemLegend(layout)
        legend.setLinkedMap(map_item)
        legend.setAutoUpdateModel(True)
        legend.attemptMove(qc.QgsLayoutPoint(
            body_x + body_w - 60.0, body_y + 2.0,
            qc.QgsUnitTypes.LayoutMillimeters,
        ))
        layout.addLayoutItem(legend)


def _add_table_pages(layout, *, rows: List[LookaheadRow],
                     header_text: str, date_str: str,
                     config: PdfExportConfig):
    """Render the sequence table onto new pages. Uses fixed-height rows
    and splices manually to sidestep QgsLayoutItemManualTable quirks on
    large datasets; empirical tuning may happen in 17b on Martin Linge.
    """
    qc = _qgis_core()
    page_collection = layout.pageCollection()

    rows_per_page = 30
    n_pages = max(1, (len(rows) + rows_per_page - 1) // rows_per_page) if rows else 1

    for i in range(n_pages):
        page = qc.QgsLayoutItemPage(layout)
        page.setPageSize(
            qc.QgsLayoutSize(_A4_LANDSCAPE_W_MM, _A4_LANDSCAPE_H_MM,
                             qc.QgsUnitTypes.LayoutMillimeters)
        )
        page_collection.addPage(page)
        page_index = page_collection.pageCount() - 1

        _add_title_band(layout, page_index=page_index,
                        header_text=header_text, date_str=date_str,
                        config=config)

        chunk = rows[i * rows_per_page:(i + 1) * rows_per_page]
        _draw_table_block(layout, page_index=page_index, rows=chunk)


def _draw_table_block(layout, *, page_index: int, rows: List[LookaheadRow]):
    """Draw a simple table as a grid of QgsLayoutItemLabels. This is
    deliberately low-tech — QgsLayoutItemManualTable has known quirks
    with very tall tables and we prefer determinism over richness for
    v1. Tune cell heights and fonts in 17b smoke testing."""
    qc = _qgis_core()

    page_y_offset = sum(
        _A4_LANDSCAPE_H_MM
        for _ in range(page_index)
    )

    x0 = _MARGIN_MM
    y0 = page_y_offset + _TITLE_BAND_H_MM + 2.0
    row_h = 6.0
    header_h = 7.0

    # Header row
    x_cursor = x0
    for col_name, _, col_w in _TABLE_COLUMNS:
        label = qc.QgsLayoutItemLabel(layout)
        label.setText(col_name)
        try:
            font = label.font()
            font.setBold(True)
            font.setPointSize(9)
            label.setFont(font)
            label.setBackgroundEnabled(True)
            from qgis.PyQt.QtGui import QColor  # local import to keep top clean
            label.setBackgroundColor(QColor(255, 248, 168))
        except Exception:
            pass
        label.attemptSetSceneRect(qc.QgsLayoutRect(
            x_cursor, y0, col_w, header_h,
            qc.QgsUnitTypes.LayoutMillimeters,
        ))
        layout.addLayoutItem(label)
        x_cursor += col_w

    # Data rows
    for row_idx, row in enumerate(rows):
        x_cursor = x0
        y_cursor = y0 + header_h + row_idx * row_h
        for _col_name, key, col_w in _TABLE_COLUMNS:
            cell = qc.QgsLayoutItemLabel(layout)
            cell.setText(_cell_text(row, key))
            try:
                font = cell.font()
                font.setPointSize(8)
                cell.setFont(font)
            except AttributeError:
                pass
            cell.attemptSetSceneRect(qc.QgsLayoutRect(
                x_cursor, y_cursor, col_w, row_h,
                qc.QgsUnitTypes.LayoutMillimeters,
            ))
            layout.addLayoutItem(cell)
            x_cursor += col_w


def export_pdf(layout, output_path: str) -> Tuple[bool, Optional[str]]:
    """Render the layout to a PDF file. Returns (ok, error_message)."""
    qc = _qgis_core()
    exporter = qc.QgsLayoutExporter(layout)
    settings = qc.QgsLayoutExporter.PdfExportSettings()
    result = exporter.exportToPdf(output_path, settings)
    if result == qc.QgsLayoutExporter.Success:
        return True, None
    return False, f"QgsLayoutExporter error code {int(result)}"
