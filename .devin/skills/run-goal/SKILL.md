---
name: run-goal
description: Run a goal brief end-to-end — scaffold, component tracks, publish, Godot harness, report triage — honoring the concurrency contract
argument-hint: "briefs/<goal>.brief.json"
allowed-tools:
  - read
  - grep
  - glob
  - edit
  - exec
triggers:
  - user
  - model
---

Orchestrate a full goal run. Sequence:

## 1. Preflight

```bash
curl http://127.0.0.1:8188/system_stats   # ComfyUI up? spawn if absent
python tools/scaffold.py <brief>          # gate + create/reuse components
```

- Scaffold exits 1 on conflicts/held components — read each line: a
  `conflict:` means requested constraints ≠ certified (new id or
  --recertify); `held:` means another goal owns it — wait and retry,
  don't force.
- `reused(certified)` components cost nothing. Only `created` ones need
  the track.
- Check `pipeline/composition/<goal>/spec.json` — it holds the resolved
  rig/layout/shots snapshot; edits to `shared/` after scaffolding do NOT
  reach the in-flight run (by design — re-scaffold to pick them up).
  Same for composition edits in the goal brief: re-run scaffold or
  publish won't see them (publish warns on brief>spec mtime).

## 2. Component tracks

For each uncertified component, run the C-track (see /run-component —
it has the per-type details). Concurrency contract in practice:

- **Parallel-safe:** distinct components' C-stages across separate runs —
  each locks its own folder; multi-component tools acquire in sorted
  order (deadlock-free).
- **Serialized:** one ComfyUI server = one queue — 2–3 parallel runs
  overlap non-generation work, they do NOT multiply gen throughput.
  `--wait 60` on every stage invocation when running concurrently.
- **Never kill a ComfyUI you didn't spawn** — another run may share it.
- Variant components (`of:`) wait for their base to have `accepted/` art,
  then run `tools/gen_variant.py` (controlnet) or extract directly
  (parts/palette). `deploy: "swap"` variants join the library, not the
  scene — they don't appear as composition members.

## 3. Publish + harness

```bash
python tools/publish.py <goal> --wait 60
<godot exe from tools/env.json> --path godot -- <abs jobs.json>
```

- Publish resolves `composition.layout` → explicit `members` in jobs.json
  (rows/x per `<id>_row`/`<id>_x`, `spacing_px`, `patroller`, `walk`,
  card `grid`, per-layer `y_off`). **Author a layout** — defaults space
  sprites ~170px apart at y=648, which overlaps wide sprites and floats
  them above mid-canvas floors.
- Publish holds `composition/<goal>.lock` then `godot/.publish.lock`,
  copies `processed/` atomically, then runs `godot --import` inside the
  lock — without it every texture reports MISSING on the next run.
- Harness runs **windowed, unminimized** (gl_compatibility can't render
  headless on Windows); job path goes after `--`.
- Wide/vista shots frame the full 2× canvas (zoom 0.5 at canvas center);
  a 1280×720 default camera sees only each layer's sky quadrant.
- `patrol` ranges must leave sprite-width clearance from stationary
  members (~`h_px` × aspect ≈ 300px for 384px-tall sprites) — the
  overlap check counts rect penetration per patrol step.
- `layout.attach` sockets certified prop components onto host sprites:
  `{prop, to, offset, h_px}` — offsets are from the host's feet pivot;
  props ride the patroller and keep separate provenance.
- Card grids: `grid.center: true` centers each row within the declared
  grid width (including the short last row); author card sizes for the
  2× composition canvas (2560×1440), not the 1280×720 capture.
- Parallax is manual: layers are plain sprites offset by `-cam_delta ×
  factor`, clamped so each 2560px layer always covers the view —
  `ParallaxBackground` scroll tracking does not run in this harness.
- Multi-actor `action_shots` (`of: <action>`): all cast roles share one
  3D stage placed per the action spec's `spacing_m`, alternating facing;
  the latest timeline entry with `start <= capture t` owns each actor's
  clip. `props` maps role → cid or `{cid, socket, rot, aim}`: `rot` is a
  grip euler applied to the prop node (a BoneAttachment3D's own
  transform is bone-synced every frame — never offset the attachment
  itself); `aim` re-points the prop's +Y at a shared world contact point
  after each seek — use it for blade binds instead of guessing bone-local
  eulers. `contact_within_m` measures grip→`blade_tip` segment distance;
  `no_ground_clip` checks lowest bone/prop-AABB y ≥ -0.02. Prop glbs
  need `blade_mid`/`blade_tip` named empties for contact checks.
- Outputs: `pipeline/composition/<goal>/shots/` + `report.json`.
- Scene export: `python tools/export_scene.py <goal>` writes
  `dist/<goal>/scene.tscn` — a static composition (layers, members,
  attached props, rig light, glb SubViewport composites) referencing
  `res://assets/components/`. Validate with
  `godot --path godot -s scripts/scene_probe.gd -- <abs scene.tscn> [out.png]`
  — reports the instantiated tree and optionally snaps a frame.

## 4. Triage report.json — component or composition?

Read `report.json` + the shots. For every flag, ask the workflow's core
question: *visible on the component alone?*

- **Yes** → component bug: loop that component to its earliest broken
  stage (see /run-component failure routing; see /bug-triage to file it).
- **No** → relational: A2 flags live in the shot metrics
  (`same_row_overlap_events`, `lit_coverage`, `sky_visible_pct`) —
  compare against `shot_expect` in spec.json/jobs.json.
- **Flag-not-fail / advisory metrics** (`gate_mode: advisory`) are
  calibration data — note the reading, don't chase it.
- Degenerate evidence (metric exactly 0, identical artifacts, empty sets)
  = the check itself is broken — flag the check, not the art.

## 5. Certify the goal

All components `certified` + report clean (zero unwaived flags) → goal
is done for this rev. Any `needs_human` component blocks the goal; report
it, don't waive silently — waivers are explicit fields, not omissions.
