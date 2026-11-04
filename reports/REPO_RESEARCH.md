# External repo research — adopted vs. logged

Surveyed for workflow improvements (session: Mixar follow-up). Status:
**adopted** = implemented in tree, **logged** = parked with rationale.

## Adopted

| Source | Pattern | Where it landed |
|---|---|---|
| mapbox/pixelmatch → whtsky/pixelmatch-py | OKLab perceptual diff + anti-aliased-pixel detection — AA/font noise no longer counts as drift | `tools/golden_check.py` (raw-channel fallback if uninstalled) |
| felippeomgt/mymeshy | Swappable provider adapters (`base.py` registry + `mock` so the contract is testable without GPU) | `tools/providers/{base,mock}.py`; glb briefs may set `provider: "mock"` — wired in `gen_component.py` |
| GeekatplayStudio/GameAssetMake | Plan rendered as a map *before* generation spends GPU | `tools/layout_map.py` — resolved members/patrol/attach from jobs.json → `composition/<goal>/layout_map.png`; wired into `run_goal.py` post-publish |

## Logged for future reference

| Source | What it offers | Why deferred / when to revisit |
|---|---|---|
| Comfy-Org/comfy-python-sdk | Typed workflow submit, progress streaming, blake3 asset-hash dedup | Installed. Our urllib transport (post/poll/history) works and error extraction is custom-fit; swap when gen needs asset uploads or streaming progress — don't refactor working code for elegance |
| felippeomgt/mymeshy (full) | Hunyuan3D-2-mini/TRELLIS/TripoSR image→3D + cleanup/decimate/xatlas-UV/PBR-bake chain, VRAM-budget degrade (albedo projection fallback) | The real `provider` backends for mannequin→production. Next big step: port meshproc chain as `tools/providers/hunyuan3d.py` (~6-12GB VRAM fits local GPU) |
| KumChaiYin/AI-to-GameReady-Pipeline | Minimal TripoSR→Blender-quadriflow→bake pipeline | Reference for the same provider work; simpler starting shape than mymeshy |
| trebeljahr/sprite-tools | Sheet-lint, collision polygons, normal maps, palette-swap recolor, atlas pack, Godot export — CLI + JSON | Palette recolor could replace controlnet `sprite_variant` for pure colorways (deterministic, no i2i repaint risk — see ledger #21/#33). Evaluate when variants next need work |
| azagaya/laigter | Mature CLI normal-map generator (`--no-gui -d -n`, presets) | Alternative to guide-derived normals for sprites without a depth pass |
| godot-gdunit-labs/gdUnit4 | GDScript/C# unit tests, CLI + JUnit | runner.gd is the largest untested file; adopt when the GDScript surface stabilizes — needs the addon vendored into `godot/addons/` |
| kitepon-rgb/sprite-forge-mcp | Character LoRA + per-panel bible corrections that stick in history | Nicer recertify UX for sheets; revisit if multi-angle sheets become a component type |
| lumosai8/ComfyUI-OrbitSheets | Vision-judged frame selection from one consistent camera move | Same trick as our vision checklist for multi-view consistency |
| mav3r1ckmediastudio renegade-engine LC01 | Asset UUIDs vs paths; product-hash-observed-at-import provenance records | Our manifest shas cover most of it; "product hash at import" is a cheap future manifest field |
| amethyst/distill | Daemon-based import cache + dependency graph (Rust) | Too heavyweight; cited for the UUID-vs-path identity concept only |
