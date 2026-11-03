# Concept Art → Usable Godot Asset — Workflow

A brief describes the **goal** — usually a scene or set of objects ("pirate
captain + 5 crew on a ship deck at dusk"). The pipeline does **not** process
that goal as one blob. Stage 0 decomposes it into **components**; each
component runs its own gated track and is not allowed into scene assembly
until certified. Composition work handles only what cannot be checked on a
component in isolation.

```
goal brief ──decompose──> component briefs
                              │  per-component track (independently gated —
                              │  serial today on one CPU ComfyUI):
                              │  gen ──> metric pre-filter ──> human pick ──>
                              │  extract/build ──> unit render ──> certified
                              v
                    composition track (once per goal):
                    assemble ──> relational checks ──>
                    visual gate ──> package
```

**Core rule:** if a bug can be seen on the component alone, it is a component
bug and must die on the component track. Composition gates exist only for
relational failure modes (overlap, occlusion, light interaction).

**Determinism rule:** any two runs are diffable **within a pinned toolchain**
(blender/comfy/torch/godot versions + device + model sha256, recorded per run
in `gen.json`/`manifest.toolchain`). Animation/shot capture is **seek-based**,
never wall-clock: `AnimationPlayer.seek(t)` + `set_process(false)` before
capture. Golden diffs are **tolerant** (per-pixel Δ ≤ 3/255, changed-pixel
fraction ≤ 0.5%), re-blessed on recorded toolchain bump — pixel-exact and
byte-for-byte claims are false in practice (uid minting, GPU/driver
rasterization, ComfyUI device drift).

## Build status — what exists vs. designed

| Stage | Status |
|---|---|
| Stage 0 scaffold (`tools/scaffold.py`) | ✅ built — @ref resolve, certified-skip, brief slices, spec.json |
| C1 generate (`tools/gen_component.py`) | ✅ built — geometry-guided sprite path, txt2img for ui/parallax, glb build |
| C2 extract (`tools/extract.py`) | ✅ built — rembg matting, despill, variant transform, manifest |
| C3 unit render | ✅ built — `godot/` harness, job JSON, unit shots per component |
| publish (`tools/publish.py`) | ✅ built — `processed/` → `godot/assets/components/`, job file |
| A1 assemble / A2 checks / A3 shots | ✅ built — spec→jobs→`runner.gd`→`report.json` + shot set |
| `tools/pipelib.py` (locks, atomic_json) | ✅ built — wired into scaffold/gen/extract/publish |
| `tools/lint_tree.py`, vision.json, waivers | ❌ not built — ledger records verdicts at run level only |
| `run_goal` orchestrator | ⚠ partial — stages run, end-to-end driver per hardening rules |

---

## Folder management — a first-class part of the design

Every artifact has exactly one home, every path encodes provenance, and a
component's identity **is** its folder. The rules are enforced by
`tools/lint_tree.py` (work backlog) — a component with artifacts in the
wrong place fails like one with a bad sprite.

### Canonical layout

```
model-maker/
  briefs/                        # one <goal>.brief.json per goal — checked in
    pirate_deck_scene.brief.json

  shared/                        # named, reusable vocabularies — checked in;
                                 # briefs reference them via @<kind>/<name>
    styles/painted_game_art.json     # suffix/negative/subject_bg/scene_suffix
    palettes/dusk.json               # named hexes + prompt_hints (color NAMES)
    rigs/std_dusk.json               # canvas_modulate + light_2d + unit_render_bg
    poses/walk_cycle.json            # named bone-rotation poses for renders

  models.json                    # generative-model registry + model_meta
                                 # (license/source/sha256/custom-node deps)
  tools/env.json                 # tool exe paths + versions — never hardcoded
                                 # in scripts

  pipeline/
    components/                  # THE component library — global namespace
      captain/                   # (new ids take a domain prefix: pirate_*)
        brief.json               # component slice: constraints + resolved
                                 # style/palette snapshot + goal
        .lock                    # present while a stage owns the component
        candidates/              # every generated seed — files ignored, but
          captain_s011.png       # index.json below IS checked in
          index.json             # per-candidate: seed, resolved prompt,
                                 # sampler/steps/cfg, model+sha256, device,
                                 # comfy version, elapsed, vision:{score,flags}
        accepted/
          src.png                # the curated pick — CHECKED IN (signed-off)
          gen.json               # winner's sidecar + curation score
        processed/               # extraction/build outputs — CHECKED IN
          sprite.png  sprite_n.png
        unit_render/             # Godot isolation renders — CHECKED IN
          neutral.png  lit.png
          vision.json            # checklist verdicts (see Vision section)
        history/rev<n>/          # archived prior rev on re-certification
        manifest.json            # THE state file — see schema below
      crew/                      # variant component — members grouped inside:
        processed/crew_01/ …     #   crew_05/, listed in manifest.variants
      portrait/  bg_sky/  bg_deck/
      captain_3d/
        build/  export/captain_3d.glb  sanity/

    composition/
      <goal>/                    # one working area per brief
        spec.json                # resolved assembly spec (rig/shots/layout)
        jobs.json                # harness job file written by publish
        shots/                   # the standard shot set
        report.json              # metrics + provenance (versions, shas)

  godot/                         # Godot project — generated by publish step,
    assets/components/<id>/      # never hand-edited; .import sidecars
    project.godot                # committed (they pin uid:// + import flags)
    scenes/  scripts/

  golden/<goal>/                 # blessed shots — checked in, tolerant diff,
                                 # stable subset only (no ui_dialogue text)
  dist/<goal>/                   # packaged output — gitignored, rebuildable
  reports/                       # assessments + BUG_LEDGER.md — checked in

  experiment/<name>/             # work not produced through these gates —
                                 # self-contained, preserved for reference;
                                 # pipeline stages never read from it
```

### manifest.json schema

The single mutable file in a component folder; written atomically
(tmp + rename). All other artifacts are write-once per rev.

```json
{
  "schema_v": 1,
  "id": "captain", "type": "sprite", "rev": 1,
  "status": "wip|generating|curated|processed|certified|stale|needs_human",
  "constraints": {"h_px": 384, "pivot": "feet", "poses": ["idle","walk_a","walk_b"]},
  "inputs":  {"captain_3d": "sha256:…", "@styles/painted_game_art": "sha256:…"},
  "artifacts": {"processed/sprite.png": "sha256:…"},
  "metrics": {"fringe_ratio": 0.003, "palette_coverage": 0.71},
  "toolchain": {"blender": "4.5.15", "comfy": "0.43.0", "torch": "2.15+cpu",
                "device": "cpu", "models": {"dreamshaper8": "sha256:…"}},
  "waiver": null,
  "history": [{"rev": 1, "ts": "…", "reason": "…"}]
}
```

### Rules

1. **One component, one folder, everywhere** — including inside `godot/`:
   `assets/components/captain_3d/model.glb`, never a loose `models/` dir.
   Nothing pipeline-produced lives loose in a flat dir.
2. **Stages own subfolders; append-only per rev.** A stage writes only into
   its own subfolder. Re-running a stage never overwrites — it writes the
   new rev's outputs and the validator archives the old stage outputs to
   `history/rev<n>/`. `manifest.json` is the only mutable file.
3. **Candidates are kept on disk** (re-gen costs minutes on CPU) but their
   *files* are gitignored; `candidates/index.json` is checked in so provenance
   and re-curation data survive cleanup.
4. **Certified evidence is checked in.** `accepted/`, `processed/`,
   `unit_render/` are what gates signed off on and cannot be regenerated
   exactly — `.gitignore` only excludes `candidates/` and `build/`.
5. **A folder without `manifest.json` is WIP.** Certification = manifest
   reaches `status: certified` + `unit_render/` vision-passed.
6. **Filenames carry provenance from birth:** `<id>_<seed>.png` (pose-aware
   where applicable), one seed per file — never `batch_size>1`.
7. **Godot `assets/` is a build artifact**, published with `.import`
   sidecars. `.import` files are checked in — they pin `uid://` refs and
   non-default flags (`compress/mode` lossless for `*_n.png`,
   `process/normal_map_invert_y`). Never delete `.import` on re-publish —
   uids must survive content swaps.
8. **Git policy:** `briefs/`, `shared/`, `golden/`, `reports/`,
   `godot/**/*.import`, all `*.json` manifests/indexes, and checked-in
   evidence are committed; `candidates/` binaries, `build/`, `dist/` are
   ignored. Anything a human signed off on is never ignored.
9. **Invalidation is transitive and mechanical.** A component re-run bumps
   `manifest.rev`, archives the old rev to `history/`, and marks every
   manifest whose `inputs` chain reaches it `stale` — derived variants,
   `spec.json`, shots, dist. Downstream gates fail on stale inputs.
   `manifest.status` transitions only via atomic manifest rewrite.
10. **Locking (implemented — `tools/pipelib.py`).** Durable claim =
    `brief.json`'s `goal` field; in-flight exclusion = `<dir>.lock`
    (mkdir-atomic, `owner.json` {owner, pid, ts}, stale-swept on dead pid
    or 2 h age). Stage tools lock their component plus dependency bases
    (`captain_3d` for sprites, `of` for variants) — always sorted by id.
    Publish holds `composition/<goal>.lock` then `godot/.publish.lock` —
    the only multi-lock site, fixed ordering, deadlock-free.

`tools/scaffold.py <brief>` (built) creates only what the brief needs;
`tools/lint_tree.py` (backlog) audits the rules.

### Adding over time

| Adding | Goes in | Referenced by |
|---|---|---|
| A goal | `briefs/<goal>.brief.json` | `composition/<goal>`, `golden/<goal>`, `dist/<goal>` |
| A component | `pipeline/components/<domain>_<id>/` | any brief — the library is shared |
| A generative model | entry in `models.json` (+ `model_meta`) | tools and briefs via `@<id>` |
| A style / palette / rig | `shared/<kind>/<name>.json` | briefs via `@<kind>/<name>` |
| A tool binary/path | `tools/env.json` | every script — no hardcoded exe paths |
| A side experiment | `experiment/<name>/` | nothing — self-contained |

Growth rules:

- **Reuse-first scaffold, constraint-checked.** Scaffold skips a component
  only when the manifest is `certified` **and** the requested constraints ⊆
  the certified `constraints` set (type, h_px, pivot, anims, budget, rig).
  A tighter request → new id or `--recertify`; a looser one may reuse.
- **Single active rev; pins are assertions.** `"rev": N` in a brief asserts
  equality — the validator fails loudly on mismatch rather than clobbering
  the current rev. Breaking changes get a new id (`captain_v2`), which is
  also why ids take a domain prefix.
- **`@` refs, not copies.** Style/palette/rig live once in `shared/`; the
  brief slice records the *resolved snapshot* so "which prompt produced
  this" survives later edits to shared files.
- **Model names live in `models.json`.** Checkpoints/ControlNets/matting by
  id; `model_meta` carries license, source, sha256, and custom-node
  requirements (e.g. BiRefNet Zho nodes — server must not run with
  `--disable-all-custom-nodes`).

---

## Concurrency contract — running multiple workflows

Two-level ownership:

- **Durable claim = `brief.json`'s `goal` field.** Scaffold writes it; an
  uncertified component already claimed by another goal is reported
  "claimed by goal '<x>'" and skipped; a certified component whose
  constraints don't match the request reports a conflict. Ownership ends
  at `status: certified` — certified components are shared by all goals.
- **In-flight mutex = `<dir>.lock/`** — mkdir-atomic, `owner.json`
  {owner, pid, ts}, held for one stage invocation, stale-swept on dead
  pid or 2 h age. Stage tools accept `--wait N` to poll instead of
  failing fast.

Serial points (fixed ordering — no deadlock):

| Lock | Covers |
|---|---|
| `pipeline/components/<id>.lock` | C1–C3 stage invocations; `sprite` also locks `captain_3d`, `sprite_variant` locks its `of` base — sorted by id |
| `pipeline/composition/<goal>.lock` | spec.json write (scaffold); publish+run (publish) — taken **before** the publish lock |
| `godot/.publish.lock` | `pub_tree` swaps + Godot `--import` (import is not concurrency-safe) |

Publish swaps component dirs by rename-pair (`*.new`/`*.old`) — readers
never see a torn tree; every JSON write goes through `atomic_json`
(tmp + `os.replace`).

What parallelizes: distinct components' C1–C3 across distinct goals.
What does not: ComfyUI gen — one server, one queue; parallel briefs
interleave but throughput is unchanged (the win is correctness, not
speed — even on GPU the queue serializes).

---

## Vision, human gates, and waivers

"Vision pass" is meaningless without an executor. The pipeline uses three
tiers, in order:

1. **Metric pre-filter (automated, per candidate):** alpha-fill ratio vs.
   spec `h_px`, bbox aspect, residual-key-color fraction, palette-hue
   coverage, laplacian-variance sharpness. Ranks candidates, rejects obvious
   failures — no judgment calls.
2. **Human contact-sheet pick (once per component, curation):** the top 2–3
   survivors rendered as one contact sheet; a human picks the winner. This
   is the **art-direction sign-off** — the only positive "is this the right
   pirate" check in the pipeline, placed *before* compute is sunk.
3. **Agent checklist (C3 unit renders, A3 composition shots):** the agent
   reviews saved PNGs against the per-stage checklist and writes verdicts.

Every vision verdict is persisted as `vision.json` next to the artifacts it
covers: `{actor, checklist_items, per_image verdicts, timestamp}` — "vision-
passed" in a manifest is auditable, not asserted.

**Escalation and waivers.** If no candidate passes after `max_regen_rounds:
2` (same-prompt-different-seed does not fix prompt-level capability
failures), the component goes `status: needs_human` — escalate prompt
rewrite or accept with a `waiver` field. Every gate accepts `waiver:
{check, reason, approved_by}` so one flaky check can't block the pipeline;
waivers are recorded in the manifest, not silent.

**Bug ledger** (`reports/BUG_LEDGER.md`): a row is valid only if it names a
runnable `check_id` or an explicit waiver — never a promise. Checks that
never fire may be retired by ledger decision.

---

## Stage 0 — Goal brief → component decomposition

`briefs/<goal>.brief.json` — checked-in, versioned with the repo. Field
reference (as implemented by `tools/scaffold.py`):

```json
{
  "goal": "pirate_deck_scene",
  "style": "@styles/painted_game_art",
  "palette": "@palettes/dusk",
  "components": [
    {"id": "captain",    "type": "sprite",  "h_px": 384, "pivot": "feet",
     "prompt_core": "pirate captain, red coat, tricorn hat, eyepatch, orange beard, cutlass",
     "poses": ["idle", "walk_a", "walk_b"]},
    {"id": "crew",       "type": "sprite_variant", "of": "captain",
     "count": 5, "vary": ["coat_color", "trim"], "method": "palette"},
    {"id": "portrait",   "type": "ui_image", "h_px": 256,
     "prompt_core": "bust portrait of a pirate captain, tricorn hat, eyepatch, grey beard, dramatic rim light"},
    {"id": "bg_sky",     "type": "parallax", "factor": 0.2,
     "hero_art": true, "min_visible_pct": 40,
     "prompt_core": "sunset sky over the sea, orange and purple clouds, distant ship silhouettes"},
    {"id": "bg_deck",    "type": "parallax", "factor": 0.6,
     "prompt_core": "pirate ship wooden deck and railings overlooking ocean, warm dusk light, no characters"},
    {"id": "captain_3d", "type": "glb", "tri_budget": 4000,
     "anims": ["idle", "walk"], "collision": "capsule-approx"}
  ],
  "composition": {
    "lighting_rig": "@rigs/std_dusk",
    "layout": {
      "rows": [{"id": "front", "y": 648}, {"id": "back", "y": 560}],
      "captain_row": "front", "crew_row": "back",
      "spacing_px": 170, "patrol": {"speed_px": 110, "from_x": -120, "to_x": 1200},
      "light_anchor": {"of": "captain", "offset": [40, -290]},
      "feet_pivot": true
    },
    "shots": ["wide_all", "captain_closeup", "crew_lineup",
              "walk_t0", "walk_t1", "walk_t2", "low_light", "ui_dialogue"]
  }
}
```

Semantics:

- `pivot`: `"feet"` = bottom-center of alpha bounds (px); `"center"` = bbox
  center. Collider = alpha bounds shrank 10%, in px; the px→world scale
  (`h_px` / world height) is stored in the manifest.
- `vary` names palette regions (e.g. `coat_color`, `trim`); `method`
  selects the transform: `"palette"` = region-masked hue remap inside the
  alpha — deterministic numpy, but fragile on painterly art where hues
  bleed across regions (ledger #7: skin picked up coat hues — needs a
  tighter mask or per-part generation). Geometry-level differences are out
  of scope — that requires a gen, not a variant.
- A `count: N` variant component expands inside its own folder:
  `processed/<variant_id>/` per member (`crew_01…crew_05`), listed in
  `manifest.variants`, each variant's `inputs` pinning the base artifact
  sha. Godot mirrors as `assets/components/crew/crew_01/`.
- `layout` drives A1 placement and A2 expectations: named depth `rows`
  with y-coords (row assignment per component class — this is the fix for
  the walk-through bug class: captain and crew on different rows),
  `spacing_px`, scripted `patrol` path, `light_anchor` relative to a named
  component, `feet_pivot` foot alignment.
- `min_visible_pct`: measured at A1 by analytic rect subtraction (see A1).
- A brief is immutable once its components reach `certified` — change it by
  bumping the brief file (checked in) and re-scaffolding; scaffold diff is
  the change log.

**Exit gate:** every component `type` has a handler
(`sprite|sprite_variant|ui_image|parallax|glb`); every declared constraint
has an implementer; every `@` ref resolves in `shared/` or `models.json`;
component dirs exist for each uncertified id with a `brief.json` slice
(component entry + resolved style/palette snapshot + goal + ref shas).

---

## Component track — one run per component

Independently gated and parallel-*able* — but **serial in practice today**:
one CPU ComfyUI instance queues prompts; GPU enablement (backlog) changes
this. Each stage invocation locks the component (and dependency bases,
sorted by id) for its duration — see the concurrency contract.

### C1 — Generate → `candidates/` (per component type)

| Type | Path | Budget (CPU, measured) |
|---|---|---|
| `sprite` (GLB-backed) | Blender multipass (beauty/depth/normal from sibling `glb` export) → ControlNet-depth + checkpoint → painted PNG (matte at C2) | ~400 s/seed |
| `sprite` (no GLB) | txt2img "isolated on plain white" + BiRefNet matte | ~350–450 s/seed |
| `ui_image` | txt2img 512² + `subject_bg` | ~350–450 s/seed |
| `parallax` | txt2img **≥768 wide** + `scene_suffix` (pan headroom; gen-then-crop for wider) | ~350–450 s/seed |
| `sprite_variant` | transform-only — no gen | seconds |
| `glb` | `blender_pirate.py` → `build/` + `export/` | seconds |

Green-screen chroma-key is **retired** — gen output is a painted RGB on a
plain background; the alpha is derived at C2 by packaged `rembg`+
birefnet-general ONNX (hardening rule 7: pip-packaged inference beats
vendored custom nodes — the ZHO node cost two sessions before rembg worked
first try). No key color in the gen path → no halo class by construction.

**Improvement steps (in order of payoff):**

1. **Seeds → metric pre-filter → human pick.** Default 3 seeds (cap 4),
   early-stop at first pre-filter pass; survivors to a contact sheet for the
   human pick. Rejected seeds logged in `candidates/index.json` with
   resolved prompt/sampler/seed/device so re-curation is data-driven.
2. **Style-lock by construction:** one checkpoint for every painted
   component (last run mixed sd15 + DreamShaper — that *caused* the "three
   different games" finding); shared `suffix`/`negative` via `@styles`;
   optional histogram-match post-pass against the accepted captain.
   IP-Adapter → backlog (needs clip_vision files not installed).
3. **Palette via names + masked coverage gate.** `prompt_hints` uses color
   names (hexes are meaningless to CLIP); gate = within the alpha, fraction
   of subject pixels within ΔE≤30 of *any* palette hex ≥ floor — a coverage
   floor, not a per-region match. Record measured-vs-target in `gen.json`.
4. **Render > target res, matte at gen-res, then downscale.** Never
   downscale pre-key: it averages spill into more mixed pixels.
5. **For GLB:** materials from palette, `-colonly` collision naming, and
   the sibling-export contract — `sprite` components render depth from the
   goal's `glb` component (pose bones + seeds in `candidates/_spec.json`).
6. **Failure recovery:** `index.json` written incrementally; a re-run skips
   seeds already on disk. Mid-run abort loses at most the in-flight seed.

**Gate:** ≥1 candidate passes pre-filter + human pick → `accepted/` +
`gen.json`; `index.json` complete.

### C2 — Extract / build → `processed/` (`tools/extract.py`)

1. **Alpha by matting at extract, not in the gen graph.** `rembg` session
   (`birefnet-general` ONNX) on the accepted painted PNG → despill clamps
   `G ≤ max(R,B)·1.1` **only on near-key-hue pixels** (spare legitimate
   greens), soft-erosion `α = clip(α−24)` not binary erode (thin swords
   survive), then tight crop + downscale.
2. **Fringe metric = ratio, not count.** Band = `0 < α < 255` post-erode;
   metric = fraction of band pixels where `G − max(R,B) > 20`; gate < 1–2%.
   Runs again at C3 on the rendered frame — catches halos that only show
   against real backgrounds.
3. **Normal-map hierarchy:** GLB-backed → reuse Blender view-space normals
   (`postprocess2.py` path, R=+X / G=+Z / B=−Y OpenGL convention, alpha
   matched to sprite); pure-2D → luminance blurred σ≈2 px *before* gradient,
   strength ≤1.5 — or ship flat normals (flat beats bad). Convention pinned
   in manifest; verified in the C3 `low_light` unit render.
4. **Manifest out** (schema above): pivot/anchor, frame size, collider px,
   normal-map pairing, parallax factor, px→world scale.
5. **For GLB:** budget at export (tris/mesh count — fail in Blender);
   node list vs. manifest; anim sanity strip → `sanity/` (turntable + walk
   frames) catches joint clipping before Godot adds variables.
6. **`sprite_variant`:** region-masked hue remap per the brief's `vary`
   table; `inputs` records base artifact sha.

**Gate:** fringe ratio < 1–2%; `processed/` + manifest written; GLB
validator clean.

### C3 — Unit render → `unit_render/` (the component's integration test)

1. **No import needed.** The harness loads files directly:
   `Image.load_from_file` / `ImageTexture.create_from_image` for sprites +
   normals, `GLTFDocument.append_from_file` for GLBs. (Exception: `-colonly`
   → physics bodies is an *importer* convention — collision is asserted at
   A1 on the imported scene, not here.)
2. **One fixed `unit_render.tscn` + a JSON job file** passed as a `--` arg —
   no per-component scene generation. Standard rig from `@rigs/`, neutral
   backdrop (`unit_render_bg`), camera from `h_px`.
3. **Deterministic capture:** `AnimationPlayer.seek(t)` per anim state,
   `set_process(false)` before capture — never accumulate `_process` delta
   (the flake class the original test hit).
4. **Launch contract:** `gl_compatibility` cannot render `--headless` on
   Windows — run windowed, unminimized, `--resolution` + `allow_hidpi=false`
   pinned (or a fixed-size SubViewport). The `mobile`/`forward_plus`
   renderer would allow true `--headless` Vulkan on the RTX 5060 Ti —
   alternative, not default.
5. **Checks on the render:** HSV histogram vs. palette (washed-out, bug #4 —
   on the isolated component, not in a busy scene); fringe-on-render; one
   frame per anim pose for joint/clip vision; `low_light` unit shot verifies
   normal-map convention.

**Gate:** unit render passes metrics + agent checklist → `vision.json`
written, `manifest.status: certified`.

**Publish (after C3, batched per goal):** copy `processed/` →
`godot/assets/components/<id>/` **with** `.import` sidecars (uid pinned
from manifest on first import); one `--import` per goal, serialized behind
the project lock. A failed component loops to its earliest broken stage —
the validator archives stale stage folders to `history/`, nothing is
hand-deleted.

---

## Composition track — once, per goal → `pipeline/composition/<goal>/`

Runs only after all declared components are certified (and none stale).

### A1 — Assemble → `spec.json` + engine-built scene

- **No hand-templated `.tscn`.** A builder script in `godot/` reads
  `spec.json` + component manifests and constructs the scene in code, then
  `PackedScene.pack()` + `ResourceSaver.save()` — the engine writes valid
  uids. Pivots, colliders, z-order, parallax factors, light anchors all come
  from manifests + `@rigs/` — no hand-placed constants (bug #6's light is
  anchored to the character's alpha bounds, per the rig's `anchor` field).
- **Layer visibility is analytic, not rendered.** Parallax layers are
  opaque full-bleed rects → visible % = layer rect minus occluder rects in
  screen space. `hero_art` must hit `min_visible_pct` (bug #5: the sunset
  was ~95% occluded). A visible-toggle render pass exists as occasional
  audit only.
- **Rig mapping:** `@rigs/*.json` → engine params (CanvasModulate color,
  PointLight2D energy/scale/position) — a named mapper, versioned with
  `shared/`.

### A2 — Relational checks → `report.json` (only what isolation can't see)

| Check | Catches | Implementation |
|---|---|---|
| Screen-space overlap | walk-through (#2), projected overlap (#3) | 2D: `get_global_transform_with_canvas` × texture size → `Rect2`; 3D: `camera.unproject_position` of AABB corners. Flag when intersection **area > 10% of the smaller rect, sustained ≥3 sampled frames** during scripted motion; per-shot allowlist from the brief (crew_lineup legitimately overlaps). **Flag-not-fail for the first runs to calibrate.** |
| Layer visibility | composition waste (#5) | analytic, per A1 |
| Lit coverage | light placement (#6) | transform each sprite's alpha to screen space, count captured pixels above a luminance floor — floor is **per-shot** (low_light gets a lower-but-nonzero floor) or a ratio vs. the C3 lit unit render; `Image.get_data()` byte scan, not `get_pixel` |
| Full-scene histogram | palette drift under the real rig (#4) | downsampled capture, HSV binning, delta-E vs `@palettes` — in Python (numpy), not GDScript |

Plus existing metrics (draw calls, tris, frame p95, collision bodies —
asserted on the *imported* scene for `-colonly`, anim states via seek,
count checks) — still not sufficient to pass alone.

### A3 — Visual gate → `shots/` (non-negotiable)

Every shot reviewed by the **agent checklist** (named executor — see Vision
section), verdicts to `report.json`; zero unwaived flags to pass.

- **Golden set = stable subset.** Diff `wide_all`, `crew_lineup`,
  `walk_t0`, `low_light` against `golden/<goal>/` with the tolerance bands
  above; `ui_dialogue` is vision-reviewed but excluded from golden diff
  (font rasterization churns on engine bump). Re-bless on toolchain change.
- **Bug ledger:** new class → row with a runnable `check_id` or explicit
  waiver; first ask "visible on a component alone?" — yes → component-track
  check; no → A2.

---

## Stage 8 — Package → `dist/<goal>/`

```
dist/pirate_deck_scene/
  scene.tscn               # engine-built (PackedScene) — valid uids
  components/              # certified component folders, copied as units
  manifest.json            # goal brief + per-component provenance +
                           # input sha256s + toolchain + waivers + known issues
```

**Definition of done:** scene instantiates in a scratch Godot project
unedited (verify the drop-in flow once — uid refs resolve via path
fallback); every brief anim plays; perf within budget; each component
folder stands alone. Rebuilds are **verifiably equivalent** — input
sha256s + normalized content hash (strip `uid=` lines) — not byte-for-byte.

---

## Bug ledger → where each class dies

| Bug | Class | Cheapest fix | Gate |
|---|---|---|---|
| Chroma halo | component | BiRefNet (no green screen); despill fallback | C2 fringe ratio + C3 render fringe |
| Walk-through / projected overlap | composition | A1 spacing & depth | A2 screen-space overlap (calibrated) |
| Washed-out color | component | C1 palette-in-prompt + single ckpt | C3 unit-render histogram |
| Hidden hero art | composition | C1 gen-for-frame (≥768) / A1 framing | A1 analytic layer visibility |
| Light height | composition | A1 rig-anchored light | A2 lit coverage (per-shot floor) |

## Work backlog (ordered)

1. **CUDA torch for ComfyUI** — RTX 5060 Ti idle; ~20–50× gen speedup,
   inverts every budget above and makes batch curation trivial. Highest
   leverage single change.
2. **`tools/lint_tree.py`** — gate 0 validator: layout, manifest shas,
   status/folder consistency, `@` refs resolve, no loose files.
3. **C2 metrics** — fringe ratio, palette coverage, manifest writer.
4. **Unit-render harness** (`godot/` project, `unit_render.tscn`, job JSON,
   seek-based capture).
5. **A1 builder + A2 checks** — port patterns from `experiment/` scripts.
6. **Publish tool** — `processed/` + `.import` → `godot/assets/`.
7. Backlog: IP-Adapter style-lock; parallax outpaint for wide pans;
   `mobile`/`forward_plus` headless path; VLM executor for curation.

Check-accumulation loop:

```
visual gate finds bug ──> "visible on a component alone?"
  yes ──> add check at the component's earliest broken stage
  no  ──> add relational check in A2
```

Composition gates stay small by design — everything that can be killed
upstream, is.

---

## Hardening rules (run-2 learnings)

1. **New checks are born advisory.** A metric ships with
   `"gate_mode": "advisory"` in the manifest and is promoted to `enforced`
   only after its healthy range is measured on ≥1 real run. A miscalibrated
   gate is noise (`captain_lit_coverage` read 0.04 on art that looked fine).
2. **A check must prove it measured something.** Degenerate results (0,
   empty set, identical artifacts, unchanged metric) trigger a sanity flag,
   not a pass: parallax drift of exactly 0 meant the canvas transform hadn't
   updated; identical "depth" renders meant `material_override` silently
   no-oped in Eevee; a job polling forever meant it had already errored.
   Every gate emits *evidence* (numbers, hashes, file existence), not just
   pass/fail.
3. **The accepted file itself must pass vision.** "≥1 candidate passed" let
   a blind-accepted `walk_b` reach production unverified. Gate = every file
   under `accepted/` has its own unit render + vision pass.
4. **Hybrid silhouette fidelity.** For GLB-backed sprites, curate on alpha
   IoU between painted output and the depth render's alpha — catches both
   hallucinated extra objects and shape-drift (blocky legs → "columns with
   flames"). Brief may set `guide: depth|beauty`; `beauty` routes through
   img2img at ~0.5 denoise when depth produces too-literal geometry.
5. **Tool/environment paths live in `tools/env.json`** (blender, godot,
   comfyui_dir, comfyui_url, venv python) — same rule as `models.json`: a
   new environment is a registry entry, not a code change.
6. **ComfyUI lifecycle is a pipeline stage.** `run_goal` checks
   `/system_stats`, spawns the server if absent, waits for ready, and
   records server state in report provenance. Gen scripts never assume a
   running server.
7. **Prefer pip-packaged inference over vendored custom nodes.** A custom
   node is unversioned code — the ZHO BiRefNet node cost two sessions on its
   own bugs before `rembg`+official ONNX worked first try. Vendor nodes only
   when no packaged path exists.
8. **Publish→import→run is atomic.** `run_goal` issues them as one
   operation; the harness fails loudly (magenta stand-in + push_error) on
   any missing asset instead of rendering null textures.
9. **Report = provenance.** `report.json` embeds godot version, job-file
   sha, timestamp, and per-component manifest sha — that's what makes two
   runs diffable, the other half of the determinism rule.
