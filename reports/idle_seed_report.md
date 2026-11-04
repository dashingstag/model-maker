# Idle-seed generation report — xianxia_overworld character track

Status: **COMPLETE — awaiting human curation (review:human). Nothing written to `accepted/`.**
ComfyUI (127.0.0.1:8188, CUDA/RTX 5060 Ti) used as-is, not restarted. `tools/` untouched.

## Blocking defect found & worked around

- `python tools/gen_component.py <id> --goal xianxia_overworld --poses idle --seeds 4 --wait 120`
  first failed with:
  `FileNotFoundError: captain_3d: no export/<id>.glb`
  (gen_component.py:44 via render_depths:137 <- main:230).
  Cause: none of the three briefs declare `guide_from`; the default `captain_3d`
  had no component dir in `pipeline/components/` (only under `experiment/pirate/`).
- Remediation (data only, no tool patch): provisioned the documented default guide —
  `pipeline/components/captain_3d/brief.json` + `pipeline/components/captain_3d/export/pirate.glb`
  copied from `experiment/pirate/pipeline/components/captain_3d/`. Lint-clean
  (brief.json present, `export` is a legal stage dir, no `experiment/` refs).
  **Human should decide** whether the pirate-captain mesh is an acceptable depth
  guide long-term or whether a xianxia-proportioned guide component is wanted;
  also whether the three briefs should pin `guide_from` explicitly.

## Cross-cutting candidate defect

- **No candidate is "isolated on plain solid white background".** All 12 renders
  have dark painted scenic backgrounds (corner luminance 15-72, not ~255).
  `style.subject_bg` is appended at the *end* of the positive prompt
  (gen_component.py:245-246) and is swamped by the scene-like palette hints
  ("violet dusk sky", "teal waterfalls", "lilac mist"). Not fatal — extract-stage
  BiRefNet matting handles bg — but the spec deviation is uniform; log as a
  prompt-construction weakness.
- `index.json` provenance records `"device": "cpu"` (read from stale env.json
  `versions`); actual runtime is CUDA — cosmetic defect.

## xx_immortal_m — seeds 1000-1003 (4 generated, ~10-18 s each)

White/silver hanfu + jade; guide-depth figure fully in frame (bbox x143-368,
y89-560 → feet ~79px off bottom edge, headroom ~89px, no crop).

| Rank | Seed | Why |
|---|---|---|
| 1 | s1000 | Best palette match: white 23.3% + jade 15.3% (jade ornament reads); zero off-figure bright elements; centered single figure, feet clear of frame edge. Wide mid-flare = sleeves out — check for extra-limb look at curation. |
| 2 | s1002 | Clean frame, centered; white 21% + blue cast 20% (robes read silver-blue — acceptable "silver"). |
| 3 | s1001 | Clean slim figure but heavy jade/teal cast over whole robe (29%) — reads green, not white/silver. |
| 4 | s1003 | Whitest robe (25%) but off-figure bright patch top-left (~856 px secondary element) and lowest jade. |

Contact sheet: `reports/contact/xx_immortal_m_idle.png`

## xx_immortal_f — seeds 1000-1003

White+gold hanfu, golden updo, wide sleeves.

| Rank | Seed | Why |
|---|---|---|
| 1 | s1002 | Cleanest frame (0 off-figure elements); best combined white 25.3% + gold 13.6%; narrow centered updo column, symmetric wide sleeves, full body. |
| 2 | s1003 | Highest gold (15.2%) — hairpins likely read; bright patch directly above head (~740 px) is probably headdress glow — verify; lowest white (13.9%, darker read). |
| 3 | s1001 | Dramatically wide sleeves (fits must_have) but small off-figure bright blob upper-left (~448 px) and lower gold (7.8%). |
| 4 | s1000 | Strong palette (white 27%/gold 11%) BUT distinct bright structure upper-right separated from figure (~952 px) — highest "second figure" risk per must_not. |

Contact sheet: `reports/contact/xx_immortal_f_idle.png`

## xx_azure_sage — seeds 1000-1003

Indigo/silver robes, silver-white hair + dark crown, water-dragon wisps.

| Rank | Seed | Why |
|---|---|---|
| 1 | s1001 | Cleanest readable figure; indigo 30.8% + silver-white 14.5%; only bg element is an environmental crescent top-left (moon/water arc, not a figure); symmetric columnar stance, full body. |
| 2 | s1000 | Indigo 30% + best silver-white 16.5%; symmetric aura wisps flanking figure (prompt feature); large bright canopy arc overhead adds clutter. |
| 3 | s1003 | Coherent figure + flanking wisps + descending light beam; lowest white (6.4%) — darkest read. |
| 4 | s1002 | Highest indigo (44.1%) but busiest frame — ornate arch spans full width + heavy textured ground; figure least isolated, hardest to matte. |

Contact sheet: `reports/contact/xx_azure_sage_idle.png`

## Notes for the human curator

- All 12 candidates have painted scenic backgrounds — judge on figure quality;
  matting is downstream. "Extra limbs"/fine must_have details (jade ornament,
  hairpins, crown, blue-gem embroidery) are below ASCII-analysis resolution —
  verify on the contact sheets / raw PNGs.
- Tool also rendered depth/beauty/normal for ALL poses in each brief into
  `candidates/_render/` ( `--poses` filters only the SD loop) and left
  `candidates/_spec.json` + `candidates/_guide.glb` — expected tool artifacts.
- Helper script left at `reports/_gen_idle_contact.py` (delete after curation).
  Another track agent's `reports/contact/_make_sheets.py` also exists — not mine.
