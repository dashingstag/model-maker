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
- [x] **2. humanoid_v2 rig** — `shared/skeletons/humanoid_v2.json`: v1
  superset (+30 finger, 4 skirt, 4 hair, jaw, 2 eyes = 60 joints).
  `blender_hero` emits chains + finger stubs on v2 briefs; gesture
  tables (`@poses/*.json` joints_deg) key into clips via
  `CLIP_GESTURES`; skirt/hair keys added to shared poses (inert on
  v1). **Done** — sage rev8 certified: skirt carries ~4.4k verts,
  hair.2 90, jaw 12; fingers present-but-unbound (fused mitten).
- [x] **3. Real geometry** — QuadriFlow confirmed no-op on the
  non-manifold shell cloud (985 islands; extends #60) → retopo
  rejected. Route shipped: `rig: "reskin"` chains conform→
  `blender_reskin` (nearest-conformed-part BVH transfer, top-2 id²
  blend, 0.06 m grab cap on detail bones). Painted mesh keeps its
  textures + silhouette; certified at 14,588 tris. Honest limit:
  blob deformation, fused hands, smeary face.
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
  goldens re-blessed for verified material change; #75 filed).

- 2026-11-13 — honest post-batch-1 evaluation: mechanism correct and
  reusable, but visible delta on the sage is small (~95% identical
  render). The asset's dominant signature is baked-in specular albedo +
  facet geometry, not lighting response — toon without a clean diffuse
  albedo ≈ noise. **Revised order: batch 3 spike → batch 4 bake split
  are prerequisites for batch 1's payoff.** Next: batch 3's retopo
  spike is a decision point — run it before batch 2 depth, since its
  outcome shapes how much rig investment pays off.

- 2026-11-14 — batches 2+3 landed (sage rev8). Reskin made batch 1's
  toon outline finally legible (bright painted albedo contrasts the
  hull). QuadriFlow route rejected; `rig:"reskin"` is the geometry
  path. v2 bones drive real verts (skirt ~4.4k). Remaining gap to
  target: bake split (4), face (5), deformation smoothness at
  extremes — the last is a mesh-topology property, not a rig one.

- 2026-11-18 — batches 4+5 landed (sage rev9). Batch 4 found the
  chrome source empirically: packed metallicRoughness mean roughness
  0.26 (hy3d paints cloth glossy); metallic already sane (0.7% hot
  px). pbr_fix.py floors non-metal roughness (0.55), preserves
  metal/gem response; blender_ao.py Cycles-bakes real AO into the
  atlas, injected as occlusionTexture (visible in Godot, invisible
  in EEVEE — verified via the harness). Batch 5 took the geometric
  route after texture-space failed (face = ~50x80 texels, scattered
  islands): blender_face.py adds bone-parented eye/brow/lip cards —
  flat n-gons (14.7k tris, under budget). Cards read in closeups;
  painted smear still dominates at distance — honest limit. Provider
  now exposes post:[face|pbr|ao] so future generated assets get the
  same finishing chain. Stray unskinned provider artifacts (a 2m
  hidden Icosphere riding inside the shell cloud) are stripped.
  Goldens re-blessed (drift 2-7% = material+cards, inspected).
