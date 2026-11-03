# Pirate Pipeline — Three-Approach Test Plan

Validates the three rendering/pipeline approaches from the pirate character test
(Sprites, Real-Time 3D, Painted Cutout) end-to-end: asset generation → Godot
import → scene assembly → automated checks → screenshot capture → mandatory
visual inspection → comparative report.

Primary goal: exercise the pipeline plumbing and close the bug-detection gap
(5 of 6 bugs in the prior run were only visible in screenshots).

---

## 0. Prerequisites

| Requirement | Notes |
|---|---|
| `pirate_pipeline_test/` | Godot project in this repo (rebuilt — original zip not present in workspace) |
| Godot binary | `C:\Workspace\Godot_v4.6.3-stable_win64.exe\Godot_v4.6.3-stable_win64.exe` — verified `4.6.3.stable` ⚠ test originally ran on 4.5; record compat warnings |
| Python 3 | For scripted stand-in generators (spritesheet, glTF, cutout painter) — stdlib only |
| Network/GPU | Not required — all generation is procedural per test constraints; `gl_compatibility` renderer used (no Vulkan/GPU dependency) |

Environment validation step (fail fast):
- `Godot_v4.6.3-stable_win64.exe --version` → **confirmed 4.6.3.stable** (≠ 4.5.x — known delta)
- `python --version` → ≥ 3.10
- Confirm `project.godot` parses and all three scene files exist

---

## 1. Test harness design

One driver script (`run_pipeline_tests.py`) runs the identical sequence for each
approach so results are comparable:

```
for approach in [sprites, realtime_3d, painted_cutout]:
    1. Run asset-generation stand-in script        → artifacts + manifest
    2. Run Godot import (headless, --import)       → capture import log
    3. Launch scene, run automated checks          → metrics JSON
    4. Capture screenshot set (see §4)             → PNGs
    5. Run vision inspection on every PNG          → pass/flag per image
    6. Emit per-approach report row
```

Determinism: fixed random seed, fixed camera positions, fixed lighting rig,
same 6 pirates (1 captain + 5 crew) in every approach.

---

## 2. Automated checks (run identically for all three approaches)

| Check | Method | Gate |
|---|---|---|
| Import integrity | Parse `--import` log for errors/missing resources | Zero errors |
| Scene integrity | Assert expected node counts, no missing textures | Zero missing |
| Draw calls | `RenderingServer`/`Performance.get_monitor(DRAW_CALLS)` | Log vs. per-approach budget (§3) |
| Triangle count | Per-character tri count | Under threshold (the one automated check that caught a bug last run — keep it) |
| Frame time | 300-frame capture, p95 frame time | < 16.6 ms target |
| Collision | Assert expected physics bodies exist | Per-approach expectation |
| Animation | Play every animation state, assert no errors | All states run |
| Pirate count | Exactly 6 pirates spawned, 1 flagged captain | Exact |

## 3. Per-approach tests

### 3A. Sprites (2D spritesheets)

- **Asset**: spritesheet generated; frame grid matches manifest; alpha channel intact.
- **Import**: `.import` files produced; texture filter setting as intended.
- **Functional**: all 6 pirates render; 5 crew are palette-recolors of one sheet —
  assert each crew member's modulation tint is distinct and correct.
- **Perf budget**: ~8 draw calls total; zero extra draw calls for the 5 recolored crew.
- **Visual QA**: no missing/blank frames, recolors visibly applied, no texture bleeding.

### 3B. Real-Time 3D (script-generated glTF)

- **Asset**: glTF parses cleanly; every independent body-part mesh present;
  materials/textures assigned (no default-gray fallbacks unless expected).
- **Import**: **collision bodies auto-created from object-name convention** —
  enumerate expected colliders from the name list and assert each exists.
- **Functional**: parts poseable/movable; **captain navigation — assert minimum
  separation distance between captain and crew during walk cycle** (regression
  for the walk-through-clipping bug).
- **Perf budget**: ~345 draw calls baseline — log it; flag >10% regression.
  Also record tri count (high — many separate meshes).
- **Visual QA**: **colors not washed out** (check light energy/exposure/
  material albedo); no inter-part clipping at joints.

### 3C. Painted Cutout (2.5D layered)

- **Asset**: all cutout layer textures generated; naming/order manifest matches
  parallax stack order.
- **Functional**: move camera along scripted path → parallax layers shift at
  different rates (assert layer offsets differ); lights respond to surface
  detail; **dialogue UI appears with captain's portrait** (regression item).
- **Perf budget**: between sprites and 3D — log exact draw calls.
- **Visual QA**: no visible layer seams/halos, correct z-ordering, portrait
  matches captain sprite, lighting lands on painted detail not flat quads.

## 4. Screenshot set (identical framing per approach)

| Shot | Purpose |
|---|---|
| `wide_all` | All 6 pirates, default lighting — baseline |
| `captain_closeup` | Detail/portrait check |
| `crew_lineup` | Recolor/mesh/cutout comparison across crew |
| `walk_cycle_t0/t1/t2` | Animation + clipping detection |
| `low_light` | Lighting response (washed-out / flat detection) |
| `ui_dialogue` | Dialogue box + portrait (cutout); equivalent UI state in others |

## 5. Mandatory visual inspection (the gap fix — non-negotiable)

Every PNG passes through a vision/verification step with a per-approach
checklist:

- [ ] No missing textures (magenta/black quads)
- [ ] No interpenetration (character-through-character, joint clipping)
- [ ] Colors not washed out / over-dark
- [ ] Correct layer ordering (cutout); correct recolor application (sprites)
- [ ] Expected UI elements present
- [ ] Lighting looks intentional, not blown

**Pipeline run FAILS if any screenshot is flagged** — a clean automated-metrics
run is not sufficient to pass.

## 6. Regression tests — the 6 known bugs

| Bug | Detection then | Test now |
|---|---|---|
| Excessive triangle count | Automated | §2 tri-count gate (3B) |
| Washed-out 3D colors | Visual only | §4 `low_light` + `wide_all` vision check (3B) |
| Captain walks through crew member | Visual only | Automated distance assertion + `walk_cycle` vision check (3B) |
| Visual bug #4 | Visual only | Encode as specific vision-checklist item once zip reveals which approach |
| Visual bug #5 | Visual only | Same — fill in from archive |
| Visual bug #6 | Visual only | Same — fill in from archive |

*(Confirm the exact 5 visual bugs against the framework doc and name them here.)*

## 7. Results & comparison

Emit `pipeline_test_report.md` with one row per approach:

| Approach | Draw calls | Tris | p95 frame | Auto checks | Vision checks | Bugs found |
|---|---|---|---|---|---|---|
| Sprites | | | | | | |
| Real-Time 3D | | | | | | |
| Painted Cutout | | | | | | |

Plus a findings list mapping each failure → screenshot → suspected cause.

## 8. Pass criteria

1. All three scenes assemble and render without import errors.
2. Automated checks pass within per-approach budgets.
3. **Zero flagged screenshots** in mandatory visual inspection.
4. All 6 prior bugs either absent or caught-and-reported by the new checks.
5. Report generated with comparable metrics across all three approaches.
