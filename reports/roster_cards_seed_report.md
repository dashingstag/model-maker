# Roster card seed report — goal `xianxia_roster`, style `xianxia_dark`

Generated: `python tools/gen_component.py <id> --goal xianxia_roster --seeds 4 --wait 120`
(seeds 5000–5003 per card, DreamShaper txt2img, 320x512, dpmpp_2m_sde/karras, 28 steps, cfg 7)

STOP for `review:human`. Nothing written to `accepted/`.
Contact sheets: `reports/contact/<id>.png` (2x2 grid, labelled, built by `reports/contact/_make_sheets.py`).

Global must_not check — no rendered titles/typography in any candidate; several have
baked-in corner ornaments / lattice frames / white margins (flagged per card below).

---

## xx_card_blade — swordsman, dao over shoulder, blood moon
must_have: sword silhouette over shoulder / blood moon / fur-lined dark robes
must_not: text, letters, border, frame, second figure, facing camera

| Rank | Seed | Notes |
|------|------|-------|
| 1 | s5003 | Profile, fur-lined collar, dark full-bleed bg, red moon + branches, sheathed blade at waist. Clean — no text/border. |
| 2 | s5002 | Profile, fur-lined cloak, blood moon + branches, dark bg. DEFECT: white ornamental corner stamp top-left (border/seal-adjacent). |
| 3 | s5001 | Profile, fur collar, red moon — but light-gray bg (violates dark backdrop), sword held low at side. |
| 4 | s5000 | Reads female, light bg, black disc (no blood moon), no fur — weakest. |

Systemic defect: no seed gets the dao rising OVER the shoulder — all carry it low/at side.

## xx_card_archivist — white-haired woman, tome, gourd, talismans
must_have: open tome / gourd vessel / white hair / floating talismans
must_not: text, letters, border, frame, second figure

| Rank | Seed | Notes |
|------|------|-------|
| 1 | s5001 | Open glowing tome in hands, white hair, crescent backdrop. Clean. Missing gourd + talismans. |
| 2 | s5003 | Holds white gourd vessel, white hair. Mild cloud-scroll corner ornaments; no tome/talismans. |
| 3 | s5000 | Ornamented vessel (gourd-ish), crescent moon — but white margins at corners (not full-bleed). No tome. |
| REJECT | s5002 | Open tome + flame, BUT baked-in gold lattice frame on all edges = `border`/`frame` violation. |

Systemic defect: no floating talismans in any seed; gourd only in s5003.

## xx_card_venom — tattooed man, glowing moth, spectral serpent
must_have: neck tattoos / glowing moth / spectral serpent above
must_not: text, letters, border, frame, second figure

| Rank | Seed | Notes |
|------|------|-------|
| 1 | s5001 | Glowing red moth on raised fingertip, forearm/hand tattoos, red serpentine smoke swirls. Clean. Female read. |
| 2 | s5003 | Clean dark profile, tattooed hand — but no moth, no serpent. Female read. |
| 3 | s5002 | Red spectral wisp with serpent-head shape + tattooed arms. DEFECT: gold ornamental corner pieces (border-adjacent). Female read. |
| REJECT | s5000 | Gold corner cartouches contain glyph-like symbols (letters-adjacent) + corner ornaments. |

Systemic defect: all four read female vs prompt "man"; no literal serpent coiling above.

## xx_card_mirror — woman before ornate mirror, spider lilies
must_have: ornate mirror / visible reflection / red spider lilies
must_not: text, letters, border, frame, third figure

| Rank | Seed | Notes |
|------|------|-------|
| 1 | s5000 | Tall arched ornate gold mirror frame, red spider lilies at right, profile, dark bg. Reflection dark/ambiguous. |
| 2 | s5002 | Clearest standing-mirror prop (arched, ornate frame), applying lip rouge — but no lilies, reflection unclear. |
| 3 | s5001 | Ornate gold arch (mirror-frame-like) + spider lily held — but no mirror surface, no reflection. |
| 4 | s5003 | Round patterned disc reads as decorative screen, not a mirror; flower dish not clearly spider lilies. |

Systemic defect: no seed shows a clear "reflection gazing back" (must_have).

## xx_card_monk — bald monk, prayer beads, runic halo
must_have: prayer pose / wooden beads / runic halo ring / bald head
must_not: text, letters, border, frame, hair

| Rank | Seed | Notes |
|------|------|-------|
| 1 | s5003 | Prayer pose, bald, glowing ring halo above head, thin bead cord on chest. Clean, full-bleed. |
| 2 | s5001 | Prayer pose, bald, concentric red ring halo behind head, glowing sigil between palms. Beads not clearly visible. |
| 3 | s5002 | Prayer pose, clearly visible wooden bead necklaces, red enso ring. DEFECT: white corner margins (not full-bleed). |
| REJECT | s5000 | Long black hair/veil draping down both sides = `hair` must_not violation. |

Systemic defect: halo is a plain/enso ring in every seed — no runic symbols.

## xx_card_planets — white-haired wanderer, nine orbiting spheres
must_have: multiple orbiting spheres / raised reaching arm / streaming white hair
must_not: text, letters, border, frame, second figure

| Rank | Seed | Notes |
|------|------|-------|
| 1 | s5001 | White orbital arcs + red moon sphere, arm extended outward, streaming hair, starry sky. |
| 2 | s5002 | Glowing red orb in palm + swirl ring; pale robes match "wind-torn pale robes". Small flower ornament top-left corner. |
| 3 | s5000 | Dramatic red/white enso energy ring, upward gaze — arm low, no distinct spheres. |
| 4 | s5003 | Single ember sphere at edge, arms down, least must_have coverage. |

Systemic defect: "nine ringed planets" never achieved — max 1–2 spheres; ring swirls stand in for orbits.

## xx_card_azure_sage — silver-white sage, water orb, water-dragon aura
must_have: water-dragon aura / silver-white hair / indigo layered robes / glowing water orb
must_not: text, letters, border, frame, second figure

| Rank | Seed | Notes |
|------|------|-------|
| 1 | s5000 | Scaled white dragon coiling behind, glowing orb over raised palm, teal-indigo embroidered robes, rocky cliff ledge. All 4 must_have hit. Clean. |
| 2 | s5001 | Water-dragon swirl arcing over figure, orb held in both hands, indigo layered robes. Clean. |
| 3 | s5002 | Water aura + glowing orb + ornate robes — DEFECT: geometric lattice corners top edge = border/frame violation. |
| 4 | s5003 | No dragon aura, tiny orb, female-leaning read; floating-pagoda cliff bg is the only bonus. |

Strongest batch overall — s5000/s5001 both close to brief.

---

## Reject summary (hard must_not violations)
- xx_card_archivist s5002 — baked-in lattice frame.
- xx_card_venom s5000 — glyph-like symbols in corner cartouches.
- xx_card_monk s5000 — hair (must_not).
- Border-adjacent flags (human call): blade s5002, venom s5002, archivist s5003, azure_sage s5002 (lattice), monk s5002 + archivist s5000 (white margins, not full-bleed).

## Suggested regen tweaks if a second pass is wanted
- blade: add "sheathed dao slung diagonally across back, pommel visible above shoulder".
- venom: add "man, masculine" emphasis + "serpent coiling overhead"; drop ornament tokens.
- mirror: "her face reflected inside the mirror" to force visible reflection.
- planets: "nine small ringed planets" with count emphasis.
- monk: "ring of glowing rune glyphs" to get runes rather than a plain ring.
