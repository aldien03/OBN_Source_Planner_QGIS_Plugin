def handle_run_simulation(self):
    """
    Main handler for simulation execution: Prepares data, calculates deviations,
    filters lines, generates acquisition sequence, and visualizes results.
    """
    log.info("--- handle_run_simulation START ---")
    QApplication.setOverrideCursor(Qt.WaitCursor)
    
    # Reset all previous simulation data
    self.last_simulation_result = None
    self.last_sim_params = None
    self.last_line_data = None
    self.last_required_layers = None
    self.last_turn_cache = {}
    
    if hasattr(self, 'editFinalizeButton'):
        self.editFinalizeButton.setEnabled(False)
    
    try:
        # Step 1: Get simulation parameters
        sim_params = self._gather_simulation_parameters()
        self.last_sim_params = sim_params
        if not sim_params:
            raise ValueError("Parameter gathering failed")
        
        # Step 2: Prepare line data
        line_data_initial, required_layers = self._prepare_line_data(sim_params)
        self.last_required_layers = required_layers
        if not line_data_initial:
            raise ValueError("Line data preparation failed")

        # Step 3: Calculate line deviations using RRT algorithm
        rrt_params = {
            k: sim_params.get(f'rrt_{k}') 
            for k in ['step_size', 'max_iterations', 'goal_bias']
        }
        # Remove None values
        rrt_params = {k: v for k, v in rrt_params.items() if v is not None}
        
        line_data_deviated = self._calculate_and_apply_deviations_rrt(
            line_data_initial, 
            sim_params.get('nogo_layer'),
            sim_params.get('deviation_clearance_m', 100.0),
            sim_params.get('turn_radius_meters', 500.0),
            rrt_params
        )
        # Store potentially modified data
        self.last_line_data = line_data_deviated

        # Step 4: Filter lines that need to be acquired
        active_line_nums = sorted([
            ln for ln, data in line_data_deviated.items() 
            if str(data.get('Status', 'Acquired')).upper() == 'TO BE ACQUIRED' 
            and not data.get('deviation_failed', False)
        ])
        
        if not active_line_nums:
            raise ValueError("No usable 'To Be Acquired' lines after deviation checks.")
            
        log.info(f"Proceeding with {len(active_line_nums)} non-failed, 'To Be Acquired' lines.")

        # Determine starting line
        first_line_num = sim_params['first_line_num']
        if first_line_num not in active_line_nums:
            log.warning(f"First line {first_line_num} not active/valid. Using {active_line_nums[0]}.")
            first_line_num = active_line_nums[0]
            sim_params['first_line_num'] = first_line_num

        # Step 5: Generate acquisition sequence based on selected mode
        selected_mode = sim_params.get('acquisition_mode', 'Racetrack')
        best_final_sequence_info = None
    
        # --- Racetrack Mode ---
        if selected_mode == "Racetrack":
            log.info("Starting Racetrack Simulation...")
            
            # Calculate ideal jump between lines
            ideal_jump = 1
            interval = self._calculate_most_common_interval_from_lines(required_layers['lines'])
            if interval and interval > 1.0:
                try:
                    ideal_jump = max(1, int(round((sim_params['turn_radius_meters'] * 2.0) / interval)))
                except Exception:
                    pass
                log.info(f"Ideal Jump: {ideal_jump}")
            
            # Generate sequence
            seq = self._generate_interleaved_racetrack_sequence(active_line_nums, first_line_num, ideal_jump)
            if not seq:
                raise ValueError("Failed Racetrack sequence generation.")
            
            # Calculate sequence timing for both directions
            cost_norm, dirs_norm = self._calculate_sequence_time(
                seq, False, sim_params,
                line_data_deviated, required_layers,
                self.last_turn_cache
            )
            
            cost_recip, dirs_recip = self._calculate_sequence_time(
                seq, True, sim_params,
                line_data_deviated, required_layers,
                self.last_turn_cache
            )
            
            if cost_norm is None and cost_recip is None:
                raise ValueError("Both Racetrack timings failed.")
            
            # Select best direction based on user preference
            user_prefers_recip = (sim_params['first_heading_option'] == "High to Low SP (Reciprocal)")
            final_cost = 0
            final_dirs = {}
            
            if user_prefers_recip:
                if cost_recip is not None:
                    final_cost = cost_recip
                    final_dirs = dirs_recip
                    log.info("Selected Reciprocal direction (User Preference).")
                elif cost_norm is not None:
                    final_cost = cost_norm
                    final_dirs = dirs_norm
                    log.warning("Preferred Reciprocal direction failed. Using Normal.")
            else:
                if cost_norm is not None:
                    final_cost = cost_norm
                    final_dirs = dirs_norm
                    log.info("Selected Normal direction (User Preference).")
                elif cost_recip is not None:
                    final_cost = cost_recip
                    final_dirs = dirs_recip
                    log.warning("Preferred Normal direction failed. Using Reciprocal.")
            
            # Store final sequence info
            best_final_sequence_info = {
                'seq': seq,
                'cost': final_cost,
                'state': {'line_directions': final_dirs}
            }
            
        # --- Teardrop Mode ---
        elif selected_mode == "Teardrop":
            log.info("Starting Teardrop Simulation...")
            start_recip = (sim_params['first_heading_option'] == "High to Low SP (Reciprocal)")
            
            # Initialize sequence with first line
            current_seq = [first_line_num]
            initial_cost = 0.0
            
            # Get exit state for first line
            current_exit_pt, current_exit_hdg = self._get_next_exit_state(
                first_line_num, 
                start_recip, 
                line_data_deviated
            )
            
            # Set up initial state
            initial_state = {
                'last_line_num': first_line_num,
                'exit_pt': current_exit_pt,
                'exit_hdg': current_exit_hdg,
                'is_reciprocal': start_recip,
                'remaining_lines': set(active_line_nums) - {first_line_num},
                'line_directions': {first_line_num: ('high_to_low' if start_recip else 'low_to_high')}
            }
            
            # Begin iterative line selection
            current_state = initial_state
            current_cost = initial_cost
            
            # Process lines until all are added or we encounter an error
            while current_state['remaining_lines']:
                # Find next line to add to sequence
                next_ln = self._determine_next_line(
                    current_state['last_line_num'], 
                    current_state['remaining_lines'], 
                    line_data_deviated
                )
                
                if next_ln is None:
                    log.warning("No valid next line found. Ending sequence.")
                    break
                
                # Set direction for next line (alternate directions)
                next_is_recip = not current_state['is_reciprocal']
                current_state['line_directions'][next_ln] = (
                    'high_to_low' if next_is_recip else 'low_to_high'
                )
                
                # Get entry details for next line
                next_info = line_data_deviated[next_ln]
                p_entry, h_entry = self._get_entry_details(next_info, next_is_recip)
                exit_pt = current_state['exit_pt']
                exit_hdg = current_state['exit_hdg']
                
                # Calculate turn between current exit and next entry
                turn_g, turn_l, turn_t = self._get_cached_turn(
                    current_state['last_line_num'], 
                    next_ln, 
                    next_is_recip, 
                    exit_pt, 
                    exit_hdg, 
                    p_entry, 
                    h_entry, 
                    sim_params, 
                    self.last_turn_cache
                )
                
                # Check if turn was possible
                if turn_g is None or turn_t is None:
                    log.error(f"Teardrop turn failed {current_state['last_line_num']}->{next_ln}. Stopping sequence.")
                    break
                
                # Add turn time to total
                current_cost += turn_t
                
                # Simulate line acquisition and get next exit state
                next_exit_pt, next_exit_hdg, runin_t_step, line_t_step = self._simulate_add_line(
                    next_ln, 
                    next_is_recip, 
                    line_data_deviated, 
                    required_layers, 
                    sim_params
                )
                
                # Add acquisition time to total
                current_cost += runin_t_step + line_t_step
                
                # Update sequence and state
                current_seq.append(next_ln)
                current_state['remaining_lines'].remove(next_ln)
                current_state['last_line_num'] = next_ln
                current_state['exit_pt'] = next_exit_pt
                current_state['exit_hdg'] = next_exit_hdg
                current_state['is_reciprocal'] = next_is_recip
            
            # Store teardrop sequence results
            best_final_sequence_info = {
                'seq': current_seq, 
                'cost': current_cost, 
                'state': current_state
            }
        
        # Handle unknown acquisition mode
        else:
            raise ValueError(f"Unknown acquisition mode: {selected_mode}")

        # Step 6: Visualize results if sequence was found
        if best_final_sequence_info:
            # Save results for later use
            self.last_simulation_result = best_final_sequence_info
            log.info("Simulation successful. Visualizing path...")
            
            # Reconstruct the complete path with turns
            path_segments = self._reconstruct_path(
                best_final_sequence_info, 
                line_data_deviated, 
                required_layers, 
                sim_params, 
                self.last_turn_cache
            )
            
            # Create visualization layers                                  
            self._visualize_optimized_path(
                best_final_sequence_info['seq'], 
                path_segments, 
                sim_params.get('start_datetime'), 
                required_layers['lines'].crs(), 
                line_data_deviated
            )
            
            # Enable edits if supported
            if hasattr(self, 'editFinalizeButton'):
                self.editFinalizeButton.setEnabled(True)
                
            # Show final estimated time
            log.info(f"Final Estimated Cost: {best_final_sequence_info.get('cost',0)/3600.0:.2f} hours")
        else:
            log.error("Simulation algorithm failed to produce a valid result.")
            
    except ValueError as ve:
        log.error(f"Input/Data Error during Run Simulation: {ve}")
        QMessageBox.warning(self, "Simulation Error", f"{ve}")
    except Exception as e:
        log.exception(f"Unexpected error during Run Simulation: {e}")
        QMessageBox.critical(self, "Simulation Error", 
                            f"Unexpected error during simulation:\n{e}\n\nSee log for details.")
    finally:
        # Always restore cursor
        QApplication.restoreOverrideCursor()
        log.info("--- handle_run_simulation END ---")
