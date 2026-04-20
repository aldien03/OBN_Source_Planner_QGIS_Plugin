# -*- coding: utf-8 -*-
"""
48-hour Lookahead preview dialog (Phase 17b).

A custom dialog that gives the Chief Navigator an "export workspace":
settings + layer visibility + map canvas + Render PDF button, all in
one modal. Mirrors QGIS's own Print Layout in spirit but scoped to
the one output this plugin produces.

Why this exists instead of a fully-automated one-click export: the
user explicitly rejected 100% automation. Chiefs need to pan/zoom the
map and toggle layers case-by-case (SIMOPS changes daily, bathymetry
sometimes clutters, etc.).
"""
from __future__ import annotations

import logging
import os
from datetime import datetime

from qgis.core import (
    QgsProject,
    QgsMapLayer,
)
from qgis.gui import QgsMapCanvas, QgsMapToolPan
from qgis.PyQt import QtCore, QtWidgets
from qgis.PyQt.QtCore import QDate, QSettings, Qt
from qgis.PyQt.QtGui import QDesktopServices
from qgis.PyQt.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
)

try:
    from .services.pdf_export import (
        PdfExportConfig,
        build_lookahead_layout,
        compute_output_filename,
        export_pdf,
        rows_from_optimized_path_layer,
    )
except ImportError:  # pragma: no cover
    from services.pdf_export import (  # type: ignore
        PdfExportConfig,
        build_lookahead_layout,
        compute_output_filename,
        export_pdf,
        rows_from_optimized_path_layer,
    )

log = logging.getLogger("obn_planner")

_QS_PREFIX = "pdf/"
_DEFAULT_HEADER = "{vessel} {hours}Hrs Look Ahead \u2014 {project}"


class PdfExportDialog(QDialog):
    """Preview + export dialog for the 48-hour Lookahead PDF.

    Constructor arguments:
      parent:         the QGIS plugin dock (for modality).
      project:        the active QgsProject.
      optimized_path_layer: memory layer with simulation timing.
      generated_lines_layer: memory layer with Operation/FGSP/LGSP.
    """

    def __init__(self, parent, project, optimized_path_layer,
                 generated_lines_layer):
        super().__init__(parent)
        self.setWindowTitle("Create 48-hour Lookahead Report")
        self.setModal(True)
        self.resize(1100, 700)

        self._project = project
        self._opt_layer = optimized_path_layer
        self._gen_layer = generated_lines_layer
        self._settings = QSettings("obn_planner", "pdf_export")

        self._build_ui()
        self._load_settings()
        self._populate_layers_panel()
        self._populate_fit_layer_combo()
        self._sync_canvas_to_selection()

    # --- UI construction ---------------------------------------------------

    def _build_ui(self):
        root = QHBoxLayout(self)

        # --- Left column: settings + layers + decorations ---
        left = QVBoxLayout()
        left.setSpacing(6)

        # Settings group
        gb_settings = QGroupBox("Report details")
        form = QFormLayout(gb_settings)
        self.surveyEdit = QLineEdit()
        self.surveyEdit.setPlaceholderText("e.g. 4D TVD")
        self.vesselEdit = QLineEdit()
        self.vesselEdit.setPlaceholderText("Vessel name")
        self.projectEdit = QLineEdit()
        self.projectEdit.setPlaceholderText("Project / client")
        self.hoursSpin = QSpinBox()
        self.hoursSpin.setRange(1, 999)
        self.hoursSpin.setValue(48)
        self.hoursSpin.setSuffix(" hrs")
        self.headerEdit = QLineEdit()
        self.headerEdit.setPlaceholderText(_DEFAULT_HEADER)
        form.addRow("Survey:", self.surveyEdit)
        form.addRow("Vessel:", self.vesselEdit)
        form.addRow("Project:", self.projectEdit)
        form.addRow("Hours:", self.hoursSpin)
        form.addRow("Header:", self.headerEdit)

        self.logoVesselEdit, btnLV = self._make_logo_row("Vessel logo")
        self.logoCompanyEdit, btnLC = self._make_logo_row("Company logo")
        self.logoClientEdit, btnLX = self._make_logo_row("Client logo")
        form.addRow("Vessel logo:", self._logo_row_layout(self.logoVesselEdit, btnLV))
        form.addRow("Company logo:", self._logo_row_layout(self.logoCompanyEdit, btnLC))
        form.addRow("Client logo:", self._logo_row_layout(self.logoClientEdit, btnLX))

        left.addWidget(gb_settings)

        # Layers group
        gb_layers = QGroupBox("Layers to include in map")
        lay_layers = QVBoxLayout(gb_layers)
        self.layerList = QListWidget()
        self.layerList.setToolTip("Tick which layers to draw on the map page.")
        lay_layers.addWidget(self.layerList)
        left.addWidget(gb_layers, stretch=1)

        # Map controls group
        gb_map = QGroupBox("Map controls")
        lay_map = QFormLayout(gb_map)
        self.fitLayerCombo = QComboBox()
        self.fitLayerCombo.setToolTip(
            "Snap the map extent to this layer's bounding box + 10% padding."
        )
        self.cbNorth = QCheckBox("North arrow")
        self.cbScale = QCheckBox("Scale bar")
        self.cbLegend = QCheckBox("Legend")
        self.cbGrid = QCheckBox("Coord grid")
        for cb in (self.cbNorth, self.cbScale, self.cbLegend, self.cbGrid):
            cb.setChecked(True)
        deco = QHBoxLayout()
        deco.addWidget(self.cbNorth)
        deco.addWidget(self.cbScale)
        deco.addWidget(self.cbLegend)
        deco.addWidget(self.cbGrid)
        deco_wrap = QtWidgets.QWidget()
        deco_wrap.setLayout(deco)
        lay_map.addRow("Fit to:", self.fitLayerCombo)
        lay_map.addRow("Decorations:", deco_wrap)
        left.addWidget(gb_map)

        # --- Right column: map canvas ---
        right = QVBoxLayout()
        self.mapCanvas = QgsMapCanvas()
        self.mapCanvas.setCanvasColor(Qt.white)
        self.mapCanvas.enableAntiAliasing(True)
        self._panTool = QgsMapToolPan(self.mapCanvas)
        self.mapCanvas.setMapTool(self._panTool)
        right.addWidget(self.mapCanvas, stretch=1)

        # --- Bottom button row ---
        btnRow = QHBoxLayout()
        btnRow.addStretch(1)
        self.renderBtn = QPushButton("Render PDF\u2026")
        self.renderBtn.setDefault(True)
        self.cancelBtn = QPushButton("Cancel")
        btnRow.addWidget(self.cancelBtn)
        btnRow.addWidget(self.renderBtn)

        full_left = QVBoxLayout()
        full_left.addLayout(left, stretch=1)

        left_wrap = QtWidgets.QWidget()
        left_wrap.setLayout(full_left)
        left_wrap.setMaximumWidth(420)

        right_wrap = QtWidgets.QWidget()
        right_lay = QVBoxLayout(right_wrap)
        right_lay.addLayout(right, stretch=1)
        right_lay.addLayout(btnRow)

        root.addWidget(left_wrap)
        root.addWidget(right_wrap, stretch=1)

        # --- Wiring ---
        self.cancelBtn.clicked.connect(self.reject)
        self.renderBtn.clicked.connect(self._on_render_clicked)
        self.layerList.itemChanged.connect(self._sync_canvas_to_selection)
        self.fitLayerCombo.currentIndexChanged.connect(self._on_fit_layer_changed)

        # Persist-on-change for every settings field
        for edit in (self.surveyEdit, self.vesselEdit, self.projectEdit,
                     self.headerEdit, self.logoVesselEdit,
                     self.logoCompanyEdit, self.logoClientEdit):
            edit.editingFinished.connect(self._save_settings)
        self.hoursSpin.valueChanged.connect(lambda _v: self._save_settings())
        for cb in (self.cbNorth, self.cbScale, self.cbLegend, self.cbGrid):
            cb.toggled.connect(lambda _v: self._save_settings())

    def _make_logo_row(self, label: str):
        edit = QLineEdit()
        edit.setPlaceholderText("(no logo)")
        edit.setReadOnly(True)
        btn = QPushButton("Browse\u2026")
        btn.clicked.connect(lambda _=False, e=edit, l=label: self._pick_logo(e, l))
        return edit, btn

    def _logo_row_layout(self, edit, btn):
        wrap = QtWidgets.QWidget()
        lay = QHBoxLayout(wrap)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(edit, stretch=1)
        lay.addWidget(btn)
        return wrap

    def _pick_logo(self, edit: QLineEdit, label: str):
        last = edit.text() or self._settings.value(_QS_PREFIX + "last_logo_dir", "")
        start_dir = os.path.dirname(last) if last else ""
        path, _ = QFileDialog.getOpenFileName(
            self, f"Pick {label}", start_dir,
            "Images (*.png *.jpg *.jpeg *.svg)",
        )
        if path:
            edit.setText(path)
            self._settings.setValue(_QS_PREFIX + "last_logo_dir",
                                    os.path.dirname(path))
            self._save_settings()

    # --- Settings persistence ---------------------------------------------

    def _load_settings(self):
        s = self._settings
        self.surveyEdit.setText(s.value(_QS_PREFIX + "survey_name", "", type=str))
        self.vesselEdit.setText(s.value(_QS_PREFIX + "vessel_name", "", type=str))
        self.projectEdit.setText(s.value(_QS_PREFIX + "project_name", "", type=str))
        self.hoursSpin.setValue(int(s.value(_QS_PREFIX + "hours", 48, type=int)))
        self.headerEdit.setText(
            s.value(_QS_PREFIX + "header_template", _DEFAULT_HEADER, type=str)
        )
        self.logoVesselEdit.setText(s.value(_QS_PREFIX + "logo_vessel", "", type=str))
        self.logoCompanyEdit.setText(s.value(_QS_PREFIX + "logo_company", "", type=str))
        self.logoClientEdit.setText(s.value(_QS_PREFIX + "logo_client", "", type=str))
        self.cbNorth.setChecked(
            s.value(_QS_PREFIX + "show_north", True, type=bool)
        )
        self.cbScale.setChecked(
            s.value(_QS_PREFIX + "show_scale", True, type=bool)
        )
        self.cbLegend.setChecked(
            s.value(_QS_PREFIX + "show_legend", True, type=bool)
        )
        self.cbGrid.setChecked(
            s.value(_QS_PREFIX + "show_grid", True, type=bool)
        )

    def _save_settings(self):
        s = self._settings
        s.setValue(_QS_PREFIX + "survey_name", self.surveyEdit.text())
        s.setValue(_QS_PREFIX + "vessel_name", self.vesselEdit.text())
        s.setValue(_QS_PREFIX + "project_name", self.projectEdit.text())
        s.setValue(_QS_PREFIX + "hours", self.hoursSpin.value())
        s.setValue(_QS_PREFIX + "header_template",
                   self.headerEdit.text() or _DEFAULT_HEADER)
        s.setValue(_QS_PREFIX + "logo_vessel", self.logoVesselEdit.text())
        s.setValue(_QS_PREFIX + "logo_company", self.logoCompanyEdit.text())
        s.setValue(_QS_PREFIX + "logo_client", self.logoClientEdit.text())
        s.setValue(_QS_PREFIX + "show_north", self.cbNorth.isChecked())
        s.setValue(_QS_PREFIX + "show_scale", self.cbScale.isChecked())
        s.setValue(_QS_PREFIX + "show_legend", self.cbLegend.isChecked())
        s.setValue(_QS_PREFIX + "show_grid", self.cbGrid.isChecked())

    # --- Layers panel ------------------------------------------------------

    def _all_project_layers(self):
        return list(self._project.mapLayers().values())

    def _populate_layers_panel(self):
        self.layerList.blockSignals(True)
        self.layerList.clear()
        layer_tree = self._project.layerTreeRoot()
        for layer in self._all_project_layers():
            item = QListWidgetItem(layer.name())
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            node = layer_tree.findLayer(layer.id())
            visible = True if node is None else bool(node.isVisible())
            item.setCheckState(Qt.Checked if visible else Qt.Unchecked)
            item.setData(Qt.UserRole, layer.id())
            self.layerList.addItem(item)
        self.layerList.blockSignals(False)

    def _populate_fit_layer_combo(self):
        self.fitLayerCombo.blockSignals(True)
        self.fitLayerCombo.clear()
        for layer in self._all_project_layers():
            self.fitLayerCombo.addItem(layer.name(), layer.id())
        remembered = self._settings.value(_QS_PREFIX + "fit_layer_id", "", type=str)
        if remembered:
            idx = self.fitLayerCombo.findData(remembered)
            if idx >= 0:
                self.fitLayerCombo.setCurrentIndex(idx)
        self.fitLayerCombo.blockSignals(False)

    def _selected_layers(self):
        layers = []
        for i in range(self.layerList.count()):
            item = self.layerList.item(i)
            if item.checkState() == Qt.Checked:
                lid = item.data(Qt.UserRole)
                layer = self._project.mapLayer(lid)
                if layer is not None:
                    layers.append(layer)
        return layers

    # --- Canvas synchronization -------------------------------------------

    def _sync_canvas_to_selection(self, *_):
        layers = self._selected_layers()
        self.mapCanvas.setLayers(layers)
        if layers:
            self.mapCanvas.setDestinationCrs(layers[0].crs())
        self._fit_to_selected_layer()

    def _on_fit_layer_changed(self, _index: int):
        lid = self.fitLayerCombo.currentData()
        if lid:
            self._settings.setValue(_QS_PREFIX + "fit_layer_id", lid)
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
        self.mapCanvas.setExtent(extent)
        self.mapCanvas.refresh()

    # --- Render ------------------------------------------------------------

    def _current_config(self) -> PdfExportConfig:
        return PdfExportConfig(
            survey_name=self.surveyEdit.text().strip() or "Survey",
            vessel_name=self.vesselEdit.text().strip(),
            project_name=self.projectEdit.text().strip(),
            hours=self.hoursSpin.value(),
            header_template=self.headerEdit.text().strip() or _DEFAULT_HEADER,
            logo_vessel_path=self.logoVesselEdit.text().strip() or None,
            logo_company_path=self.logoCompanyEdit.text().strip() or None,
            logo_client_path=self.logoClientEdit.text().strip() or None,
            show_north_arrow=self.cbNorth.isChecked(),
            show_scale_bar=self.cbScale.isChecked(),
            show_legend=self.cbLegend.isChecked(),
            show_coord_grid=self.cbGrid.isChecked(),
        )

    def _on_render_clicked(self):
        self._save_settings()
        cfg = self._current_config()

        last_dir = self._settings.value(_QS_PREFIX + "export_dir", "", type=str)
        out_dir = QFileDialog.getExistingDirectory(
            self, "Pick folder for the PDF", last_dir or os.path.expanduser("~"),
        )
        if not out_dir:
            return
        self._settings.setValue(_QS_PREFIX + "export_dir", out_dir)

        date_str = QDate.currentDate().toString("yyyy_MM_dd")
        filename = compute_output_filename(date_str, cfg.survey_name, out_dir)
        full_path = os.path.join(out_dir, filename)

        try:
            rows = rows_from_optimized_path_layer(self._opt_layer, self._gen_layer)
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
            layout = build_lookahead_layout(
                project=self._project,
                visible_layers=visible_layers,
                map_extent=map_extent,
                rows=rows,
                config=cfg,
                date_str=date_str,
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
