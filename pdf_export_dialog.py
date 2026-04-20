# -*- coding: utf-8 -*-
"""
48-hour Lookahead preview dialog (Phase 17b).

Two dialogs in this module:

- `ReportSetupDialog`: one-time setup for the rarely-changed defaults
  (vessel name, project/client, default hours, header template, 3
  logo paths). Persists to QSettings under the "obn_planner/pdf/*"
  namespace. The chief fills this once per vessel and effectively
  never again.

- `PdfExportDialog`: the per-report workspace. Shows survey name +
  layer checkboxes + embedded map canvas + Render PDF button. The
  chief adjusts layers and extent, clicks Render, and a PDF is
  written. Opens ReportSetupDialog on "Report setup..." button if
  the defaults need editing.

Why split: the user explicitly asked for a one-time setup separate
from the per-export flow. Report details (vessel/logos/etc.) rarely
change; layers and survey-name change every export.
"""
from __future__ import annotations

import logging
import os

from qgis.core import QgsProject
from qgis.gui import QgsMapCanvas, QgsMapToolPan
from qgis.PyQt import QtCore, QtWidgets
from qgis.PyQt.QtCore import QDate, QSettings, Qt
from qgis.PyQt.QtGui import QDesktopServices
from qgis.PyQt.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
)

try:
    from .services.pdf_export import (
        PdfExportConfig,
        _expand_extent_to_aspect,
        build_lookahead_layout,
        compute_output_filename,
        export_pdf,
        rows_from_optimized_path_layer,
    )
except ImportError:  # pragma: no cover
    from services.pdf_export import (  # type: ignore
        PdfExportConfig,
        _expand_extent_to_aspect,
        build_lookahead_layout,
        compute_output_filename,
        export_pdf,
        rows_from_optimized_path_layer,
    )

# Phase 17d.2: title band shrunk from 26 -> 18 mm. Mirror the PDF map
# body aspect so the preview canvas shows what the PDF will actually
# render. Body geometry: width 249 mm (297 - 10 - 18 - 60 - 10) by
# height 180 mm (210 - 18 - 2 - 10) -> aspect ~1.38 when the legend is
# enabled.
_PDF_BODY_ASPECT = (297.0 - 10.0 - 18.0 - 60.0 - 10.0) / \
                   (210.0 - 18.0 - 2.0 - 10.0)

log = logging.getLogger("obn_planner")

_QS_PREFIX = "pdf/"
_DEFAULT_HEADER = "{vessel} {hours}Hrs Look Ahead \u2014 {project}"


def _settings() -> QSettings:
    """Single QSettings instance for all PDF-related persistence."""
    return QSettings("obn_planner", "pdf_export")


# ---------------------------------------------------------------------------
# Setup dialog — one-time defaults
# ---------------------------------------------------------------------------


class ReportSetupDialog(QDialog):
    """Modal for editing the rarely-changed report defaults.

    Saves to QSettings on OK, discards on Cancel. The dialog reads the
    current values on open so edits are additive, not overwrites from
    empty state.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Report setup (defaults)")
        self.setModal(True)
        self.resize(520, 360)

        form = QFormLayout()

        self.vesselEdit = QLineEdit()
        self.vesselEdit.setPlaceholderText("e.g. Sanco Star")
        self.projectEdit = QLineEdit()
        self.projectEdit.setPlaceholderText("e.g. Petrobras MMBC \u2014 3D OBN")
        self.hoursSpin = QSpinBox()
        self.hoursSpin.setRange(1, 999)
        self.hoursSpin.setSuffix(" hrs")
        self.headerEdit = QLineEdit()
        self.headerEdit.setPlaceholderText(_DEFAULT_HEADER)
        self.headerEdit.setToolTip(
            "Placeholders: {vessel}, {project}, {hours}, {date}, {survey}"
        )

        form.addRow("Vessel name:", self.vesselEdit)
        form.addRow("Project / client:", self.projectEdit)
        form.addRow("Default hours:", self.hoursSpin)
        form.addRow("Header template:", self.headerEdit)

        self.logoVesselEdit,  btnLV = self._logo_row("Vessel logo")
        self.logoCompanyEdit, btnLC = self._logo_row("Company logo")
        self.logoClientEdit,  btnLX = self._logo_row("Client logo")
        form.addRow("Vessel logo:", self._bundle(self.logoVesselEdit, btnLV))
        form.addRow("Company logo:", self._bundle(self.logoCompanyEdit, btnLC))
        form.addRow("Client logo:", self._bundle(self.logoClientEdit, btnLX))

        hint = QLabel(
            "These values are saved once and re-used for every report. "
            "Only the Survey name changes per export."
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #555;")

        btns = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        btns.button(QDialogButtonBox.Save).setText("Save defaults")
        btns.accepted.connect(self._on_accept)
        btns.rejected.connect(self.reject)

        root = QVBoxLayout(self)
        root.addLayout(form)
        root.addWidget(hint)
        root.addStretch(1)
        root.addWidget(btns)

        self._load()

    def _logo_row(self, label: str):
        edit = QLineEdit()
        edit.setPlaceholderText("(no logo)")
        edit.setReadOnly(True)
        btn = QPushButton("Browse\u2026")
        btn.clicked.connect(lambda _=False, e=edit, l=label: self._pick_logo(e, l))
        return edit, btn

    def _bundle(self, edit, btn):
        wrap = QtWidgets.QWidget()
        lay = QHBoxLayout(wrap)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(edit, stretch=1)
        lay.addWidget(btn)
        return wrap

    def _pick_logo(self, edit: QLineEdit, label: str):
        s = _settings()
        last = edit.text() or s.value(_QS_PREFIX + "last_logo_dir", "", type=str)
        start_dir = os.path.dirname(last) if last else ""
        path, _ = QFileDialog.getOpenFileName(
            self, f"Pick {label}", start_dir,
            "Images (*.png *.jpg *.jpeg *.svg)",
        )
        if path:
            edit.setText(path)
            s.setValue(_QS_PREFIX + "last_logo_dir", os.path.dirname(path))

    def _load(self):
        s = _settings()
        self.vesselEdit.setText(s.value(_QS_PREFIX + "vessel_name", "", type=str))
        self.projectEdit.setText(s.value(_QS_PREFIX + "project_name", "", type=str))
        self.hoursSpin.setValue(int(s.value(_QS_PREFIX + "hours", 48, type=int)))
        self.headerEdit.setText(
            s.value(_QS_PREFIX + "header_template", _DEFAULT_HEADER, type=str)
        )
        self.logoVesselEdit.setText(
            s.value(_QS_PREFIX + "logo_vessel", "", type=str)
        )
        self.logoCompanyEdit.setText(
            s.value(_QS_PREFIX + "logo_company", "", type=str)
        )
        self.logoClientEdit.setText(
            s.value(_QS_PREFIX + "logo_client", "", type=str)
        )

    def _on_accept(self):
        s = _settings()
        s.setValue(_QS_PREFIX + "vessel_name", self.vesselEdit.text().strip())
        s.setValue(_QS_PREFIX + "project_name", self.projectEdit.text().strip())
        s.setValue(_QS_PREFIX + "hours", self.hoursSpin.value())
        s.setValue(_QS_PREFIX + "header_template",
                   self.headerEdit.text().strip() or _DEFAULT_HEADER)
        s.setValue(_QS_PREFIX + "logo_vessel", self.logoVesselEdit.text().strip())
        s.setValue(_QS_PREFIX + "logo_company", self.logoCompanyEdit.text().strip())
        s.setValue(_QS_PREFIX + "logo_client", self.logoClientEdit.text().strip())
        s.sync()
        self.accept()


# ---------------------------------------------------------------------------
# Per-export preview + render dialog
# ---------------------------------------------------------------------------


class PdfExportDialog(QDialog):
    """Preview + export dialog for the 48-hour Lookahead PDF.

    Constructor arguments:
      parent:         the QGIS plugin dock (for modality).
      project:        the active QgsProject.
      optimized_path_layer: memory layer with simulation timing.
      generated_lines_layer: memory layer with Operation/FGSP/LGSP.
    """

    def __init__(self, parent, project, optimized_path_layer,
                 generated_lines_layer, start_sequence_number: int = 1):
        super().__init__(parent)
        self.setWindowTitle("Create 48-hour Lookahead Report")
        self.setModal(True)
        self.resize(1100, 700)

        self._project = project
        self._opt_layer = optimized_path_layer
        self._gen_layer = generated_lines_layer
        self._start_seq = int(start_sequence_number or 1)

        self._build_ui()
        self._load_per_export_settings()
        self._refresh_setup_summary()
        self._populate_layers_panel()
        self._populate_fit_layer_combo()
        self._sync_canvas_to_selection()

    # --- UI ---------------------------------------------------------------

    def _build_ui(self):
        root = QHBoxLayout(self)

        left = QVBoxLayout()
        left.setSpacing(6)

        # Setup summary at top — shows current defaults + edit button
        gb_setup = QGroupBox("Report defaults")
        setup_lay = QHBoxLayout(gb_setup)
        self.setupSummaryLabel = QLabel("\u2014")
        self.setupSummaryLabel.setWordWrap(True)
        self.setupSummaryLabel.setStyleSheet("color: #333;")
        self.setupBtn = QPushButton("Setup\u2026")
        self.setupBtn.setToolTip(
            "Edit the one-time report defaults (vessel, project, logos, "
            "header template). Saved for future reports."
        )
        self.setupBtn.clicked.connect(self._open_setup_dialog)
        setup_lay.addWidget(self.setupSummaryLabel, stretch=1)
        setup_lay.addWidget(self.setupBtn)
        left.addWidget(gb_setup)

        # Per-export: survey name only (everything else is saved defaults)
        gb_export = QGroupBox("This report")
        form = QFormLayout(gb_export)
        self.surveyEdit = QLineEdit()
        self.surveyEdit.setPlaceholderText("e.g. 4D TVD")
        form.addRow("Survey name:", self.surveyEdit)
        self.surveyEdit.editingFinished.connect(self._save_per_export_settings)
        left.addWidget(gb_export)

        # Layers panel — 2 columns: [checkbox + real name] | display name
        # Phase 17d.3/.5: three-column reorderable layer tree.
        #   col 0: checkbox (show on map) + layer name
        #   col 1: editable display name for the legend
        #   col 2: checkbox (show in legend)
        # Row order controls the order layers appear in the PDF
        # legend; chief can drag-drop rows OR use the ↑ / ↓ buttons.
        gb_layers = QGroupBox("Layers to include in map")
        lay_layers = QVBoxLayout(gb_layers)
        self.layerTree = QTreeWidget()
        self.layerTree.setColumnCount(3)
        self.layerTree.setHeaderLabels(["Layer", "Display as (legend)", "In legend"])
        # Phase 17d.6: groups are top-level rows, member layers are
        # indented children. setRootIsDecorated(True) shows expand
        # arrows so the chief can collapse large groups.
        self.layerTree.setRootIsDecorated(True)
        self.layerTree.setAlternatingRowColors(True)
        self.layerTree.setEditTriggers(
            QAbstractItemView.DoubleClicked | QAbstractItemView.EditKeyPressed
            | QAbstractItemView.SelectedClicked
        )
        # Drag-drop reordering within the tree.
        self.layerTree.setDragEnabled(True)
        self.layerTree.setAcceptDrops(True)
        self.layerTree.setDropIndicatorShown(True)
        self.layerTree.setDragDropMode(QAbstractItemView.InternalMove)
        self.layerTree.setSelectionMode(QAbstractItemView.SingleSelection)
        hdr = self.layerTree.header()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(1, QHeaderView.Stretch)
        hdr.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.layerTree.setToolTip(
            "Col 1: tick = show on map. Col 2: rename how a layer appears "
            "in the PDF legend (double-click to edit). Col 3: tick = "
            "include in legend. Drag rows or use the arrow buttons to "
            "reorder legend entries. The main QGIS project is not affected."
        )
        lay_layers.addWidget(self.layerTree)

        # Reorder toolbar: ↑ / ↓ buttons.
        reorder_row = QHBoxLayout()
        self.moveUpBtn = QPushButton("\u25b2 Up")
        self.moveDownBtn = QPushButton("\u25bc Down")
        self.moveUpBtn.setToolTip("Move the selected layer up in the legend order.")
        self.moveDownBtn.setToolTip("Move the selected layer down in the legend order.")
        self.moveUpBtn.clicked.connect(lambda: self._move_selected_layer(-1))
        self.moveDownBtn.clicked.connect(lambda: self._move_selected_layer(+1))
        reorder_row.addStretch(1)
        reorder_row.addWidget(self.moveUpBtn)
        reorder_row.addWidget(self.moveDownBtn)
        lay_layers.addLayout(reorder_row)

        left.addWidget(gb_layers, stretch=1)

        # Map controls
        gb_map = QGroupBox("Map controls")
        lay_map = QFormLayout(gb_map)
        self.fitLayerCombo = QComboBox()
        self.fitLayerCombo.setToolTip(
            "Snap the map extent to this layer's bounding box + 10% padding."
        )
        self.cbNorth = QCheckBox("North arrow")
        self.cbScale = QCheckBox("Scale bar")
        self.cbLegend = QCheckBox("Legend")
        for cb in (self.cbNorth, self.cbScale, self.cbLegend):
            cb.setChecked(True)
            cb.toggled.connect(lambda _v: self._save_per_export_settings())
        deco = QHBoxLayout()
        deco.addWidget(self.cbNorth)
        deco.addWidget(self.cbScale)
        deco.addWidget(self.cbLegend)
        deco_wrap = QtWidgets.QWidget()
        deco_wrap.setLayout(deco)
        lay_map.addRow("Fit to:", self.fitLayerCombo)
        lay_map.addRow("Decorations:", deco_wrap)

        # Phase 17d.3: coord-grid style (off / light / normal).
        self.gridStyleCombo = QComboBox()
        self.gridStyleCombo.addItem("Off", "off")
        self.gridStyleCombo.addItem("Light (recommended)", "light")
        self.gridStyleCombo.addItem("Normal", "normal")
        self.gridStyleCombo.setToolTip(
            "Coordinate grid intensity. 'Light' keeps the grid visible "
            "but lets the survey plan show through."
        )
        self.gridStyleCombo.currentIndexChanged.connect(
            lambda _i: self._save_per_export_settings()
        )
        lay_map.addRow("Grid:", self.gridStyleCombo)

        self.renameGroupsBtn = QPushButton("Rename legend groups\u2026")
        self.renameGroupsBtn.setToolTip(
            "Rename or hide group headings shown in the PDF legend "
            "(e.g. rename \"SAE GIS Shapefiles\" to \"Assets\", or "
            "blank-out a name to flatten the group)."
        )
        self.renameGroupsBtn.clicked.connect(self._open_group_rename_dialog)
        lay_map.addRow("", self.renameGroupsBtn)

        left.addWidget(gb_map)

        left_wrap = QtWidgets.QWidget()
        left_wrap.setLayout(left)
        left_wrap.setMaximumWidth(420)

        # Map canvas
        self.mapCanvas = QgsMapCanvas()
        self.mapCanvas.setCanvasColor(Qt.white)
        self.mapCanvas.enableAntiAliasing(True)
        self._panTool = QgsMapToolPan(self.mapCanvas)
        self.mapCanvas.setMapTool(self._panTool)

        btnRow = QHBoxLayout()
        btnRow.addStretch(1)
        self.renderBtn = QPushButton("Render PDF\u2026")
        self.renderBtn.setDefault(True)
        self.cancelBtn = QPushButton("Cancel")
        btnRow.addWidget(self.cancelBtn)
        btnRow.addWidget(self.renderBtn)

        right_wrap = QtWidgets.QWidget()
        right_lay = QVBoxLayout(right_wrap)
        right_lay.addWidget(self.mapCanvas, stretch=1)
        right_lay.addLayout(btnRow)

        root.addWidget(left_wrap)
        root.addWidget(right_wrap, stretch=1)

        self.cancelBtn.clicked.connect(self.reject)
        self.renderBtn.clicked.connect(self._on_render_clicked)
        self.layerTree.itemChanged.connect(self._on_layer_item_changed)
        self.fitLayerCombo.currentIndexChanged.connect(self._on_fit_layer_changed)
        # Persist order after drag-drop reordering.
        self.layerTree.model().rowsMoved.connect(
            lambda *_args: self._persist_layer_order()
        )

    # --- Setup summary ----------------------------------------------------

    def _open_setup_dialog(self):
        dlg = ReportSetupDialog(self)
        if dlg.exec_() == QDialog.Accepted:
            self._refresh_setup_summary()

    def _refresh_setup_summary(self):
        s = _settings()
        vessel = s.value(_QS_PREFIX + "vessel_name", "", type=str) or "(no vessel)"
        project = s.value(_QS_PREFIX + "project_name", "", type=str) or "(no project)"
        hours = int(s.value(_QS_PREFIX + "hours", 48, type=int))
        logos_configured = sum(
            1 for key in ("logo_vessel", "logo_company", "logo_client")
            if (s.value(_QS_PREFIX + key, "", type=str) or "").strip()
        )
        text = (
            f"Vessel: <b>{vessel}</b> &middot; "
            f"Project: <b>{project}</b> &middot; "
            f"Hours: <b>{hours}</b> &middot; "
            f"Logos: <b>{logos_configured}/3</b>"
        )
        self.setupSummaryLabel.setText(text)

    # --- Per-export persistence (survey name + map controls) --------------

    def _load_per_export_settings(self):
        s = _settings()
        self.surveyEdit.setText(s.value(_QS_PREFIX + "survey_name", "", type=str))
        self.cbNorth.setChecked(s.value(_QS_PREFIX + "show_north", True, type=bool))
        self.cbScale.setChecked(s.value(_QS_PREFIX + "show_scale", True, type=bool))
        self.cbLegend.setChecked(s.value(_QS_PREFIX + "show_legend", True, type=bool))
        grid_style = s.value(_QS_PREFIX + "grid_style", "light", type=str)
        idx = self.gridStyleCombo.findData(grid_style)
        if idx >= 0:
            self.gridStyleCombo.setCurrentIndex(idx)

    def _save_per_export_settings(self):
        s = _settings()
        s.setValue(_QS_PREFIX + "survey_name", self.surveyEdit.text().strip())
        s.setValue(_QS_PREFIX + "show_north", self.cbNorth.isChecked())
        s.setValue(_QS_PREFIX + "show_scale", self.cbScale.isChecked())
        s.setValue(_QS_PREFIX + "show_legend", self.cbLegend.isChecked())
        s.setValue(_QS_PREFIX + "grid_style",
                   self.gridStyleCombo.currentData() or "light")

    # --- Layers + canvas --------------------------------------------------

    def _all_project_layers(self):
        return list(self._project.mapLayers().values())

    def _populate_layers_panel(self):
        self.layerTree.blockSignals(True)
        self.layerTree.clear()
        layer_tree = self._project.layerTreeRoot()

        # Phase 17d.6: enumerate top-level children of the project
        # layer tree. Each top-level node is either a QgsLayerTreeGroup
        # or a QgsLayerTreeLayer; both become reorderable top-level
        # rows in our QTreeWidget. Groups expand to show their member
        # layers (indented, non-draggable; their own checkboxes + display
        # name still work).
        top_entries = []  # list of (key, kind, node)
        for child in layer_tree.children():
            if hasattr(child, "layerId"):
                top_entries.append(("l:" + child.layerId(), "layer", child))
            elif hasattr(child, "children"):
                top_entries.append(("g:" + child.name(), "group", child))

        # Apply saved legend order to the top-level entries.
        saved_order = self._load_layer_order()
        if saved_order:
            by_key = {e[0]: e for e in top_entries}
            ordered = []
            for key in saved_order:
                # Legacy support: pre-17d.6 saved bare layer_ids.
                candidates = [key]
                if not key.startswith(("l:", "g:")):
                    candidates = ["l:" + key]
                for k in candidates:
                    if k in by_key:
                        ordered.append(by_key.pop(k))
                        break
            ordered.extend(by_key.values())
            top_entries = ordered

        for key, kind, node in top_entries:
            if kind == "layer":
                layer = self._project.mapLayer(node.layerId())
                if layer is None:
                    continue
                item = self._build_layer_row(layer, key, draggable=True)
                self.layerTree.addTopLevelItem(item)
            else:  # group
                item = self._build_group_row(node, key)
                self.layerTree.addTopLevelItem(item)
                # Add member layers as children, non-draggable.
                for child in node.children():
                    if not hasattr(child, "layerId"):
                        continue
                    lyr = self._project.mapLayer(child.layerId())
                    if lyr is None:
                        continue
                    sub = self._build_layer_row(
                        lyr, "l:" + lyr.id(), draggable=False
                    )
                    item.addChild(sub)
                item.setExpanded(True)

        self.layerTree.blockSignals(False)

    def _build_layer_row(self, layer, key: str, *, draggable: bool):
        """QTreeWidgetItem for an individual layer row."""
        s = _settings()
        lid = layer.id()
        override = s.value(
            _QS_PREFIX + "display_names/" + lid, "", type=str
        )
        hide_in_legend = s.value(
            _QS_PREFIX + "hidden_from_legend/" + lid, False, type=bool
        )
        item = QTreeWidgetItem([layer.name(), override or "", ""])
        flags = (Qt.ItemIsEnabled | Qt.ItemIsSelectable
                 | Qt.ItemIsUserCheckable | Qt.ItemIsEditable)
        if draggable:
            flags |= Qt.ItemIsDragEnabled
        item.setFlags(flags)
        layer_tree = self._project.layerTreeRoot()
        node = layer_tree.findLayer(lid)
        visible = True if node is None else bool(node.isVisible())
        item.setCheckState(0, Qt.Checked if visible else Qt.Unchecked)
        item.setCheckState(
            2, Qt.Unchecked if hide_in_legend else Qt.Checked
        )
        item.setData(0, Qt.UserRole, key)
        return item

    def _build_group_row(self, group_node, key: str):
        """QTreeWidgetItem for a group row — reorderable, bold label,
        no per-row on-map / in-legend checkboxes (use child rows)."""
        name = group_node.name()
        item = QTreeWidgetItem([f"[Group] {name}", "", ""])
        # Group rows are draggable but not drop targets (drop goes
        # between rows), and not editable — renaming happens in the
        # dedicated 'Rename legend groups…' modal.
        item.setFlags(
            Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsDragEnabled
        )
        # Visual distinction: bold font for the group name column.
        try:
            f = item.font(0)
            f.setBold(True)
            item.setFont(0, f)
        except Exception:  # noqa: BLE001
            pass
        item.setData(0, Qt.UserRole, key)
        return item

    # ---------------- Per-project fit-layer helpers ----------------------

    def _project_scope_key(self) -> str:
        """Return a short stable key for the current project suitable
        for QSettings subgrouping. Falls back to 'default' for
        untitled projects."""
        try:
            path = self._project.fileName() or ""
        except Exception:  # noqa: BLE001
            path = ""
        if not path:
            return "default"
        base = os.path.basename(path)
        # Strip extension, collapse non-word chars, cap length.
        name, _ext = os.path.splitext(base)
        safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in name)
        return safe[:60] or "default"

    def _fit_layer_settings_key(self) -> str:
        """Per-project QSettings key. Scoped on the project's basename
        so each survey remembers its own fit layer independently."""
        return f"{_QS_PREFIX}fit_layer/{self._project_scope_key()}"

    def _populate_fit_layer_combo(self):
        self.fitLayerCombo.blockSignals(True)
        self.fitLayerCombo.clear()
        for layer in self._all_project_layers():
            self.fitLayerCombo.addItem(layer.name(), layer.id())
        s = _settings()
        # Per-project first, then global fallback.
        remembered = s.value(self._fit_layer_settings_key(), "", type=str)
        if not remembered:
            remembered = s.value(_QS_PREFIX + "fit_layer_id", "", type=str)
        if remembered:
            idx = self.fitLayerCombo.findData(remembered)
            if idx >= 0:
                self.fitLayerCombo.setCurrentIndex(idx)
        self.fitLayerCombo.blockSignals(False)

    # ---- Key helpers for the layer tree ------------------------------------
    #
    # Phase 17d.6 made the tree mixed — top-level rows are either groups
    # (key "g:<name>") or standalone layers ("l:<id>"), and member layers
    # of a group appear as INDENTED CHILD rows (also keyed "l:<id>"). The
    # helpers below abstract both layouts so every consumer handles both
    # top-level and nested layer rows uniformly.

    @staticmethod
    def _row_layer_id(item):
        """Return the layer_id from an item's UserRole, or None if the
        item is a group row. Accepts legacy bare layer_id (pre-17d.6)."""
        key = item.data(0, Qt.UserRole)
        if not key:
            return None
        if key.startswith("l:"):
            return key[2:]
        if key.startswith("g:"):
            return None
        return key  # legacy format — plain layer_id

    def _iter_layer_items(self):
        """Yield every (item, layer_id) pair in the tree — both
        top-level standalone layers AND member layers nested under
        group rows. Skips group rows themselves."""
        for i in range(self.layerTree.topLevelItemCount()):
            top = self.layerTree.topLevelItem(i)
            lid = self._row_layer_id(top)
            if lid is not None:
                yield top, lid
            for j in range(top.childCount()):
                child = top.child(j)
                clid = self._row_layer_id(child)
                if clid is not None:
                    yield child, clid

    def _selected_layers(self):
        layers = []
        for item, lid in self._iter_layer_items():
            if item.checkState(0) == Qt.Checked:
                layer = self._project.mapLayer(lid)
                if layer is not None:
                    layers.append(layer)
        return layers

    def _layer_display_overrides(self) -> dict:
        """Return {layer_id: display_name} for layers that have a
        non-empty override typed into the second column."""
        overrides = {}
        for item, lid in self._iter_layer_items():
            name = (item.text(1) or "").strip()
            if lid and name:
                overrides[lid] = name
        return overrides

    def _on_layer_item_changed(self, item, column):
        """Handle checkbox toggles (col 0, col 2) and display-name edits (col 1).
        Group rows are skipped for per-layer settings — their own
        "Rename legend groups…" modal handles them."""
        lid = self._row_layer_id(item)
        if column == 1:
            if lid:
                new_name = (item.text(1) or "").strip()
                _settings().setValue(
                    _QS_PREFIX + "display_names/" + lid, new_name
                )
            return
        if column == 2:
            if lid:
                hidden = item.checkState(2) != Qt.Checked
                _settings().setValue(
                    _QS_PREFIX + "hidden_from_legend/" + lid, hidden
                )
            return
        # Column 0: checkbox changed -> resync canvas.
        self._sync_canvas_to_selection()

    def _move_selected_layer(self, direction: int):
        """Move the currently-selected TOP-LEVEL row up (-1) or down (+1).
        Child rows (member layers inside groups) are not reorderable
        individually; reorder the whole group instead.
        Persists the new order per-project on success."""
        items = self.layerTree.selectedItems()
        if not items:
            return
        item = items[0]
        if item.parent() is not None:
            # Child row — not reorderable on its own.
            return
        index = self.layerTree.indexOfTopLevelItem(item)
        if index < 0:
            return
        new_index = index + direction
        if new_index < 0 or new_index >= self.layerTree.topLevelItemCount():
            return
        # Take + reinsert preserves children and check states.
        self.layerTree.blockSignals(True)
        # Preserve expanded state of groups across take+insert.
        was_expanded = item.isExpanded()
        taken = self.layerTree.takeTopLevelItem(index)
        self.layerTree.insertTopLevelItem(new_index, taken)
        if was_expanded:
            taken.setExpanded(True)
        self.layerTree.setCurrentItem(taken)
        self.layerTree.blockSignals(False)
        self._persist_layer_order()

    def _persist_layer_order(self):
        """Save the current layer-tree order under the per-project key."""
        order = []
        for i in range(self.layerTree.topLevelItemCount()):
            item = self.layerTree.topLevelItem(i)
            lid = item.data(0, Qt.UserRole)
            if lid:
                order.append(lid)
        s = _settings()
        # Qt can round-trip lists through QSettings as QStringList.
        s.setValue(f"{_QS_PREFIX}layer_order/{self._project_scope_key()}",
                   order)

    def _load_layer_order(self):
        """Return persisted order as a list of layer_ids, or None."""
        raw = _settings().value(
            f"{_QS_PREFIX}layer_order/{self._project_scope_key()}", None
        )
        if raw is None:
            return None
        if isinstance(raw, str):
            return [raw] if raw else None
        return list(raw)

    def _legend_hidden_set(self) -> set:
        """Layer IDs where column 2 ('In legend') is UNCHECKED.
        Walks both top-level and group-nested rows."""
        hidden = set()
        for item, lid in self._iter_layer_items():
            if item.checkState(2) != Qt.Checked:
                hidden.add(lid)
        return hidden

    def _group_display_overrides(self) -> dict:
        """Load all {group_name: display_name_or_empty} overrides from
        QSettings. Empty value == flatten (hide heading, keep children)."""
        s = _settings()
        overrides = {}
        s.beginGroup(_QS_PREFIX + "group_names")
        try:
            for key in s.childKeys():
                overrides[key] = s.value(key, "", type=str)
        finally:
            s.endGroup()
        return overrides

    def _all_layer_tree_groups(self):
        """Walk the project layer tree and yield every group node."""
        root = self._project.layerTreeRoot()
        stack = [root]
        groups = []
        while stack:
            node = stack.pop()
            try:
                children = list(node.children())
            except AttributeError:
                children = []
            for child in children:
                if hasattr(child, "findGroups"):
                    groups.append(child)
                    stack.append(child)
        return groups

    def _open_group_rename_dialog(self):
        groups = self._all_layer_tree_groups()
        if not groups:
            QMessageBox.information(
                self, "No groups",
                "The current project's layer tree has no groups.",
            )
            return
        existing = self._group_display_overrides()

        dlg = QDialog(self)
        dlg.setWindowTitle("Rename legend groups")
        dlg.setModal(True)
        dlg.resize(520, 320)

        form = QFormLayout()
        line_edits = {}
        hint = QLabel(
            "Empty value = hide the group heading (children still appear "
            "flat in the legend)."
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #555;")

        for grp in groups:
            name = grp.name()
            edit = QLineEdit(existing.get(name, ""))
            edit.setPlaceholderText(name)
            form.addRow(f"{name}:", edit)
            line_edits[name] = edit

        btns = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        btns.accepted.connect(dlg.accept)
        btns.rejected.connect(dlg.reject)

        root = QVBoxLayout(dlg)
        root.addWidget(hint)
        root.addLayout(form)
        root.addStretch(1)
        root.addWidget(btns)

        if dlg.exec_() == QDialog.Accepted:
            s = _settings()
            s.beginGroup(_QS_PREFIX + "group_names")
            try:
                for name, edit in line_edits.items():
                    s.setValue(name, (edit.text() or "").strip())
            finally:
                s.endGroup()

    def _sync_canvas_to_selection(self, *_):
        layers = self._selected_layers()
        self.mapCanvas.setLayers(layers)
        if layers:
            self.mapCanvas.setDestinationCrs(layers[0].crs())
        self._fit_to_selected_layer()

    def _on_fit_layer_changed(self, _index: int):
        lid = self.fitLayerCombo.currentData()
        if lid:
            s = _settings()
            # Write BOTH the per-project key (primary) and the global
            # key (legacy fallback for future projects that lack their
            # own per-project key).
            s.setValue(self._fit_layer_settings_key(), lid)
            s.setValue(_QS_PREFIX + "fit_layer_id", lid)
        self._fit_to_selected_layer()

    def _fit_to_selected_layer(self):
        lid = self.fitLayerCombo.currentData()
        if not lid:
            self.mapCanvas.zoomToFullExtent()
            return
        layer = self._project.mapLayer(lid)
        if layer is None:
            self.mapCanvas.zoomToFullExtent()
            return
        extent = layer.extent()
        if extent.isEmpty():
            self.mapCanvas.zoomToFullExtent()
            return
        pad = 0.10
        w = extent.width() * pad
        h = extent.height() * pad
        extent.setXMinimum(extent.xMinimum() - w)
        extent.setXMaximum(extent.xMaximum() + w)
        extent.setYMinimum(extent.yMinimum() - h)
        extent.setYMaximum(extent.yMaximum() + h)
        # WYSIWYG: expand to match the PDF map frame aspect so the
        # preview shows the same area the PDF will render.
        _expand_extent_to_aspect(extent, _PDF_BODY_ASPECT)
        self.mapCanvas.setExtent(extent)
        self.mapCanvas.refresh()

    # --- Render -----------------------------------------------------------

    def _current_config(self) -> PdfExportConfig:
        s = _settings()
        return PdfExportConfig(
            survey_name=self.surveyEdit.text().strip() or "Survey",
            vessel_name=s.value(_QS_PREFIX + "vessel_name", "", type=str),
            project_name=s.value(_QS_PREFIX + "project_name", "", type=str),
            hours=int(s.value(_QS_PREFIX + "hours", 48, type=int)),
            header_template=s.value(_QS_PREFIX + "header_template",
                                    _DEFAULT_HEADER, type=str) or _DEFAULT_HEADER,
            logo_vessel_path=(s.value(_QS_PREFIX + "logo_vessel", "", type=str)
                              or None),
            logo_company_path=(s.value(_QS_PREFIX + "logo_company", "", type=str)
                               or None),
            logo_client_path=(s.value(_QS_PREFIX + "logo_client", "", type=str)
                              or None),
            show_north_arrow=self.cbNorth.isChecked(),
            show_scale_bar=self.cbScale.isChecked(),
            show_legend=self.cbLegend.isChecked(),
            show_coord_grid=True,  # gated by grid_style below
            grid_style=(self.gridStyleCombo.currentData() or "light"),
            start_sequence_number=self._start_seq,
            layer_display_names=self._layer_display_overrides(),
            group_display_names=self._group_display_overrides(),
            hidden_from_legend=self._legend_hidden_set(),
            legend_order=self._current_legend_order(),
        )

    def _current_legend_order(self) -> list:
        """Return the current on-screen row order as a list of layer_ids."""
        order = []
        for i in range(self.layerTree.topLevelItemCount()):
            item = self.layerTree.topLevelItem(i)
            lid = item.data(0, Qt.UserRole)
            if lid:
                order.append(lid)
        return order

    def _on_render_clicked(self):
        self._save_per_export_settings()
        cfg = self._current_config()

        s = _settings()
        last_dir = s.value(_QS_PREFIX + "export_dir", "", type=str)
        out_dir = QFileDialog.getExistingDirectory(
            self, "Pick folder for the PDF", last_dir or os.path.expanduser("~"),
        )
        if not out_dir:
            return
        s.setValue(_QS_PREFIX + "export_dir", out_dir)

        date_str = QDate.currentDate().toString("yyyy_MM_dd")
        filename = compute_output_filename(date_str, cfg.survey_name, out_dir)
        full_path = os.path.join(out_dir, filename)

        try:
            rows = rows_from_optimized_path_layer(
                self._opt_layer, self._gen_layer,
                start_sequence_number=self._start_seq,
            )
        except Exception as e:
            log.exception("Failed to build rows from Optimized_Path")
            QMessageBox.critical(self, "PDF export failed",
                                 f"Could not read plan rows: {e}")
            return

        if not rows:
            QMessageBox.warning(
                self, "No rows to export",
                "The Optimized_Path layer has no Line-type features to export. "
                "Run a simulation first.",
            )
            return

        visible_layers = self._selected_layers()
        map_extent = self.mapCanvas.extent()
        try:
            map_crs = self.mapCanvas.mapSettings().destinationCrs()
        except Exception:  # noqa: BLE001
            map_crs = None

        try:
            layout = build_lookahead_layout(
                project=self._project,
                visible_layers=visible_layers,
                map_extent=map_extent,
                rows=rows,
                config=cfg,
                date_str=date_str,
                map_crs=map_crs,
            )
            ok, err = export_pdf(layout, full_path)
        except Exception as e:
            log.exception("PDF layout/export raised")
            QMessageBox.critical(self, "PDF export failed", str(e))
            return

        if not ok:
            QMessageBox.critical(self, "PDF export failed",
                                 err or "Unknown exporter error.")
            return

        resp = QMessageBox.information(
            self,
            "Report created",
            f"Saved:\n{full_path}\n\nOpen it now?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes,
        )
        if resp == QMessageBox.Yes:
            QDesktopServices.openUrl(QtCore.QUrl.fromLocalFile(full_path))

        self.accept()
