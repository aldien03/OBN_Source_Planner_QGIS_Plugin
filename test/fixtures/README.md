# SPS Test Fixtures

Hand-crafted minimal samples covering each supported SPS variant. Every
fixture has 5 data rows — enough to exercise parse, multi-row aggregation,
and edge cases without storing copies of real (sensitive) survey data.

Real customer files must NEVER be committed — `.gitignore` should filter
them (to be added in Phase 9 cleanup).

| Fixture | Format | Has direction? | Notes |
|---|---|---|---|
| `sample_sps_1_0.sps` | SPS 1.0 (1990 SEG) | no | 4-char line/SP fields, short data records |
| `sample_sps_2_1.sps` | SPS 2.1 canonical | no | 10-char line/SP fields, no extension columns |
| `sample_martin_linge.sps` | SPS 2.1 + direction | yes (76.8 / 256.8) | direction column at positions 80-86 |
| `sample_pxgeo.s01` | SPS 2.1 headerless | no | no H-records, integer line/SP |
| `sample_short_lines.sps` | SPS 2.1 | — | mixed good/truncated lines for error-log test |
