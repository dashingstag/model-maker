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

## Round 2 — remaining-limits tooling (texture / retopo / rig)

Researched against the real constraints: RTX 5060 Ti 16GB, Windows, torch
2.14+cu130 in the shared venv, pipeline already orchestrates ComfyUI over HTTP.

### Texture (hunyuan3d shape output is untextured)

| Source | What it offers | Verdict |
|---|---|---|
| **Blender projection-bake** | xatlas UV + project `accepted/` image onto mesh via Blender's own bake — zero new deps | **Adopt as v1.** mymeshy's degrade path; we own all the pieces already (xatlas installed, Blender scripted). Textures the exact concept art onto the mesh — honest and free |
| Tencent-Hunyuan/Hunyuan3D-2.1 Paint | PBR texture gen (RomanTex+MaterialMVP), mesh+ref-image → textured GLB | **Deferred — VRAM wall.** 21GB @ 6 views > 16GB. visualbruno/ComfyUI-Hunyuan3d-2-1 ships *prebuilt Windows wheels* for custom_rasterizer + DifferentiableRenderer (build friction solved); YanWenKun/Hunyuan3D-2-WinPortable adds mmgp offload that may fit 16GB. Revisit if quality demands exceed projection-bake |
| microsoft/TRELLIS.2 (4B) | image→PBR-textured GLB direct | Too heavy: ≥24GB VRAM, Linux-only tested. TRELLIS 1 (MIT, ~16GB, Windows workable per community) is the lighter alternative if a second full image→3D engine is ever wanted |
| daveredrum/Text2Tex | Multi-view diffusion texture painting, 12GB | Text-driven only (no reference-image conditioning); old torch 1.12 stack. Wrong fit |
| **ComfyUI-3D-Pack** (MrForExample) | TRELLIS, Hunyuan3D-2/2.1, InstantMesh, StableFast3D, PartCrafter as ComfyUI nodes; YanWenKun/Comfy3D-WinPortable = prebuilt Windows wheels | **High leverage:** our pipeline already POSTs workflows to ComfyUI — a 3D workflow could reuse the exact same transport/gating. Evaluate if the node-pack path beats the pip path for future 3D work |

### Retopology (generated meshes are 1.3M-face triangle soup)

| Source | What it offers | Verdict |
|---|---|---|
| **Blender `object.quadriflow_remesh`** | QuadriFlow built into Blender 4.x — fewer singularities than Instant Meshes | **Adopt.** Already installed; scriptable in the provider's post-step. `-f` face count maps to tri_budget |
| wjakob/instant-meshes | Field-aligned quad remesher, Windows CLI binary, ~10x faster than QuadriFlow | Alternative if Quadriflow proves slow at batch scale; single-binary dep is cheap |
| pymeshlab | `remeshing_isotropic_explicit` + quadric filters | Already installed; weaker than QuadriFlow for animation-ready loops but fine for props |

### Rigging (no skeleton on generated meshes)

| Source | What it offers | Verdict |
|---|---|---|
| **VAST-AI/SkinTokens** | Successor to UniRig (SIGGRAPH'25): mesh → skeleton + skinning weights in ONE autoregressive pass (Qwen3-0.6B, GRPO-refined). MIT license, ~1.6GB ckpts, trained on ArticulationXL2.0+VRoid+ModelsResource | **Adopt — the SOTA open answer.** UniRig's skeleton-only release is superseded. Fits 16GB easily. Output imports to Blender→GLB; then either retarget clips or conform to humanoid_v1 |
| VAST-AI/UniRig | Skeleton prediction only (skinning model shipped later/separate) | Superseded by SkinTokens |
| **Blender auto-weights + surface-deform onto `humanoid_v1`** | Skin a generated mesh onto the EXISTING rig — zero new deps, preserves the entire clip/sync/check/shot infrastructure | **The pragmatic bridge:** for humanoid actors, conforming generated geometry to our rig keeps every action/attach3d/golden valid. Use before/alongside SkinTokens |
| hjwdzh/QuadriFlow / RigNet (zhan-xu) | Older learned/auto rigging | Weaker than SkinTokens |
| Tripo `auto_rig` (mymeshy's backend) | Cloud auto-rig → rigged GLB | API fallback only — breaks the local-first rule |

### Recommended integration order

1. `tools/recolor.py` port (sprite-tools algorithm — proven this session)
2. **Provider post-step** — ✅ DONE (`tools/blender_texture.py`, wired into `hunyuan3d.generate`): smart-UV + projection-bake of the `accepted/` image to albedo (manual ortho projection — `uv.project_from_view` needs a UI context; alpha-bbox crop; normal-weighted 4-view merge via `--view turntable`) + `quadriflow_remesh` retopo with decimate fallback (QuadriFlow overshoots `target_faces` on dense organic input). `check.py texture:smoke` covers it headless
3. **SkinTokens provider stage** for rigged actors (new component class: `glb` + `rig: auto`), Blender conform-to-humanoid_v1 as the fallback
4. Comfy3D nodes only if the pip path shows friction at scale
