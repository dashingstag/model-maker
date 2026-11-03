# Pirate Pipeline Re-Assessment — Real Tools Run

Re-ran the three-approach pipeline evaluation **with real tools** (the original
used scripted stand-ins due to network blocks; all blocks are now lifted).

## Environment

| Tool | Version | Location |
|---|---|---|
| Blender | 4.5.15 LTS | `C:\Workspace\blender` |
| ComfyUI | 0.43.0 (CPU, torch 2.15.0+cpu) | `C:\Workspace\ComfyUI` |
| Checkpoint | SD1.5 `v1-5-pruned-emaonly` | `ComfyUI/models/checkpoints` |
| Godot | **4.6.3** ⚠ (original test: 4.5) | `C:\Workspace\Godot_v4.6.3-stable_win64.exe` |
| GPU | **RTX 5060 Ti present** ⚠ (original test: none; ComfyUI still ran CPU-only) | |

## Pipeline stages — all real

1. **Blender headless** (`tools/blender_pirate.py`): procedural pirate, 20
   separate meshes, armature + `walk` clip, `-colonly` collision node →
   `assets/models/pirate.glb` (122KB).
2. **ComfyUI API** (`tools/comfy_gen.py`): 4 images @ 512², ~112s each on CPU —
   green-screen character, portrait, sky, deck backgrounds.
3. **Post-process** (`tools/postprocess.py`): chroma-key alpha +
   largest-component isolation, tight crop, luminance→normal map, crops.
4. **Godot 4.6.3**: `--import` + windowed run of `test_runner` — 3 scenes,
   automated checks, metrics, 16 screenshots → `pirate_pipeline_test/reports/`.

## Results

| Check | Sprites | Real-Time 3D | Painted Cutout |
|---|---|---|---|
| Draw calls | **6** | **115** | **8** |
| Primitives | 12 | 8,402 | 16 |
| Frame p95 (ms) | 16.71 | 16.72 | 16.72 (vsync 60) |
| Pirate count | 6 ✓ | 6 ✓ | 6 ✓ |
| Distinct crew tints | 6 ✓ | n/a | yes |
| Meshes/pirate | — | 19 | — |
| Collision auto-import | — | 1 shape + 1 body ✓ (`-colonly` worked) | — |
| Walk animation | — | `walk` plays ✓ | — |
| Min captain↔crew sep. | — | 0.75 m | — |
| Parallax verified | — | — | ✓ sky −32px / deck −96px on 160px pan (exact 0.2/0.6 ratio) |
| Light2D + dialogue UI | — | — | ✓ both present |

## Visual-inspection findings (the mandatory step — 16/16 shots reviewed)

**Bugs found — all visual-only, none caught by automated checks:**

1. `sprites/*` — **chroma-key halo**: light cyan/green fringe around every
   sprite edge (residual from green-screen extraction).
2. `sprites/wide_all`, `walk_t1` — **captain overlaps crew #1** during patrol
   (2D sprite walk-through — same class as the original 3D bug).
3. `realtime_3d/crew_lineup`, `walk_t2` — **captain visually overlaps a crew
   member** despite 0.75m measured separation: different depth rows project to
   screen overlap. Automated check passed; only visible in screenshots.
4. `realtime_3d/*` — **washed-out colors** (recurrence of an original bug
   class): ambient 0.6 + sun 1.6 flattens navy pants to periwinkle, overall
   flat lighting.
5. `cutout/wide_all` — **composition waste**: sky layer almost entirely hidden
   behind deck layer — only a flat purple band shows; the generated sunset art
   is unused.
6. `cutout/low_light` — **PointLight2D positioned too high**: pirates render as
   near-pure silhouettes; light pool sits above their heads.

## vs. the original run

- Original: 8 draw calls (sprites) / 345 (3D) — ours: 6 / 115 (fewer mesh parts;
  the characteristic ordering is identical).
- Original bug ratio reproduced faithfully: **all 6 new bugs are visual-only**;
  automated checks passed everything except the (previously known) parallax
  measurement bug, which was a test-harness timing issue, now fixed.
- New this run: real Blender rig→glTF→Godot anim import, real `-colonly`
  collision import, real AI-painted art — all working end-to-end.
- Godot 4.6.3 vs 4.5: no compat issues observed.

## Verdict

Pipeline plumbing: **PASS** end-to-end on all three approaches.
Visual quality gate: **FAIL as shipped** — 6 visual bugs found, matching the
original test's conclusion that automated checks alone are insufficient.
