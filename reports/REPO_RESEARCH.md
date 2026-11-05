# External repo research — adopted vs. logged

Surveyed for workflow improvements (session: Mixar follow-up). Status:
**adopted** = implemented in tree, **logged** = parked with rationale.

## Adopted

| Source | Pattern | Where it landed |
|---|---|---|
| mapbox/pixelmatch → whtsky/pixelmatch-py | OKLab perceptual diff + anti-aliased-pixel detection — AA/font noise no longer counts as drift | `tools/golden_check.py` (raw-channel fallback if uninstalled) |
| felippeomgt/mymeshy | Swappable provider adapters (`base.py` registry + `mock` so the contract is testable without GPU) | `tools/providers/{base,mock}.py`; glb briefs may set `provider: "mock"` — wired in `gen_component.py` |
| GeekatplayStudio/GameAssetMake | Plan rendered as a map *before* generation spends GPU | `tools/layout_map.py` — resolved members/patrol/attach from jobs.json → `composition/<goal>/layout_map.png`; wired into `run_goal.py` post-publish |
| godot-gdunit-labs/gdUnit4 | GDScript unit tests, CLI + JUnit | Vendored at `godot/addons/gdUnit4` (v6.2.3); `godot/tests/` suite covers runner shot/camera contracts; `check.py tests:gd` |
| trebeljahr/sprite-tools | Ramp-preserving palette recolor (`--ramp member=#newbase` re-tints a whole shading ramp; variant manifest v1 mirrors our `manifest.variants`) | **Evaluated: adopt.** Ramp swap on `xx_immortal_m` recolored robes brown→indigo with all embroidery/shading intact, skin ramp untouched — deterministic, silhouette-guaranteed, strictly better than i2i for pure colorways. Integration: port `src/lib/palette/{extract,ramps,oklab}.ts` (~350 lines pure-TS, no deps) to `tools/recolor.py` — a node/tsx runtime dep for one op violates the fewer-deps rule |

## Logged for future reference

| Source | What it offers | Why deferred / when to revisit |
|---|---|---|
| Comfy-Org/comfy-python-sdk | Typed workflow submit, progress streaming, blake3 asset-hash dedup | Installed. Our urllib transport (post/poll/history) works and error extraction is custom-fit; swap when gen needs asset uploads or streaming progress — don't refactor working code for elegance |
| felippeomgt/mymeshy (full) | Hunyuan3D-2-mini/TRELLIS/TripoSR image→3D + cleanup/decimate/xatlas-UV/PBR-bake chain, VRAM-budget degrade (albedo projection fallback) | **Adopted (shape path):** `tools/providers/hunyuan3d.py` live — accepted image → hy3dgen mini (~74s, 1.3M faces) → quadric decimate to `tri_budget` → GLB. Pins: transformers==4.49.0, diffusers==0.33.1, hub<1.0 (ledger #51). Remaining: texgen paint (needs custom_rasterizer CUDA build), retopo/rig for actor components — props/set pieces usable today |
| KumChaiYin/AI-to-GameReady-Pipeline | Minimal TripoSR→Blender-quadriflow→bake pipeline | Reference for the same provider work; simpler starting shape than mymeshy |
| trebeljahr/sprite-tools (rest) | Sheet-lint, collision polygons, normal maps, atlas pack, Godot export | Palette eval done above; the other tools are candidates per-need (lint → C3 checklist, normal-map → alternative to guide normals) |
| azagaya/laigter | Mature CLI normal-map generator (`--no-gui -d -n`, presets) | Alternative to guide-derived normals for sprites without a depth pass |
| kitepon-rgb/sprite-forge-mcp | Character LoRA + per-panel bible corrections that stick in history | Nicer recertify UX for sheets; revisit if multi-angle sheets become a component type |
| lumosai8/ComfyUI-OrbitSheets | Vision-judged frame selection from one consistent camera move | Same trick as our vision checklist for multi-view consistency |
| mav3r1ckmediastudio renegade-engine LC01 | Asset UUIDs vs paths; product-hash-observed-at-import provenance records | Our manifest shas cover most of it; "product hash at import" is a cheap future manifest field |
| amethyst/distill | Daemon-based import cache + dependency graph (Rust) | Too heavyweight; cited for the UUID-vs-path identity concept only |
