# Phase 17d — Cartography notes for the 48-hour Lookahead PDF

Short reference of the cartographic principles applied in Phase 17d
and which config knob controls which. Future tweaks should start
here.

## Principles

1. **Visual hierarchy.** The chief navigator's attention goes to
   the survey plan first (Optimized_Path, Generated_Survey_Lines,
   Source Polygon), hazards and safety buffers second, and
   bathymetry/coastline/context last. PDF chrome (title, legend,
   scale, arrow, grid) should sit at the edges of the page and
   never compete with the plan.

2. **Figure–ground contrast.** The grid was previously a solid
   black reference line that obscured the survey plan. Light
   grey at 0.1 mm width (alpha ~180) now reads as a background
   reference without visually fighting the plan.

3. **Balance.** Map body targets ~75 % of the map page area after
   reserving gutters for the left-side grid annotation (18 mm)
   and the right-side legend (60 mm). The title band shrank from
   26 mm to 18 mm so ~8 mm returns to the map.

4. **Legend hygiene.** Chiefs read the legend looking for layer
   meaning, not QGIS symbology mechanics. Style subclasses ("Line
   Low→High", "Turn", "Run-In") collapse to a single entry per
   layer. Group headings are user-renameable; empty rename
   flattens the group (heading gone, children stay).

5. **Scale bar units.** UTM metres produced label strings like
   "0 1000,000 m" that read poorly. Kilometres are the field
   chief's natural unit at the scale we render.

## Knob map

| Principle | Knob | Location |
|---|---|---|
| Grid visibility | `PdfExportConfig.grid_style` (`off` / `light` / `normal`) | Dialog "Map controls > Grid" dropdown |
| Grid default | `light` | `services/pdf_export.py:_add_map_item` |
| Map body aspect | `_expand_extent_to_aspect` matches frame aspect before `setExtent` | `services/pdf_export.py` |
| Legend — one-entry-per-layer | `QgsMapLayerLegendUtils.setLegendNodeOrder(node, [0])` | `services/pdf_export.py:_add_map_item` |
| Legend — rename layer | QTreeWidget col 1 (double-click) → `pdf/display_names/<lid>` | Preview dialog |
| Legend — hide layer from legend (but show on map) | QTreeWidget col 2 → `pdf/hidden_from_legend/<lid>` | Preview dialog |
| Legend — rename group | "Rename legend groups…" button → `pdf/group_names/<name>` | Preview dialog |
| Legend — flatten group (drop heading, keep children) | Empty rename value | Preview dialog |
| Scale bar units | Forced to km in `_add_map_item` | `services/pdf_export.py` |
| Fit-to-layer persistence | `pdf/fit_layer/<project_basename>` (per-project) with `pdf/fit_layer_id` fallback | Preview dialog |
| Logo consistent sizing | `_place_logo_centered` helper (all three logos go through it) | `services/pdf_export.py` |
| Title band height | `_TITLE_BAND_H_MM = 18.0` | `services/pdf_export.py` |

## Rules of thumb

- A map with 4–8 layers visible is comfortable. More than 10 layers
  starts to overwhelm; hide non-essential ones via col-0 uncheck.
- Rename technical QGIS layer names to chief-facing labels
  ("installations", "safety_zones" → "Installations", "Safety
  Zones").
- If a logo looks stretched or off-center, the image aspect
  differs sharply from the 28×14 mm slot — the helper
  preserves aspect, so the image will appear smaller than the
  slot; that is correct behavior.
- Grid step auto-picks as a 1 / 2 / 5 × 10ⁿ "nice" number based
  on extent width. If the label spacing is odd, that usually
  means the extent is very narrow or very wide — adjust the
  Fit-to layer.
