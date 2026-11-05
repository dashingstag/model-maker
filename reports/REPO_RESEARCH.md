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

## Round 3 — how to close the three hard limits (post step-2)

Re-researched after the projection-bake landed. Two earlier verdicts get
revised by new evidence; one gets confirmed harder than expected.

### Texture: PBR paint may already fit in 16GB — mmgp changes the math

The "21GB wall" assumed resident weights. Community evidence:

- **mmgp offloading works on ≤16GB** (Tencent-Hunyuan/Hunyuan3D-2.1#15 —
  confirmed by a user on a *mobile* 5080): `pip install mmgp`, then
  `offload.profile(paint_pipeline.models["multiview_model"].pipeline,
  profile_type.…)` keeps the heavy multiview diffusion CPU-side and
  streams. deepbeepmeep/Hunyuan3D-2GP reports shape 6GB / shape+paint
  ~24.5GB *unmanaged*, but profile 4 targets ≥6GB VRAM with sufficient
  system RAM — we have plenty.
- **Windows build friction is solved:** visualbruno/ComfyUI-Hunyuan3d-2-1
  ships prebuilt cp312 wheels for `custom_rasterizer` AND
  `mesh_inpaint_processor` (DifferentiableRenderer) — the two C++
  extensions that blocked the pip path.
- ComfyUI-3D-Pack caveat (issue #554): TexGen hangs traced to
  diffusers/transformers/accelerate drift — fix is
  `diffusers==0.30.0 transformers==4.46.0 accelerate==1.1.1`. NOTE this
  conflicts with our hy3dgen-mini pins (4.49.0/0.33.1) — 2.1 paint
  probably wants its own venv, not the shared ComfyUI one.
- TRELLIS 1 remains a real alternative engine: ~11.7–12.5GB measured
  (not the quoted 16), image→textured GLB direct, MIT. Slower/simpler
  texture than 2.1-PBR but one-shot.

**Revised verdict:** attempt Hunyuan3D-2.1 paint in a dedicated venv with
mmgp profile 4/5 + the visualbruno wheels. Projection-bake stays as the
`texture: "project"` degrade; `texture: "paint"` becomes the upgrade
opt-in. Text2Tex (12GB, SD2-depth, 15min/mesh) is a text-driven fallback
if image-conditioned paint proves immovable — but PyTorch3D is
conda/Linux friction on Windows.

### Topology: learned artist-retopo is a dead end — template-fit instead

A sibling research doc (Effigy 03-retopology) audited the field:

- MeshAnything V2: **S-Lab non-commercial** license, ~1.6k face cap — out.
- Tencent BPT: territory-restricted license — out.
- FastMesh/MeshFlow (Meta): non-commercial — out.
- DeepMesh 0.5B: Apache-2.0, but 1B variant (~30k faces) unreleased —
  **watch-list only**.
- QuadGPT/PolyGen/Tripo P2.0/Meshtron: closed or API-only — out.
- The doc's bottom line matches Blender's own docs: *no open tool emits
  animation-ready topology* (shoulder/elbow/knee/face loops).

**The guarantee is template fitting:** register a CC0 looped humanoid
base (MakeHuman hm08-style, or our own authored humanoid_v1-compatible
surface mesh) onto the generated silhouette via Blender
shrinkwrap/surface-deform — topology arrives by construction. For
non-humanoid props, QuadriFlow+decimate (already shipped) is the right
answer — props don't need deformation loops.

### Rigging: skin-tokens.cpp collapses the whole question

The best find: **localai-org/skin-tokens.cpp** — a C++23/GGML port of
SkinTokens/TokenRig by the LocalAI team. Runs on **CPU or Vulkan** — no
CUDA build, no torch env, single CLI:

- `skintokens-cli rig models/ character.glb out.glb --device vulkan` —
  full skeleton+weights on arbitrary meshes (F16 GGUF, ~1.6GB)
- `skintokens-cli skin` — **weights for an EXISTING skeleton**: give it a
  GLB carrying our `humanoid_v1` armature and it re-weights the generated
  mesh onto OUR rig — every clip, event, socket, attach3d and golden
  check stays valid. This is the conform path, learned rather than
  heuristic.
- Upstream VAST-AI/SkinTokens (MIT, Qwen3-0.6B, GRPO-refined) + the
  Aero-Ex/ComfyUI-SkinTokens node (headless bpy server — pipeline
  already speaks ComfyUI) remain options if the GGML port lags upstream.

**New integration order:**

1. `skintokens-cli skin` against a GLB with `humanoid_v1` embedded →
   generated mesh inherits the full animation contract. Probably the
   single highest-leverage move for the xianxia_hero production path.
2. Hunyuan3D-2.1 paint in a dedicated venv (mmgp + visualbruno wheels) —
   `texture: "paint"` provider opt-in.
3. Template-fit surface conform for actor silhouette quality (only if
   the generated shape reads badly at unit-render distance).
4. DeepMesh/artist-retopo stays watch-list; Tripo auto_rig stays the
   documented API fallback.
