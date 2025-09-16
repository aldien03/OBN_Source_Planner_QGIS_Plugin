# -*- coding: utf-8 -*-
import copy
from datetime import datetime, timedelta
import logging # Added for logging
# Using xlsxwriter instead of openpyxl for XLSX export
try:
    import xlsxwriter
except ImportError:
    pass  # We'll handle this in the export function
from qgis.core import QgsGeometry, QgsPointXY, QgsPoint
from qgis.PyQt import QtCore, QtGui, QtWidgets
from qgis.PyQt.QtCore import Qt, QDateTime
from qgis.PyQt.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QPushButton,
                             QTableWidget, QTableWidgetItem, QAbstractItemView,
                             QLabel, QHeaderView, QComboBox, QMessageBox,
                             QSizePolicy, QApplication, QFileDialog) # Added QFileDialog

# --- Logger ---
log = logging.getLogger("obn_planner") # Use the main plugin logger

# --- Define constants for column indices ---
COL_SEQ_NUM = 0 # New
COL_LINE_NUM = 1
COL_START_SP = 2
COL_END_SP = 3
COL_START_TIME = 4
COL_END_TIME = 5
COL_DURATION = 6
COL_DIRECTION = 7
COL_ACTIONS = 8 # Placeholder

# --- ENHANCED custom_deepcopy (using copy constructor for QgsGeometry) ---
def custom_deepcopy(obj, memo=None):
    """Custom deepcopy function that handles QgsPointXY, QgsPoint, and QgsGeometry objects."""
    if memo is None:
        memo = {}
    obj_id = id(obj)
    if obj_id in memo:
        return memo[obj_id]

    if isinstance(obj, QgsGeometry):
        new_geom = QgsGeometry(obj) # Use copy constructor
        memo[obj_id] = new_geom
        return new_geom
    elif isinstance(obj, QgsPointXY):
        new_point = QgsPointXY(obj.x(), obj.y())
        memo[obj_id] = new_point
        return new_point
    elif isinstance(obj, QgsPoint):
        new_point = QgsPoint(obj.x(), obj.y())
        memo[obj_id] = new_point
        return new_point
    elif isinstance(obj, dict):
        new_dict = {}
        memo[obj_id] = new_dict
        for k, v in obj.items():
             new_dict[custom_deepcopy(k, memo)] = custom_deepcopy(v, memo)
        return new_dict
    elif isinstance(obj, list):
        new_list = []
        memo[obj_id] = new_list
        for item in obj:
            new_list.append(custom_deepcopy(item, memo))
        return new_list
    elif isinstance(obj, tuple):
         new_tuple_elements = [custom_deepcopy(item, memo) for item in obj]
         new_tuple = tuple(new_tuple_elements)
         memo[obj_id] = new_tuple # Cache the tuple itself
         return new_tuple
    else:
        # Use standard deepcopy for other types, but be careful
        try:
            new_obj = copy.deepcopy(obj, memo)
            memo[obj_id] = new_obj
            return new_obj
        except (TypeError, NotImplementedError):
            # If deepcopy fails, return the object itself (shallow copy for this element)
            # This might happen for complex QGIS objects or external library objects
            memo[obj_id] = obj
            return obj
# --- END ENHANCED custom_deepcopy ---

class SequenceEditDialog(QDialog):
    """ Dialog for viewing, editing sequence, directions, and timing. """

    def __init__(self, initial_sequence_info, recalculation_context, recalculation_callback, parent=None):
        """ Constructor for the Sequence Edit Dialog. """
        super().__init__(parent)
        self.setWindowTitle("Edit Survey Sequence")
        self.setMinimumSize(950, 600) # Wider for Sequence column

        # Store initial data, context, and callback
        self.original_sequence_info = custom_deepcopy(initial_sequence_info)
        self.current_sequence_info = custom_deepcopy(initial_sequence_info)

        # --- ADD DEBUG LOG ---
        log.debug(f"[SequenceEditDialog.__init__] Received initial sequence info:")
        log.debug(f"  Sequence: {self.current_sequence_info.get('seq')}")
        log.debug(f"  State: {self.current_sequence_info.get('state')}")
        log.debug(f"  Directions from state: {self.current_sequence_info.get('state', {}).get('line_directions')}")
        # --- END DEBUG LOG ---
        
        self.recalculation_context = recalculation_context # Dict with params, data, layers, cache, methods
        self.recalculation_callback = recalculation_callback # Callback to update main widget's cost/state

        # --- Get Start Sequence Number (Requirement 3) ---
        try:
            self.start_seq_num = int(self.recalculation_context.get("sim_params", {}).get("start_sequence_number", 1))
        except (ValueError, TypeError):
            log.warning("Could not parse start_sequence_number from context, defaulting to 1.")
            self.start_seq_num = 1
        log.debug(f"SequenceEditDialog using start sequence number: {self.start_seq_num}")


        self.segment_timings = {} # Cache detailed timings: {line_num: {'start': dt, 'end': dt, 'turn': s, 'runin': s, 'line': s, 'total_segment': s}}

        # --- UI Elements ---
        self.layout = QVBoxLayout(self)

        # Table Widget
        self.tableWidget = QTableWidget()
        # --- MODIFIED: Column count and headers (Requirement 3) ---
        self.tableWidget.setColumnCount(9) # Increased count
        self.tableWidget.setHorizontalHeaderLabels([
            "Seq", "Line", "Start SP", "End SP", "Start Time", "End Time", "Duration", "Direction", "Actions"
        ])

        # Adjust column widths (Updated indices - Requirement 3)
        self.tableWidget.horizontalHeader().setSectionResizeMode(COL_SEQ_NUM, QHeaderView.ResizeToContents) # New
        self.tableWidget.horizontalHeader().setSectionResizeMode(COL_LINE_NUM, QHeaderView.ResizeToContents)
        self.tableWidget.horizontalHeader().setSectionResizeMode(COL_START_SP, QHeaderView.ResizeToContents)
        self.tableWidget.horizontalHeader().setSectionResizeMode(COL_END_SP, QHeaderView.ResizeToContents)
        self.tableWidget.horizontalHeader().setSectionResizeMode(COL_START_TIME, QHeaderView.Stretch)
        self.tableWidget.horizontalHeader().setSectionResizeMode(COL_END_TIME, QHeaderView.Stretch)
        self.tableWidget.horizontalHeader().setSectionResizeMode(COL_DURATION, QHeaderView.ResizeToContents)
        self.tableWidget.horizontalHeader().setSectionResizeMode(COL_DIRECTION, QHeaderView.ResizeToContents)
        self.tableWidget.horizontalHeader().setSectionResizeMode(COL_ACTIONS, QHeaderView.ResizeToContents)

        self.tableWidget.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tableWidget.setSelectionMode(QAbstractItemView.SingleSelection)
        self.tableWidget.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.layout.addWidget(self.tableWidget)

        # Bottom Controls Layout
        self.bottomControlLayout = QHBoxLayout()

        # Move Buttons
        self.moveButtonLayout = QHBoxLayout()
        self.upButton = QPushButton("Move Up")
        self.downButton = QPushButton("Move Down")
        self.moveButtonLayout.addStretch()
        self.moveButtonLayout.addWidget(self.upButton)
        self.moveButtonLayout.addWidget(self.downButton)
        self.moveButtonLayout.addStretch()
        self.bottomControlLayout.addLayout(self.moveButtonLayout) # Add move buttons to bottom layout

        # Export Button (Requirement 4)
        self.exportButton = QPushButton("Export XLSX")
        self.bottomControlLayout.addWidget(self.exportButton) # Add export button

        self.layout.addLayout(self.bottomControlLayout) # Add the combined bottom layout

        # Info Label (Total Time)
        self.infoLayout = QHBoxLayout()
        self.timeLabel = QLabel("Est. Total Time: --- hours")
        self.timeLabel.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.infoLayout.addWidget(self.timeLabel)
        self.layout.addLayout(self.infoLayout)

        # OK / Cancel Buttons
        self.buttonBox = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)
        self.buttonBox.accepted.connect(self.on_accept)
        self.buttonBox.rejected.connect(self.reject)
        self.layout.addWidget(self.buttonBox)

        # --- Connect Signals ---
        self.upButton.clicked.connect(self.move_up)
        self.downButton.clicked.connect(self.move_down)
        self.exportButton.clicked.connect(self.export_to_xlsx) # Connect export button
        self.tableWidget.itemSelectionChanged.connect(self.update_button_states)

        # --- Initial Population ---
        self.run_full_timing_calculation_and_update(show_message=False)
        self.update_button_states()


    def _calculate_segment_times(self, sequence, directions):
        """
        Internal helper to calculate detailed start/end/duration for each line segment.
        Uses context passed during dialog initialization. DOUBLES run-in time.
        Returns a dictionary: {line_num: {'start': dt, 'end': dt, 'turn': s, 'runin': s, 'line': s, 'total_segment': s}}
        Returns None on failure.
        """
        timings = {}
        if not sequence:
            return timings

        # ... (Retrieve context safely - code remains the same) ...
        sim_params = self.recalculation_context.get("sim_params")
        line_data = self.recalculation_context.get("line_data")
        required_layers = self.recalculation_context.get("required_layers")
        turn_cache = self.recalculation_context.get("turn_cache")
        _get_cached_turn = self.recalculation_context.get("_get_cached_turn")
        _find_runin_geom = self.recalculation_context.get("_find_runin_geom")
        _calculate_runin_time = self.recalculation_context.get("_calculate_runin_time")
        _get_next_exit_state = self.recalculation_context.get("_get_next_exit_state")
        _get_entry_details = self.recalculation_context.get("_get_entry_details")

        if not all([sim_params, line_data, required_layers, turn_cache is not None,
                    _get_cached_turn, _find_runin_geom, _calculate_runin_time,
                    _get_next_exit_state, _get_entry_details]):
            QMessageBox.critical(self, "Context Error", "Missing required context for timing calculation. Cannot proceed.")
            log.error("Error: Missing context for segment time calculation.")
            return None

        current_time = sim_params.get('start_datetime', datetime.now())
        current_state = {}
        total_cost_seconds = 0.0

        try:
            log.debug("--- Calculating Segment Times (with DOUBLED Run-In) ---")
            # --- Process First Line ---
            line_num = sequence[0]
            is_reciprocal = (directions.get(line_num) == 'high_to_low')
            line_info = line_data.get(line_num)
            if not line_info: raise ValueError(f"Line data not found for line {line_num}")

            line_time_s = line_info.get('length', 0) / sim_params.get('avg_shooting_speed_mps', 1.0)
            runin_time_s_original = 0.0 # Store original calculation
            runin_geom = _find_runin_geom(required_layers['runins'], line_num, "End" if is_reciprocal else "Start")
            if runin_geom:
                runin_time_s_original = _calculate_runin_time(runin_geom, sim_params)

            # --- MODIFICATION: Double the run-in time ---
            runin_time_s = runin_time_s_original * 2.0
            log.debug(f"  Line {line_num} (First): Original RunIn={runin_time_s_original:.1f}s, Using Doubled RunIn={runin_time_s:.1f}s")
            # --- END MODIFICATION ---

            segment_start_time = current_time
            segment_duration_s = runin_time_s + line_time_s # Use doubled runin_time_s
            segment_end_time = segment_start_time + timedelta(seconds=segment_duration_s)
            total_segment_time = runin_time_s + line_time_s # Turn time is 0

            log.debug(f"  Line {line_num} (First): Start={segment_start_time.strftime('%H:%M:%S')}, DoubledRunIn={runin_time_s:.1f}s, Line={line_time_s:.1f}s, End={segment_end_time.strftime('%H:%M:%S')}")

            timings[line_num] = {
                'start': segment_start_time, 'end': segment_end_time,
                'turn': 0.0,
                'runin': runin_time_s, # Store the doubled value
                'line': line_time_s,
                'total_segment': total_segment_time
            }
            current_time = segment_end_time
            total_cost_seconds += total_segment_time

            current_exit_pt, current_exit_hdg = _get_next_exit_state(line_num, is_reciprocal, line_data)
            if current_exit_pt is None or current_exit_hdg is None:
                 raise ValueError(f"Could not determine exit state after first line {line_num}")
            current_state = { 'exit_pt': current_exit_pt, 'exit_hdg': current_exit_hdg }

            # --- Iterate Through Remaining Lines ---
            for i in range(len(sequence) - 1):
                from_line = sequence[i]
                line_num = sequence[i+1]
                is_reciprocal = (directions.get(line_num) == 'high_to_low')

                line_info = line_data.get(line_num)
                if not line_info: raise ValueError(f"Line data not found for line {line_num}")

                p_entry, h_entry = _get_entry_details(line_info, is_reciprocal)
                exit_pt = current_state['exit_pt']
                exit_hdg = current_state['exit_hdg']

                if not p_entry or h_entry is None or not exit_pt or exit_hdg is None:
                    raise ValueError(f"Missing turn data for {from_line}->{line_num}")

                turn_geom, turn_length, turn_time_s = _get_cached_turn(from_line, line_num, is_reciprocal, exit_pt, exit_hdg, p_entry, h_entry, sim_params, turn_cache)
                if turn_geom is None or turn_time_s is None:
                    raise ValueError(f"Turn calculation failed for {from_line}->{line_num}")

                line_time_s = line_info.get('length', 0) / sim_params.get('avg_shooting_speed_mps', 1.0)
                runin_time_s_original = 0.0 # Store original calculation
                runin_geom = _find_runin_geom(required_layers['runins'], line_num, "End" if is_reciprocal else "Start")
                if runin_geom:
                     runin_time_s_original = _calculate_runin_time(runin_geom, sim_params)


                # --- MODIFICATION: Double the run-in time ---
                runin_time_s = runin_time_s_original * 2.0
                log.debug(f"  Line {line_num}: Original RunIn={runin_time_s_original:.1f}s, Using Doubled RunIn={runin_time_s:.1f}s")
                # --- END MODIFICATION ---

                segment_start_time = current_time + timedelta(seconds=turn_time_s)
                segment_duration_s = runin_time_s + line_time_s # Use doubled runin_time_s
                segment_end_time = segment_start_time + timedelta(seconds=segment_duration_s)
                total_segment_time = turn_time_s + runin_time_s + line_time_s # Use doubled runin_time_s

                log.debug(f"  Line {line_num}: PrevEnd={current_time.strftime('%H:%M:%S')}, Turn={turn_time_s:.1f}s, Start={segment_start_time.strftime('%H:%M:%S')}, DoubledRunIn={runin_time_s:.1f}s, Line={line_time_s:.1f}s, End={segment_end_time.strftime('%H:%M:%S')}")

                timings[line_num] = {
                    'start': segment_start_time, 'end': segment_end_time,
                    'turn': turn_time_s,
                    'runin': runin_time_s, # Store doubled value
                    'line': line_time_s,
                    'total_segment': total_segment_time
                }
                current_time = segment_end_time
                total_cost_seconds += total_segment_time

                current_exit_pt, current_exit_hdg = _get_next_exit_state(line_num, is_reciprocal, line_data)
                if current_exit_pt is None or current_exit_hdg is None:
                     raise ValueError(f"Could not determine exit state after line {line_num}")
                current_state = { 'exit_pt': current_exit_pt, 'exit_hdg': current_exit_hdg }

            # --- End Loop ---
            log.debug(f"Total Calculated Cost (with doubled run-in): {total_cost_seconds:.1f} seconds")
            self.current_sequence_info['cost'] = total_cost_seconds
            log.debug("--- Finished Calculating Segment Times (with DOUBLED Run-In) ---")
            return timings

        except Exception as e:
            log.exception(f"Error calculating segment times: {e}")
            QMessageBox.warning(self, "Timing Error", f"Could not calculate segment times:\n{e}")
            return None


    def run_full_timing_calculation_and_update(self, show_message=True):
        """Calculates timings for all segments and updates the table and total time label."""
        QApplication.setOverrideCursor(Qt.WaitCursor)
        calculation_ok = False
        try:
            sequence = self.current_sequence_info.get('seq', [])
            directions = self.current_sequence_info.get('state', {}).get('line_directions', {})

            if not sequence:
                 log.warning("Cannot calculate timing, sequence is empty.")
                 self.timeLabel.setText("Estimated Total Time: No Sequence")
                 self.populate_table() # Clear table
                 return False

            log.info("Running full timing calculation...")
            new_timings = self._calculate_segment_times(sequence, directions)

            if new_timings is not None:
                self.segment_timings = new_timings # Update stored timings
                self.populate_table() # Update table with new timings
                self.update_time_label() # Update total time label
                if show_message:
                    QMessageBox.information(self, "Calculation Complete", "Timings updated.")
                calculation_ok = True
                log.info("Timing calculation successful.")
            else:
                # Error handled/shown in _calculate_segment_times
                self.timeLabel.setText("Estimated Total Time: Error")
                log.error("Timing calculation failed.")

        finally:
            QApplication.restoreOverrideCursor()
        return calculation_ok # Return success/failure

    def populate_table(self):
        """ Fills the table including Sequence numbers, SPs and formatted duration. """
        sequence = self.current_sequence_info.get('seq', [])
        directions = self.current_sequence_info.get('state', {}).get('line_directions', {})
        log.debug(f"[populate_table] Using directions map: {directions}") # DEBUG
        line_data_map = self.recalculation_context.get("line_data", {}) # Get line_data from context

        self.tableWidget.blockSignals(True)
        self.tableWidget.setRowCount(len(sequence))
        dt_format = "%Y-%m-%d %H:%M:%S" # Datetime format

        # --- Store combos and their desired indices ---
        combos_to_set = [] # List to hold dictionaries {'combo': QComboBox, 'index': int, 'row': int, 'line': int}

        for i, line_num in enumerate(sequence):
            line_specific_data = line_data_map.get(line_num, {}) # Get data for this line

            # --- Sequence Number (Requirement 3) ---
            seq_num_val = self.start_seq_num + i
            seq_item = QTableWidgetItem(str(seq_num_val))
            seq_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            seq_item.setFlags(seq_item.flags() & ~Qt.ItemIsEditable)
            self.tableWidget.setItem(i, COL_SEQ_NUM, seq_item)
            # ---

            # Line Number
            line_item = QTableWidgetItem(str(line_num))
            line_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            line_item.setFlags(line_item.flags() & ~Qt.ItemIsEditable)
            self.tableWidget.setItem(i, COL_LINE_NUM, line_item)

            # --- Get SP based on Direction (Requirement 1 - Ensure consistency) ---
            direction_str = directions.get(line_num, 'low_to_high') # Get stored direction
            log.debug(f"  Row {i}, Line {line_num}: Fetched direction = '{direction_str}'") # DEBUG
            is_reciprocal = (direction_str == 'high_to_low')
            # Fetch SPs based on the *stored* direction
            start_sp_val = line_specific_data.get('highest_sp') if is_reciprocal else line_specific_data.get('lowest_sp')
            end_sp_val = line_specific_data.get('lowest_sp') if is_reciprocal else line_specific_data.get('highest_sp')
            start_sp_str = str(start_sp_val) if start_sp_val is not None else "N/A"
            end_sp_str = str(end_sp_val) if end_sp_val is not None else "N/A"

            start_sp_item = QTableWidgetItem(start_sp_str)
            start_sp_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            start_sp_item.setFlags(start_sp_item.flags() & ~Qt.ItemIsEditable)
            self.tableWidget.setItem(i, COL_START_SP, start_sp_item)

            end_sp_item = QTableWidgetItem(end_sp_str)
            end_sp_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            end_sp_item.setFlags(end_sp_item.flags() & ~Qt.ItemIsEditable)
            self.tableWidget.setItem(i, COL_END_SP, end_sp_item)
            # ---

            # Timing Items
            start_time_str, end_time_str, duration_str_hhmm = "N/A", "N/A", "N/A"
            line_timing = self.segment_timings.get(line_num)
            if line_timing:
                start_time_str = line_timing['start'].strftime(dt_format)
                end_time_str = line_timing['end'].strftime(dt_format)
                # Calculate duration from start/end times for robustness
                try:
                    segment_delta = line_timing['end'] - line_timing['start']
                    total_seconds = segment_delta.total_seconds()
                except TypeError:
                    total_seconds = -1 # Indicate error if dates are not valid

                if total_seconds >= 0:
                    hours = int(total_seconds // 3600)
                    minutes = int((total_seconds % 3600) // 60)
                    duration_str_hhmm = f"{hours:02d}:{minutes:02d}" # Format HH:MM
                else:
                    duration_str_hhmm = "Error"
            else:
                log.warning(f"No timing info found for line {line_num} during table population.")

            start_item = QTableWidgetItem(start_time_str); start_item.setFlags(start_item.flags() & ~Qt.ItemIsEditable); self.tableWidget.setItem(i, COL_START_TIME, start_item)
            end_item = QTableWidgetItem(end_time_str); end_item.setFlags(end_item.flags() & ~Qt.ItemIsEditable); self.tableWidget.setItem(i, COL_END_TIME, end_item)
            duration_item = QTableWidgetItem(duration_str_hhmm); duration_item.setFlags(duration_item.flags() & ~Qt.ItemIsEditable); self.tableWidget.setItem(i, COL_DURATION, duration_item)
            duration_item.setTextAlignment(Qt.AlignCenter | Qt.AlignVCenter) # Center align duration

            # --- Direction ComboBox (Create and store for deferred index setting) ---
            combo = QComboBox()
            combo.addItems(["Low to High", "High to Low"])
            combo.setProperty("row", i)
            combo.currentIndexChanged.connect(self.direction_changed)
            self.tableWidget.setCellWidget(i, COL_DIRECTION, combo)

            # Determine the correct index and store it
            direction_index = 1 if is_reciprocal else 0
            combos_to_set.append({'combo': combo, 'index': direction_index, 'row': i, 'line': line_num})
            # --- End Direction ComboBox creation ---

            # Actions Item
            actions_item = QTableWidgetItem("") # Placeholder
            actions_item.setFlags(actions_item.flags() & ~Qt.ItemIsEditable)
            self.tableWidget.setItem(i, COL_ACTIONS, actions_item)

        # --- Set ComboBox Indices AFTER the loop ---
        log.debug(f"Setting ComboBox indices for {len(combos_to_set)} rows after loop...")
        for item_info in combos_to_set:
            combo_widget = item_info['combo']
            target_index = item_info['index']
            log.debug(f"  Row {item_info['row']}, Line {item_info['line']}: Setting index to {target_index}")
            combo_widget.setCurrentIndex(target_index)
            # Optional: Check if it worked immediately (less critical now)
            # log.debug(f"  Row {item_info['row']}, Line {item_info['line']}: Actual index after set: {combo_widget.currentIndex()}, Text: '{combo_widget.currentText()}'")
        # --- End deferred setting ---

        self.tableWidget.blockSignals(False)
        self.tableWidget.resizeRowsToContents()

    def direction_changed(self, index):
        """ Handles direction ComboBox changes and triggers recalculation. """
        sender_combo = self.sender()
        if not sender_combo: return

        row = sender_combo.property("row")
        # Get line number from the correct column now (COL_LINE_NUM)
        line_num_item = self.tableWidget.item(row, COL_LINE_NUM)
        if line_num_item is None: return # Should not happen

        try:
            line_num = int(line_num_item.text())
        except (ValueError, TypeError):
            log.error(f"Error getting line number from row {row}")
            return

        new_direction_text = sender_combo.currentText()
        new_direction_str = new_direction_text.lower().replace(" ", "_")

        if 'state' in self.current_sequence_info and 'line_directions' in self.current_sequence_info['state']:
            if self.current_sequence_info['state']['line_directions'].get(line_num) != new_direction_str:
                self.current_sequence_info['state']['line_directions'][line_num] = new_direction_str
                log.info(f"Direction updated for line {line_num} to {new_direction_str}")
                # Recalculate and update table (important to refresh SPs and timings)
                self.run_full_timing_calculation_and_update(show_message=False)
        else:
            log.error(f"Error: Could not update direction state for line {line_num}")

    # --- Export to XLSX (Requirement 4) ---
    def export_to_xlsx(self):
        """Exports the current table data to an XLSX file using xlsxwriter."""
        log.debug("Export to XLSX button clicked.")
        
        try:
            import xlsxwriter
        except ImportError:
            log.error("Cannot export to XLSX: xlsxwriter library not found.")
            QMessageBox.critical(self, "Export Error", "The 'xlsxwriter' library is required to export to XLSX.\nPlease install it (e.g., 'pip install xlsxwriter') and restart QGIS.")
            return

        # Suggest filename
        now = datetime.now()
        default_filename = f"Shooting_Plan_{now.strftime('%Y%m%d_%H%M%S')}.xlsx"
        save_path, _ = QFileDialog.getSaveFileName(self, "Save Shooting Plan", default_filename, "Excel Files (*.xlsx)")

        if not save_path:
            log.info("XLSX export cancelled by user.")
            return

        # Ensure correct extension
        if not save_path.lower().endswith(".xlsx"):
            save_path += ".xlsx"

        try:
            # Create a workbook and add a worksheet
            workbook = xlsxwriter.Workbook(save_path)
            worksheet = workbook.add_worksheet("Shooting Plan")
            
            # Add a bold format for headers
            header_format = workbook.add_format({'bold': True})
            
            # Get headers
            headers = []
            for j in range(self.tableWidget.columnCount()):
                header_item = self.tableWidget.horizontalHeaderItem(j)
                headers.append(header_item.text() if header_item else f"Col_{j+1}")
            
            # Write headers
            for col_idx, header in enumerate(headers):
                worksheet.write(0, col_idx, header, header_format)
            
            # Write data rows
            for row_idx in range(self.tableWidget.rowCount()):
                for col_idx in range(self.tableWidget.columnCount()):
                    widget = self.tableWidget.cellWidget(row_idx, col_idx)
                    if isinstance(widget, QComboBox):
                        value = widget.currentText()
                    else:
                        item = self.tableWidget.item(row_idx, col_idx)
                        value = item.text() if item else ""
                    worksheet.write(row_idx + 1, col_idx, value)
            
            # Auto-fit columns (equivalent to auto-adjust column widths)
            for col_idx in range(len(headers)):
                max_width = len(headers[col_idx])
                for row_idx in range(self.tableWidget.rowCount()):
                    widget = self.tableWidget.cellWidget(row_idx, col_idx)
                    if isinstance(widget, QComboBox):
                        cell_text = widget.currentText()
                    else:
                        item = self.tableWidget.item(row_idx, col_idx)
                        cell_text = item.text() if item else ""
                    max_width = max(max_width, len(str(cell_text)))
                worksheet.set_column(col_idx, col_idx, max_width + 2)
            
            # Close the workbook
            workbook.close()
            
            log.info(f"Successfully exported shooting plan to {save_path}")
            QMessageBox.information(self, "Export Successful", f"Shooting plan exported to:\n{save_path}")

        except Exception as e:
            log.exception(f"Error exporting data to XLSX: {e}")
            QMessageBox.critical(self, "Export Error", f"An error occurred while exporting to XLSX:\n{e}")


    # --- Movement and Update Methods (Adjusted for new column indices) ---
    def move_up(self):
        """ Moves row up, updates internal sequence, recalculates timings. """
        currentRow = self.tableWidget.currentRow()
        if currentRow > 0:
            seq = self.current_sequence_info['seq']
            seq.insert(currentRow - 1, seq.pop(currentRow))
            log.debug(f"Internal sequence updated: {seq}")
            if self.run_full_timing_calculation_and_update(show_message=False):
                self.tableWidget.selectRow(currentRow - 1)

    def move_down(self):
        """ Moves row down, updates internal sequence, recalculates timings. """
        currentRow = self.tableWidget.currentRow()
        rowCount = self.tableWidget.rowCount()
        if currentRow < rowCount - 1 and currentRow != -1:
            seq = self.current_sequence_info['seq']
            seq.insert(currentRow + 1, seq.pop(currentRow))
            log.debug(f"Internal sequence updated: {seq}")
            if self.run_full_timing_calculation_and_update(show_message=False):
                self.tableWidget.selectRow(currentRow + 1)

    def update_button_states(self):
        """ Enables/disables Up/Down buttons based on selection. """
        currentRow = self.tableWidget.currentRow(); rowCount = self.tableWidget.rowCount()
        self.upButton.setEnabled(currentRow > 0); self.downButton.setEnabled(currentRow != -1 and currentRow < rowCount - 1)

    def update_time_label(self):
        """ Updates the total time label based on current_sequence_info cost. """
        cost_seconds = self.current_sequence_info.get('cost')
        if cost_seconds is None or cost_seconds < 0:
            self.timeLabel.setText("Estimated Total Time: Error")
            return
        cost_hours = cost_seconds / 3600.0
        self.timeLabel.setText(f"Est. Total Time: {cost_hours:.2f} hours")

    def on_accept(self):
        """ Run final recalculation before accepting to ensure consistency. """
        log.info("Accepting sequence edit dialog.")
        if self.run_full_timing_calculation_and_update(show_message=False):
            super().accept()
        else:
            QMessageBox.warning(self, "Accept Failed", "Final timing calculation failed. Cannot accept.")

    def get_final_sequence_info(self):
        """ Returns the potentially modified sequence info dictionary. """
        # Ensure the cost is up-to-date before returning
        self.update_time_label() # Recalculates cost if needed via run_full... called by other methods
        return self.current_sequence_info