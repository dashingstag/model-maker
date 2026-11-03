# Bug Ledger — pipeline v2 (hybrid 3D+SD), pirate_deck_scene

Format: bug → where caught → fix applied → gate that owns it now.
"Component" bugs die on the component track; only relational bugs live in A2.

| # | Bug | Class | Found by | Fix applied | Owning gate | Status |
|---|---|---|---|---|---|---|
| 1 | Chroma-key halo on sprite edges | component | shot review (run 1) | BiRefNet matting instead of green-screen; despill+erode in extract | C2 `fringe_px` metric (captain: fringe_ok=true) | FIXED |
| 2 | Sprite walk-through | composition | A2 same-row overlap (398 events → 0 after row split) | captain on front row (y=648), crew back row (y=560); A2 counts same-row pen>40px only | A2 `same_row_overlap_events` (=0 now) | FIXED |
| 3 | Washed-out colors | component | C3 `sat_mean` + unit lit.png eyeball | dusk palette into prompt; sat_mean 0.688 | C3 histogram/sat metric | FIXED |
| 4 | Hero sky art ~0% visible | composition | A1 `sky_visible_pct` (=0.0 first run) | deck layer y_off=380 → sky 52.8% visible | A1 min_visible_pct gate (52.8 ≥ 40) | FIXED |
| 5 | Light rig too dark → silhouettes | composition | `captain_lit_coverage`=0.035 + lit.png | canvas_modulate #73738c→#a8a8bc, energy 1.4→2.2, light anchored -290px | A2 `lit_coverage` | PARTIAL — coverage still low (~0.04); floor/anchor needs calibration vs. dark-toned art |
| 6 | Captain/crew visually overlap despite separation | composition | A2 — now correctly classified: 306 cross-row occlusions are *expected* front-row depth passes, not bugs | n/a — check distinguishes same-row violation from front-row occlusion | A2 split metric | RESOLVED (was misclassified check, not a bug) |
| 7 | Crew palette-shift bleeds into skin (cyan/green faces) | component | wide_all shot review | mask tightened twice: hue∈[0.90,1.0], sat>0.4, val<200 — painted skin shares red-pink hues with the crimson coat | C3 unit render review | OPEN — palette-shift on painterly art is fragile; recommend region-masked recolor (coat band rows only) or per-part generation |
| 8 | ControlNet hallucination (ship-body pirate) | component | candidate review s1002/s1200 | rejected at curation — batched seeds exist exactly for this | C1 vision curation | FIXED (by process) |
| 9 | BiRefNet-ZHO node: arch mismatch vs official weights | infra | execution_error trace | dropped node; matting moved to extract via rembg birefnet-general ONNX | — | FIXED (better separation anyway) |
| 10 | Eevee ignores `view_layer.material_override` | infra | identical beauty/depth renders | per-mesh material swap in blender_render.py | — | FIXED |
| 11 | `-colonly` box renders in Blender (Godot convention unknown to it) | component | slab occluding renders | hide_render on `-colonly` nodes | C2 sanity render | FIXED |
| 12 | ComfyUI jobs failing silently (wait loop hung) | infra | queue polling | wait_done raises on execution_error | — | FIXED |

## Check-accumulation additions this run
- `sky_visible_pct` (A1) — proven: caught 0%→52.8%
- `same_row_overlap_events` vs `cross_row_occlusions` (A2) — proven: 398 → 0 violations
- `captain_lit_coverage` (A2) — needs calibration before it's a reliable gate (dark art + dusk rig reads ~0.04 despite visible lighting)

## Open items for next run
1. Crew variants: region-masked recolor or generate distinct crew via ControlNet+palette prompts — **not certified** (all other 5 components certified).
2. Calibrate lit_coverage floor/anchor against dusk-toned art.
3. walk_b s1201 accepted blind — verify on unit_render/walk strip.
