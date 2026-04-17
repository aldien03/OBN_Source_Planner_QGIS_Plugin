# Phase 4 — SPS direction column + PREV_DIRECTION field

**Size:** small
**Risk:** low (purely additive; feature use comes in Phase 6)
**Blocks:** Phase 6 (direction-following sequence logic reads this data)
**Blocked by:** Phase 3 (spec registry must exist)

## Goal

Parse the "previous shooting direction" column from SPS files that carry it (e.g., Martin Linge). Store direction per SPS point in the GeoPackage layer and aggregate per line when lines are generated. **No user-visible behavior change yet** — this phase only populates the data; Phase 6 uses it to constrain sequence generation, Phase 8 adds the UI toggle.

## Evidence

`D1v1_MartinLindge_260410_sailline.sps` lines 87-104, 558, 1095:
- Line 2431 points: all direction `76.8°` (east-northeast)
- Line 2439 points: all direction `256.8°` (= 76.8 + 180, opposite)
- All points on the same line share the same direction value (user confirmed 2026-04-17: "always uniform")

Column position verified: characters 80-85 (right-justified, accommodates both `"  76.8"` and `" 256.8"`). Phase 3's `SPS_2_1_MARTIN_LINGE` already carries `direction=slice(80, 86)`.

## Files touched

### `io/gpkg_writer.py` (update)

Add `PREV_DIRECTION` field to the SPS point layer:

```python
def create_sps_layer_fields() -> QgsFields:
    fields = QgsFields()
    fields.append(QgsField("LINE", QVariant.Int))
    fields.append(QgsField("SP", QVariant.Int))
    fields.append(QgsField("EASTING", QVariant.Double))
    fields.append(QgsField("NORTHING", QVariant.Double))
    fields.append(QgsField("STATUS", QVariant.String))
    fields.append(QgsField("HEADING", QVariant.Double))
    fields.append(QgsField("PREV_DIRECTION", QVariant.Double))   # NEW. NULL if spec lacks direction
    return fields
```

`write_features_to_layer(writer, records, fields)` — read `record.direction` when present, write `NULL` / `None` when not. Do not crash on missing.

### `services/line_generator.py` (update — extracted later in Phase 7)

When aggregating SPS points into survey lines for `Generated_Survey_Lines` layer, propagate `PREV_DIRECTION` to the line feature:
- Add field `PREV_DIRECTION` (Double, nullable) to the generated lines layer schema.
- During aggregation, take the direction from the first point of each line (safe per uniformity assumption). Verify uniformity: if any point on a line has a different direction, log a warning and use the mode (majority) value.
- If no point on a line has a direction (old-format SPS), leave `PREV_DIRECTION` as NULL.

Because `line_generator` doesn't exist as a separate module until Phase 7, this phase updates the inline logic in `obn_planner_dockwidget.py:handle_generate_lines` (approximately `:1516-1938`). The inline update is small: 1-2 lines where per-line attributes are assembled. Phase 7 carries the change into the extracted module.

### `obn_planner_dockwidget.py` (small additions)

- `_create_sps_layer_fields` (`:635`) — add the `PREV_DIRECTION` field (matches `io/gpkg_writer.py:create_sps_layer_fields` for when inline and extracted are still both present; Phase 3 already created the `io/` module).
- `_write_features_to_layer` — populate the new field from `record.direction`.
- `handle_generate_lines` (around `:1800`, where the line feature attributes are set) — copy `PREV_DIRECTION` from the first point to the line feature.

## Uniformity verification

When aggregating SPS points into lines, check that all points on a given line have the same direction (within 0.1° tolerance). Behavior:

- All match → use that value.
- Any mismatch → log a warning with the line number and mismatched directions, then use the value from the first point. (Don't fail the import; this is diagnostic.)
- All NULL → PREV_DIRECTION is NULL for the line.

A log line like:

```
WARNING: Line 2431 has non-uniform PREV_DIRECTION: {76.8: 470 points, 76.9: 3 points}. Using 76.8.
```

...is acceptable for the rare case where direction jitter exists in real files. Phase 4 uses simple "mode" (most common value) logic — if you want stricter rejection, make it configurable in Phase 8.

## Tests

### Extends `test/test_sps_parser.py`

- `test_martin_linge_direction_parsed` — parse the Martin Linge fixture; assert `records[0].direction == 76.8`.
- `test_pxgeo_direction_is_none` — parse PXGEO fixture (no direction column); assert `records[0].direction is None`.
- `test_direction_uniform_per_line` — parse fixture with 5 points on line 2431; assert all have direction 76.8.

### New `test/test_line_aggregation.py` (pure Python with fake `QgsFeature`-equivalent dicts)

Not a QGIS test. Verify the mode/majority logic:

- `test_aggregate_direction_uniform` — 10 points all 76.8 → aggregated direction 76.8
- `test_aggregate_direction_empty` — no points have direction → aggregated is None
- `test_aggregate_direction_mismatch_logs_warning` — mixed directions → returns mode, emits warning

## Verify

1. `pytest test/test_sps_parser.py test/test_line_aggregation.py` — green.
2. Import Martin Linge SPS. Inspect the resulting GeoPackage attribute table — `PREV_DIRECTION` column is present and populated (76.8 or 256.8 per row).
3. Import PXGEO file. Same column exists but is NULL for every row.
4. After Generate Lines, the `Generated_Survey_Lines` layer also has a `PREV_DIRECTION` field populated per line.
5. Confirm no user-visible behavior change — Run Simulation produces the same output as Phase 3 baseline (feature not wired up yet).

## Rollback

Single `git revert`. The `PREV_DIRECTION` field disappears from new imports. Old imports with the field still work (QGIS tolerates extra fields). No data loss.

## Risks and unknowns

- **Backward-compatible field addition** — adding `PREV_DIRECTION` to `_create_sps_layer_fields` means existing QGIS projects that load an *old* GeoPackage without that field will see it as missing. QGIS treats missing fields as NULL, so this is non-fatal. Verify in smoke test.
- **Direction uniformity assumption** — user confirmed uniform per line. If real files violate this (e.g., mid-line direction change), the warning logs it but silently accepts the mode. Flag for Phase 8 if stricter handling is needed.
- **Source layer that already has `PREV_DIRECTION` via other means** — if the user currently adds the direction manually via QGIS field calculator, the Phase 4 import will now overwrite their manual value on re-import. Document this in the release notes.
- **Direction units** — assumed degrees (matches file values of 76.8 / 256.8). Not converted anywhere in Phase 4. Phase 6 will compare against vessel heading which is also in degrees (or needs conversion — VERIFY at Phase 6 execution).

## Hard Stop Gate

Phase 4 is complete when:
1. `pytest` green.
2. Martin Linge import populates `PREV_DIRECTION` correctly.
3. PXGEO import leaves `PREV_DIRECTION` NULL without error.
4. Generate Lines produces a `Generated_Survey_Lines` layer with aggregated `PREV_DIRECTION` per line.

**Claude MUST stop after Phase 4 and await explicit "proceed to Phase 5" from user. Do not auto-advance.**
