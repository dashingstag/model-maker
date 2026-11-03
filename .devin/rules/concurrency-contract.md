---
description: Locking and atomic-write contract when editing tools/*.py, godot/scripts/, or any code touching pipeline components, composition dirs, or godot/assets
trigger: model_decision
---

The pipeline runs 2–3 workflows concurrently. Any code touching shared
resources must honor the contract (implemented in `tools/pipelib.py`):

- **Locks:** `<dir>.lock` via `FileLock` — mkdir-atomic, `owner.json`
  {owner, pid, ts}, stale-swept on dead pid / 2 h age. Stage tools lock
  their component plus dependency bases (`captain_3d` for sprites, `of`
  for variants) — **always acquired sorted by id**, released in reverse.
- **Publish ordering:** `composition/<goal>.lock` *then*
  `godot/.publish.lock` — the only multi-lock site; that ordering must
  not be violated by new callers.
- **Every JSON write is atomic** — `atomic_json()` (tmp + `os.replace`),
  no bare `json.dump(open(path, "w"))` on shared files
  (`manifest.json`, `spec.json`, `jobs.json`, `brief.json`,
  `candidates/index.json`).
- **Directory publication** swaps via sibling `.new`/`.old` renames —
  readers may see a μs gap, never a torn tree. No `rmtree`+`copytree`
  on published paths.
- **Ownership:** durable claim = `brief.json`'s `goal` field; `--goal`
  asserts it, `--wait N` polls, `LockHeld` means report-and-stop —
  never force-release someone else's lock.
- **ComfyUI** serializes generation (one server, one queue): never kill
  a server you didn't spawn, never assume it's up — health-check
  `/system_stats` first.
