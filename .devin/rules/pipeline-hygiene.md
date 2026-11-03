---
description: Folder ownership and evidence rules when creating, moving, or deleting files anywhere under pipeline/, godot/, shared/, briefs/, experiment/
trigger: model_decision
---

**Placement:**

- A component's identity is its folder — `pipeline/components/<id>/` with
  stage-owned subfolders (`candidates/`, `accepted/`, `processed/`,
  `unit_render/`). Nothing pipeline-produced lives loose in a flat dir;
  new ids take a domain prefix (`pirate_*`).
- Formal stages **never read `experiment/`** — and nothing in experiment/
  may be referenced by `briefs/`, `shared/`, `tools/`, or manifests.
- `godot/assets/` is a build artifact — publish regenerates it; never
  hand-edit or delete `.import` sidecars (they pin `uid://` refs).
- New vocab goes in `shared/<kind>/<name>.json` and is referenced via
  `@<kind>/<name>[.key]` — never copied into a brief or tool.

**Mutation:**

- `manifest.json` is the only mutable file per component — written
  atomically only (tmp + `os.replace`; use `tools/pipelib.py:atomic_json`).
- Stages write only their own subfolder, write-once per rev — retry by
  new rev + `history/rev<n>/` archive, never by deleting stage output.
- `candidates/` binaries are gitignored but `index.json` is checked in;
  `accepted/`/`processed/`/`unit_render/` are checked-in evidence — a
  human signed off on them.
