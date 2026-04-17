# Phase 8 — UI split + format selector + direction checkbox

**Size:** medium
**Risk:** medium (every signal connection touched)
**Blocks:** Phase 9 (cleanup relies on final UI structure)
**Blocked by:** Phases 5, 6, 7 (services must exist to be called from handlers)

## Goal

Shrink the dockwidget from ~2500-3500 lines (end of Phase 7) to its target **under 2000 lines** by extracting all UI handlers into focused modules. Add two new UI controls: the SPS format selector and the "Follow previous shooting direction" checkbox. Replace magic-string mode comparisons with enums.

## Files created

### `ui/__init__.py` (empty)

### `ui/constants.py`

```python
from enum import Enum

class AcquisitionMode(str, Enum):
    RACETRACK = "Racetrack"
    TEARDROP = "Teardrop"

class HeadingOption(str, Enum):
    LOW_TO_HIGH = "Low to High SP"
    HIGH_TO_LOW = "High to Low SP (Reciprocal)"

class StatusFilter(str, Enum):
    ALL = "All"
    TBA = "To Be Acquired"
    ACQUIRED = "Acquired"
    PENDING = "Pending"

# Line-attribute values — must match current field content to preserve saved-state compatibility
LINE_STATUS_TBA = "TO BE ACQUIRED"
LINE_STATUS_ACQUIRED = "ACQUIRED"
LINE_STATUS_PENDING = "PENDING"
```

Critical: `.value` for each enum member must equal the exact string currently used in comparisons. Grep confirms before editing. If the current code uses case-insensitive compares anywhere, update it to use enum-value compares (better) or keep `.lower()` normalization (safer for persisted state).

### `ui/progress.py`

```python
from contextlib import contextmanager
from qgis.PyQt.QtWidgets import QProgressDialog, QApplication
from qgis.PyQt.QtCore import Qt

@contextmanager
def progress_dialog(parent, label: str, maximum: int):
    dlg = QProgressDialog(label, "Cancel", 0, maximum, parent)
    dlg.setWindowModality(Qt.WindowModal)
    dlg.setMinimumDuration(200)  # don't flash for fast ops
    dlg.show()
    QApplication.processEvents()
    try:
        yield dlg
    finally:
        dlg.close()
```

### `ui/error_dialog.py`

```python
import logging
from qgis.PyQt.QtWidgets import QMessageBox

log = logging.getLogger("obn_planner.ui")

def show_error(parent, title: str, message: str, exc: Exception | None = None):
    if exc:
        log.exception(f"{title}: {message}")
    else:
        log.error(f"{title}: {message}")
    QMessageBox.critical(parent, title, message)

def show_warning(parent, title: str, message: str):
    log.warning(f"{title}: {message}")
    QMessageBox.warning(parent, title, message)
```

### `ui/dialogs/sequence_edit_dialog.py`

Move `sequence_edit_dialog.py` from repo root. Update import in dockwidget and in `services/simulation_service.py` (if the service references `custom_deepcopy` from that module).

Extract the XLSX export body (`:500-574`) into `io/xlsx_export.py`:

```python
# io/xlsx_export.py
def export_sequence_to_xlsx(path: str, headers: list[str], rows: list[list]):
    import xlsxwriter
    wb = xlsxwriter.Workbook(path)
    ws = wb.add_worksheet("Sequence")
    bold = wb.add_format({"bold": True})
    for col, h in enumerate(headers):
        ws.write(0, col, h, bold)
    for row_idx, row in enumerate(rows, start=1):
        for col, val in enumerate(row):
            ws.write(row_idx, col, val)
    for col in range(len(headers)):
        width = max((len(str(r[col])) for r in [headers] + rows), default=10) + 2
        ws.set_column(col, col, width)
    wb.close()
```

The dialog's export button calls `export_sequence_to_xlsx(...)` — pure IO, no Qt dependency.

### `ui/handlers/` package

Each handler is a free function taking the dockwidget as first arg.

| File | Handlers |
|---|---|
| `import_handlers.py` | `handle_sps_import(dw)` — includes format selector logic |
| `generate_handlers.py` | `handle_calculate_headings(dw)`, `handle_generate_lines(dw)`, `handle_calculate_deviations(dw)` |
| `simulation_handlers.py` | `handle_run_simulation(dw)`, `handle_edit_finalize(dw)` |
| `status_handlers.py` | `handle_apply_filter(dw)`, `handle_mark_acquired(dw)`, `handle_mark_tba(dw)`, `handle_mark_pending(dw)` |

Example:

```python
# ui/handlers/simulation_handlers.py
def handle_run_simulation(dw):
    log.info("Run Simulation clicked.")
    QApplication.setOverrideCursor(Qt.WaitCursor)
    dw._last_run = None
    try:
        params = SimulationParams.from_ui(dw)
        service = SimulationService(iface=dw.iface)
        dw._last_run = service.run(params)
        dw._display_results(dw._last_run)
        dw.editFinalizeButton.setEnabled(True)
    except ValueError as e:
        show_warning(dw, "Simulation failed", str(e))
    finally:
        QApplication.restoreOverrideCursor()
```

Signal connections in the dockwidget switch from bound methods to lambdas:

```python
# Before (dockwidget __init__)
self.runSimulationButton.clicked.connect(self.handle_run_simulation)

# After
from .ui.handlers.simulation_handlers import handle_run_simulation
self.runSimulationButton.clicked.connect(lambda: handle_run_simulation(self))
```

## New UI controls

### SPS format selector (for Phase 3 feature)

Placement: next to the SPS Import button. Could be a small combo box or a settings dropdown.

```python
# obn_planner_dockwidget_base.ui changes:
# - Add QComboBox "spsFormatComboBox" near importSpsButton
# - Items: "Auto-detect", "SPS 1.0", "SPS 2.1 (Shell)", "SPS 2.1 + direction (Martin Linge)",
#          "PXGEO (.s01)", "TGS (.s01)", "SAE", "Custom..."
```

Handler behavior (`ui/handlers/import_handlers.py`):

```python
def handle_sps_import(dw):
    format_choice = dw.spsFormatComboBox.currentText()
    if format_choice == "Auto-detect":
        spec = None   # parse_sps auto-detects
    elif format_choice == "Custom...":
        spec = _open_custom_spec_dialog(dw)     # Phase 8 deferred or simplified version
        if spec is None:
            return
    else:
        spec = SPS_SPECS[format_choice]
    # proceed with import using the chosen spec
    result = parse_sps(path, spec=spec)
    ...
    # feedback: always show detected/used spec in a status label
    dw.spsStatusLabel.setText(f"Imported {len(result.records)} records using {result.spec_used.name} "
                              f"({result.detection_confidence:.0%} confidence)")
```

"Custom..." can open a small dialog where the user enters slice positions for each field. Implementation is optional in Phase 8; if deferred, grey out the menu entry and log "Custom spec editing not yet implemented."

### "Follow previous shooting direction" checkbox (for Phase 4+6 feature)

Placement: in the simulation parameters group, next to the Acquisition Mode combo box.

```python
# obn_planner_dockwidget_base.ui changes:
# - Add QCheckBox "followPreviousDirectionCheckBox"
#   label: "Follow previous shooting direction"
#   tooltip: "When enabled, each line is shot in the direction stored in its PREV_DIRECTION
#            field (from the SPS file). Requires SPS format that carries direction data."
```

`SimulationParams.from_ui(dw)` reads the checkbox:

```python
follow_previous_direction = dw.followPreviousDirectionCheckBox.isChecked()
```

Enable/disable logic:

```python
# in the dockwidget __init__, after layer binding:
def _update_direction_checkbox_state(self):
    lines_layer = self.generated_lines_layer
    has_direction = (lines_layer is not None
                     and lines_layer.fields().indexOf("PREV_DIRECTION") >= 0)
    self.followPreviousDirectionCheckBox.setEnabled(has_direction)
    if not has_direction:
        self.followPreviousDirectionCheckBox.setChecked(False)
        self.followPreviousDirectionCheckBox.setToolTip(
            "Disabled: Generate Lines first from an SPS file that includes direction data.")
```

Hook this to re-run whenever `Generate Lines` completes or the lines layer changes.

## UI polish (light)

Permitted scope per user's earlier answer ("Minor UI improvements OK"):

1. **Progress indication** on `handle_generate_lines` and `handle_calculate_deviations` (currently no progress; user sees frozen QGIS). Use `ui/progress.py`.
2. **Unified error dialogs** — every `log.error(...) + QMessageBox.critical(...)` pair replaced with `show_error(...)` from `ui/error_dialog.py`.
3. **Status feedback** — small `QLabel` near SPS Import button showing detected spec after import.
4. **Tooltips** on the two new controls (SPS format combo, direction checkbox) explaining when they apply.

**Not permitted:** layout redesign, control renaming, tab reorganization. Adding two new controls is OK.

## Magic-string replacement

Grep and replace:

| Legacy string | Replacement |
|---|---|
| `"Racetrack"` | `AcquisitionMode.RACETRACK` (or `AcquisitionMode.RACETRACK.value` at boundaries) |
| `"Teardrop"` | `AcquisitionMode.TEARDROP` |
| `"Low to High SP"` | `HeadingOption.LOW_TO_HIGH.value` |
| `"High to Low SP (Reciprocal)"` | `HeadingOption.HIGH_TO_LOW.value` |
| `"To Be Acquired"` (in filters) | `StatusFilter.TBA.value` |
| `"TO BE ACQUIRED"` (in field values) | `LINE_STATUS_TBA` |

## Tests

### `test/test_ui_constants.py` (new, pure Python)

- `test_acquisition_mode_values_stable` — enum values match the strings persisted in current test/real data.
- `test_heading_option_values_stable` — same.
- `test_line_status_values_case` — `LINE_STATUS_TBA == "TO BE ACQUIRED"` (uppercase matches current field content).

No handler tests (UI glue — too costly to set up; services tests from Phases 5-7 cover logic).

## Verify

1. Every button still works. Manual smoke test (see `SMOKE_TEST.md`).
2. SPS format combo: select each format option, import a file compatible with it, confirm it's used. Test Auto-detect on Martin Linge → picks SPS 2.1 + direction; on PXGEO → picks PXGEO.
3. Direction checkbox: greyed when no PREV_DIRECTION field; enabled when present. Toggle and run simulation — sequence behavior matches Phase 6 behavior.
4. `grep '"Racetrack"\|"Teardrop"'` outside `ui/constants.py` → 0 matches.
5. `wc -l obn_planner_dockwidget.py` → **under 2000**.

## Rollback

Per-handler commit granularity. Revert any single handler extraction independently. Revert new UI controls by removing them from the .ui file and reverting the handler code that reads them.

## Risks and unknowns

- **Saved-state compatibility** — if QGIS project files reference acquisition mode by literal string, enum `.value` must match. Old projects must still load without missing-field errors. VERIFY by loading a pre-refactor `.qgz` file after Phase 8.
- **`lambda: handle_x(self)` gotcha** — lambdas capture `self` by reference. If the dockwidget is ever destroyed while a handler is still running, the lambda dangles. QGIS usually shuts down cleanly, but verify Plugin Reloader behavior. Alternative: use `functools.partial(handle_x, self)`.
- **Custom spec dialog** — deferring or simplifying is acceptable. Don't ship a half-working dialog.
- **Checkbox state on project load** — when a user opens a saved QGIS project, the checkbox state should reset based on the current `Generated_Survey_Lines` layer's fields. Hook to the layer change signal.
- **Tooltip localization** — `i18n/` has only a stub Afrikaans file. Tooltips currently hardcoded English. Phase 9 decides whether to wrap in `self.tr(...)`.

## Hard Stop Gate

Phase 8 is complete when:
1. All tests green.
2. `obn_planner_dockwidget.py` under 2000 lines.
3. Every workflow click-tested end-to-end.
4. SPS format selector and direction checkbox both work correctly.
5. No magic-string mode comparisons outside `ui/constants.py`.

**Claude MUST stop after Phase 8 and await explicit "proceed to Phase 9" from user.**
