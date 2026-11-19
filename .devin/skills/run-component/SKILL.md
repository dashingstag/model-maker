---
name: run-component
description: Drive one component through the C-track — generate → curate → extract → unit render → certify — with gate evidence and failure routing
argument-hint: "<component_id> [--goal <goal>] [--seeds N]"
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

Take one `pipeline/components/<id>/` through the component track to
`certified`. Manifest status progression: `wip → generating → curated →
processed → certified`; `stale`/`needs_human` are the failure exits.
WORKFLOW.md sections C1–C3 + "Vision, human gates, and waivers" are the
contract — read them when behavior matters.

## Stage commands

```bash
# C1 generate — ComfyUI must be up (curl http://127.0.0.1:8188/system_stats)
python tools/gen_component.py <id> [--seeds N] [--goal <goal>] [--wait 60]

# curate — human contact-sheet pick or agent checklist; winner(s) copied
# to accepted/ (sprite: one per pose, named <pose>.png; ui/parallax:
# src.png) + sidecar gen.json; rejected seeds stay logged in
# candidates/index.json

# C2 extract — uses the rembg venv python, NOT system python
<comfyui_python from tools/env.json> tools/extract.py <id> [--goal <goal>] [--wait 60]

# C3 unit render — publish then run the harness (windowed, unminimized —
# gl_compatibility cannot render headless on Windows)
python tools/publish.py <goal> --wait 60
<godot exe from tools/env.json> --path godot -- <abs path to jobs.json>
```

## Per-type notes

- `sprite_variant` — route by `method`: `controlnet` generates via
  `tools/gen_variant.py <id> --goal <g>` (i2i repaint per variant×pose,
  needs base `accepted/` first; denoise per variant/component — 0.45
  preserves too much, 0.7 repaints colorways); `parts`/`palette` are
  transform-only — skip C1, go straight to extract once the `of` base is
  `processed`. Locks its base automatically. Accepted files:
  `accepted/<variant>_<pose>.png` (sprite bases), `accepted/<variant>.png`
  (ui bases). Extract binds `manifest.base_art` = sha of every base file
  derived from — `lint_tree` fails certified variants whose base has
  since rev-bumped; re-derive + re-extract (#73). Extract also requires
  variant art for *every* pose in the base manifest — new base poses
  force a variant regen round (`--poses <new>` + curate).
- `sprite` — depth guide is opt-in via `guide_from` (locks the guide);
  without it, poses run guideless i2i from `accepted/idle.png`. Warning:
  guideless i2i at 0.55–0.62 preserves the composition skeleton — poses
  change weakly and baked-in props do not materialize (BUG#13).
- `sprite` + `prop: true` — object-only prompts (no wielder); pose list
  may be omitted → single `idle` pose.
- `ui_image`/`parallax` — plain txt2img at `w_px`×`h_px` when authored;
  accepted file must be `src.png`. Opt-in `init_from`+`denoise` runs i2i
  from `accepted/<init_from>.png` — the composite-guide route for elements
  the model can't produce on its own (e.g. exact counts: draw nine orbs in
  a ring → denoise 0.26, verified 9/9 clusters in #34). Denoise floor ~0.25
  melts flat guide art into painterly style while preserving count/layout.
- `glb` — C1 is the blender builder → `build/` + `export/`; extract
  validates tris vs `tri_budget` and lists animations. Brief
  `material: "toon"` gives the member banded toon shading + inverted-hull
  outline in unit renders and compositions (render-time; props attached
  via attach3d inherit the member's mode; doesn't affect baked-in
  specularity — that's the albedo bake's job). `provider.options.post`
  runs ordered finishing steps: `face` (bone-parented feature cards),
  `pbr` (roughness floor), `ao` (baked occlusion injection), `design`
  (position-keyed atlas repaint — cape/trim/hood/mask + stray-texel
  cleanup, `tools/design_pass.py`, xianxia-indigo palette).
- `glb` certification requires **multi-angle evidence** (#85): a
  front-only golden passed a model whose rear cape was featureless
  and whose face cards never rendered. Before recording vision.json,
  review the turntable back/side shots plus a face closeup — record
  residual artifacts in `flags`, don't certify them silently.

## Gates (don't skip — evidence, not vibes)

- C1 out: `candidates/` populated; `index.json` has every seed's
  provenance. Degenerate/hallucinated candidates stay logged, not
  deleted.
- C2 out: `manifest.json` written atomically with per-type gate fields —
  sprite `fringe_px`/`gate.fringe_ok`, glb `tris`/`gate.tris_ok`,
  variant `variants` + `of`. Check `gate.*` values, not just existence.
- C3 out: `unit_render/` shots + `vision.json` (checklist verdicts, actor,
  ts, flags). **Every file under `accepted/` must pass vision** — a blind
  accept once shipped an unverified walk_b.
- Certify: set `manifest.status: "certified"` (atomic write via
  `tools/pipelib.py:atomic_json`) only after vision passes.

## Failure routing

- A failed check loops to the **earliest broken stage** — don't re-run
  publish for a bad matte; re-run extract.
- Locks: `--wait N` polls; a `LockHeld` exit means another run owns the
  component — report the owner, don't force.
- After 2 failed regen rounds → `manifest.status: "needs_human"` with the
  blocking reason in `waiver`/`history`, and say so plainly.
- Never `rmtree` a stage folder to retry — write-once per rev; the
  validator archives to `history/rev<n>/`.
