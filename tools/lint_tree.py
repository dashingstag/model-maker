"""Gate 0 validator — audits the repo against WORKFLOW.md folder rules.

  python tools/lint_tree.py [--strict]

Errors (exit 1): loose files, unknown stage folders, bad manifest status,
certified without vision/gates/intact artifacts, unresolvable @refs, formal
files referencing experiment/, brief components missing from the library.
Warnings: stale locks, published assets without a component, legacy
manifest schema. --strict turns warnings into errors.
"""
import hashlib, json, os, re, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
from pipelib import _read_owner, _pid_alive  # noqa: E402

COMP = os.path.join(ROOT, "pipeline", "components")
STAGE_DIRS = {"candidates", "accepted", "processed", "unit_render", "history",
              "build", "export", "sanity"}
STAGE_FILES = {"brief.json", "manifest.json"}
STATUSES = {"wip", "generating", "curated", "processed", "certified", "stale",
            "needs_human"}
REF_RE = re.compile(r'"(@[a-z_]+/[A-Za-z0-9_.\-]+)"')
errors, warnings = [], []

def err(m): errors.append(m)
def warn(m): warnings.append(m)

def sha(p):
    return "sha256:" + hashlib.sha256(open(p, "rb").read()).hexdigest()

def check_ref(ref, where):
    kind, rest = ref[1:].split("/", 1)
    fname, _, keypath = rest.partition(".")
    p = os.path.join(ROOT, "shared", kind, fname + ".json")
    if not os.path.exists(p):
        err(f"{where}: {ref} -> shared/{kind}/{fname}.json missing"); return
    data = json.load(open(p))
    for k in filter(None, keypath.split(".")):
        if not isinstance(data, dict) or k not in data:
            err(f"{where}: {ref} -> key '{k}' missing"); return
        data = data[k]

def lint_components():
    for name in sorted(os.listdir(COMP)):
        p = os.path.join(COMP, name)
        if name.endswith(".lock") and os.path.isdir(p):
            info = _read_owner(p)
            if info.get("pid") and not _pid_alive(info["pid"]):
                warn(f"stale lock {name} (owner {info.get('owner')}, pid dead)")
            continue
        if not os.path.isdir(p):
            err(f"loose file in pipeline/components: {name}"); continue
        for e in os.listdir(p):
            ep = os.path.join(p, e)
            if os.path.isdir(ep) and e not in STAGE_DIRS:
                err(f"{name}: unknown stage folder '{e}'")
            elif os.path.isfile(ep) and e not in STAGE_FILES:
                err(f"{name}: loose file '{e}'")
        if not os.path.exists(os.path.join(p, "brief.json")):
            err(f"{name}: no brief.json")
        mp = os.path.join(p, "manifest.json")
        if not os.path.exists(mp):
            continue
        m = json.load(open(mp))
        st = m.get("status")
        if st not in STATUSES:
            err(f"{name}: manifest status '{st}' not in {sorted(STATUSES)}")
        if "schema_v" not in m:
            warn(f"{name}: legacy manifest (no schema_v/inputs/artifacts)")
        if st == "certified":
            vis = os.path.join(p, "unit_render", "vision.json")
            if not os.path.exists(vis):
                err(f"{name}: certified without unit_render/vision.json")
            else:
                v = json.load(open(vis))
                if v.get("verdict") != "pass" and not m.get("waiver"):
                    err(f"{name}: certified but vision verdict '{v.get('verdict')}'")
            for g, ok in m.get("gate", {}).items():
                if ok is False and not m.get("waiver"):
                    err(f"{name}: certified with failing gate {g}")
        for rel, h in m.get("artifacts", {}).items():
            ap = os.path.join(p, rel)
            if not os.path.exists(ap):
                err(f"{name}: artifact missing {rel}")
            elif sha(ap) != h:
                err(f"{name}: artifact changed since manifest (stale) {rel}")

def lint_briefs():
    for f in sorted(os.listdir(os.path.join(ROOT, "briefs"))):
        if not f.endswith(".brief.json"):
            err(f"briefs/: unexpected file {f}"); continue
        txt = open(os.path.join(ROOT, "briefs", f)).read()
        brief = json.loads(txt)
        for ref in REF_RE.findall(txt):
            check_ref(ref, f)
        goal = brief["goal"]
        spec_p = os.path.join(ROOT, "pipeline", "composition", goal, "spec.json")
        ids = [c["id"] for c in brief["components"]]
        for cid in ids:
            if not os.path.isdir(os.path.join(COMP, cid)):
                err(f"{f}: component '{cid}' not in library — run scaffold")
        if os.path.exists(spec_p) and json.load(open(spec_p)).get("components") != ids:
            warn(f"{f}: spec.json components differ from brief — re-scaffold")

def lint_experiment_refs():
    for top in ("briefs", "shared", "tools", "pipeline", "godot/scripts"):
        for dp, dirs, files in os.walk(os.path.join(ROOT, top)):
            dirs[:] = [d for d in dirs if d not in ("candidates", "history", "tests",
                                                    "__pycache__", ".godot")]
            for fn in files:
                if fn.endswith((".json", ".py", ".gd")) and fn != "lint_tree.py":
                    txt = open(os.path.join(dp, fn), errors="ignore").read()
                    if re.search(r"experiment[/\\]", txt):
                        err(f"formal file references experiment/: "
                            f"{os.path.relpath(os.path.join(dp, fn), ROOT)}")

def lint_godot():
    adir = os.path.join(ROOT, "godot", "assets", "components")
    if not os.path.isdir(adir):
        return
    for name in os.listdir(adir):
        if os.path.isdir(os.path.join(adir, name)) and not os.path.isdir(os.path.join(COMP, name)):
            warn(f"godot/assets/components/{name} has no library component")

if __name__ == "__main__":
    lint_components(); lint_briefs(); lint_experiment_refs(); lint_godot()
    for w in warnings: print("WARN ", w)
    for e in errors: print("ERROR", e)
    strict = "--strict" in sys.argv
    bad = errors or (strict and warnings)
    print(f"lint_tree: {len(errors)} error(s), {len(warnings)} warning(s)"
          + (" — FAIL" if bad else " — OK"))
    sys.exit(1 if bad else 0)
