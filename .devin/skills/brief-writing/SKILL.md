---
name: brief-writing
description: Author or improve a goal brief (briefs/<goal>.brief.json) for the concept-art→Godot pipeline — schema, quality checklist, validation
argument-hint: "[brief path or goal name]"
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

Write or improve a goal brief for this repo's asset pipeline. The brief is
the single source of intent — quality comes from making it carry what the
gates currently guess.

## Process

1. **Read the contract first.** WORKFLOW.md "Stage 0" (brief schema +
   field semantics) is authoritative — check it before writing, the
   schema evolves. Read `shared/` to see which vocabularies exist
   (`styles/`, `palettes/`, `rigs/`, `poses/`, `skeletons/`, `actions/`),
   and read `briefs/pirate_deck_scene.brief.json` as the reference
   example.
2. **Decompose into components.** A goal is a scene; the work is per
   component. Each entry must be certifiable alone — if a bug could be
   seen on it isolated, its check lives in the component's fields, not
   `shot_expect`.
3. **Reference, never duplicate.** Styles, palettes, rigs, poses,
   skeletons, actions come from `shared/` via `@<kind>/<name>[.key.path]`
   — never inline copies. If a needed vocabulary file doesn't exist,
   create it under `shared/` rather than inlining.
4. **Validate.** Run `python tools/scaffold.py <brief>` — the gate checks
   types, every `@` ref (including dotted keypaths like
   `@palettes/dusk.colors.sea`), `shot_expect` keys, attachment/cast ids.
   Fix all errors before finishing. Scaffold is idempotent — rerunning
   after edits is the change log.

## Field cheat-sheet

Every field optional except `id`/`type`. Unknown fields pass through to
`brief.json`/`spec.json` untouched — the brief is the contract.

**Identity:** `id` (domain-prefixed: `pirate_captain`, not `captain`),
`type` (`sprite|sprite_variant|ui_image|parallax|glb`), `of`/`count`/`rev`.

**Prompt shaping:** `prompt_core` (subject only), `prompt_extra`
(angle/framing), `neg_extra` (component-specific exclusions — a parallax
drops "characters", a sprite drops "scenery"), `poses` (names or
`{name, prompt_extra}` objects).

**Dual-use checklists:** `must_have` — appended to the prompt AND the
curation checklist; `must_not` — degenerate modes (extra limbs, merged
objects). This is the highest-leverage pair: it turns art direction into
checkable data.

**Consistency:** `style_anchor` (family-match vs a component's accepted
art), `same_character_as` (same face/hat/props — portrait-match bugs).

**Guide quality (GLB-backed sprites):** `guide: depth|beauty`,
`silhouette_iou_min` (alpha-IoU floor vs the guide render at curation).

**Variants:** `method` (`palette`|region-masked, `controlnet`|same-depth
regen, `modulate`|runtime tint, `parts`); `vary` (regions that change);
`variants` — explicit per-member targets keyed by **palette name**
(`@palettes/<pal>.colors.<key>`), never raw hues.

**Rigged GLBs:** `skeleton: @skeletons/<name>` (bone-graph spec — shared
skeleton = shared retarget pool); `prop: true` (attachable, no unit pose
budget); `anims` as objects `{name, loop, duration, events, hand_pose,
check}` — `events` (`contact`, `grip`, `block`) become C3 capture points
AND action-shot sync anchors; `hand_pose: @poses/<name>` verifies finger
joints within `tolerance_deg`; `attachments` bind a prop to a `socket`
with `keep_during` clip lists.

**Composition:** `lighting_rig`, `layout` (rows y-coords, `spacing_px`,
`patrol`, `light_anchor`, `feet_pivot`), `shots` (names), `shot_expect`
(shot → metric floors — where A2 expectations live instead of magic
constants), `action_shots` (`of: @actions/<name>`, `cast` role→component,
`captures` clock-t seeks, `expect` relational asserts like
`props_attached`/`contact_within_m`).

**Budgets:** `seeds`, `review: human|auto` — spend curation effort where
failure is expensive.

**Computed by scaffold, not authored:** parallax `min_w_px` (viewport +
patrol×factor), `walk_t*` seek times (spacing_px/speed_px).

## Quality checklist (what "better" means)

- [ ] Every component could be certified alone — no field relies on
      scene context to be testable
- [ ] `must_have`/`must_not` on every generated component — gates get
      data, not vibes
- [ ] Variant colors are palette refs, not hues
- [ ] Consistency refs wherever two components depict the same thing
      (portrait↔sprite, crew↔base)
- [ ] `shot_expect` entries for every shot where failure is measurable
- [ ] Derived constraints used over magic numbers where derivable
- [ ] Component ids domain-prefixed for the shared library
- [ ] `seeds`/`review` scaled to failure cost
- [ ] No constraint on a certified component differs from its manifest
      (scaffold conflicts) — new requirements → new id or --recertify

## Anti-patterns

- Flat prompt strings carrying what fields exist for
- `@`-ref-like strings not matching `@kind/name[.key]` syntax
- Shots declared without expectations when the failure is measurable
- Editing a brief whose components are certified without bumping the
  file and re-scaffolding
- Declaring a skeleton/action/pose ref that doesn't exist in `shared/`
  — create the vocab file instead of inlining
