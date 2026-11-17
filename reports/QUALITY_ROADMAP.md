# Quality roadmap — Genshin-class gap evaluation

Evaluated 2026-11-13 against the best certified model (`xx_azure_sage_3d` rev5).

## Baseline evidence

| Dimension | Current | Genshin-class |
|---|---|---|
| Tris | 3,140 (41 conformed template parts) | ~25–40k, quad-dominant sculpt |
| Joints | 19 (spec declares 15 finger joints/hand — none bound) | ~100+ incl. fingers, face, hair/cloth secondary |
| Morphs | 0 | facial blendshapes + eye/brow drivers |
| Textures | 41 per-part baked albedos, no atlases | 2K atlases, albedo+lightmap+metalmat+face SDF |
| Materials | StandardMaterial3D PBR → chrome/plastic read | toon: banded diffuse, rim, inverted-hull outline |
| Anims | 22 procedural clips, events/sockets work | keyed polish + cloth sim + facial anim |
| Face | mannequin head | eye/iris planes, brow/lash cards, SDF face lightmap |

Verdict: workflow is production-grade; asset fidelity is prototype-grade.
Generation can reach "solid indie"; true parity needs artist meshes hosted
through the same gates.

## Batches (leverage order)

- [x] **1. Toon material stack** — `material: "toon"` on glb briefs → jobs →
  runner: TOON diffuse/specular + inverted-hull outline next_pass.
  Boundary: render-time only; export_scene .tscn keeps imported materials
  (sub-resource edits out of scope). **Done** — shipped on the three hero
  glbs; outline needed a vertex-grow ShaderMaterial (Godot 4 dropped
  `BaseMaterial3D.grow`, #75). Verified: banded skirt shading visible in
  pixel-diff vs pre-toon golden, crown/hair outline bands render. Honest
  limit confirmed: baked-in albedo specularity unchanged → motivates
  batch 4's bake split.
- [ ] **2. humanoid_v2 rig** — bind declared finger chains (30 bones),
  skirt panels, hair chains, jaw + eye bones. Old clips keep working
  (shared bone names); fingers default relaxed until clips add keys.
- [ ] **3. Real geometry** — spike: QuadriFlow retopo on existing hy3d
  sage sculpt (#60 notes 6x overshoot) → decision: tune / better
  retopologizer / denser conform template. Then weight-transfer +
  part-merge toward the 15k budget.
- [ ] **4. Texture/material maps** — extend conform bake: packed 2K
  atlas, AO/lightmap for the toon ramp, metallic mask (gems vs cloth).
- [ ] **5. Face** — template eye spheres + iris slot, brow/lash cards,
  mouth interior.
- [ ] **6. Multi-view ortho reference** — composite front/side/back
  guide → i2i ~0.3 (#34 route) → hy3d input. Optional; helps gen
  consistency more than final quality.
- [ ] **7. QA gates for new dims** — contract_check: skeleton-spec vs
  GLB skin joint diff (would have caught missing fingers at certify);
  silhouette coverage; texel density. Advisory-first per gate-discipline.

## Explicitly out of scope for generation

- Mocap/keyed animation polish — 22 procedural clips + events/sockets
  are honest gameplay substrate; flag fidelity in vision.json.
- Hair-card transparency work, costume sculpt detail, facial
  expressiveness — the last ~30% is artist work.

## Status log

- 2026-11-13 — evaluation recorded; batch 1 complete (hero glbs toon;
  goldens re-blessed for verified material change; #75 filed). Next:
  batch 3's retopo spike is a decision point — run it before batch 2
  depth, since its outcome shapes how much rig investment pays off.
