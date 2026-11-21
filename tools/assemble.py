# assemble.py — merge certified part components into one character GLB
# on the shared humanoid skeleton.
#
#   python tools/assemble.py <char_id>
#
# The character's brief.json carries:
#   "assemble": {
#     "base": "@mannequin/humanoid_base",
#     "parts": {"body_torso": "body_torso", "cloth_torso": "cloth_torso", ...}
#   }
#
# Gate: every part id must resolve to a CERTIFIED component — uncertified
# parts abort assembly. Parts are grafted by matching node names: each
# part's mesh nodes re-attach under the base bone of the same name, so
# parts only assemble onto the skeleton they were built against.
#
# Coverage: cloth parts declare `covers` in their part block. v0 retains
# covered skin (the research: retain-the-body is the safe default —
# skin inside cloth can't poke out); a later rev can cull it.
#
# Writes pipeline/components/<char_id>/export/<char_id>.glb +
# export/assemble.json provenance, then the char runs the normal
# glb C-track: extract → contract → unit render → certify.

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from face_build import _read_glb, _write_glb  # noqa: E402
from pipelib import atomic_json  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
COMP = os.path.join(ROOT, "pipeline", "components")


def _ref(ref):
    kind, rest = ref[1:].split("/", 1)
    return json.load(open(os.path.join(ROOT, "shared", kind,
                                       rest + ".json")))


def _status(cid):
    mp = os.path.join(COMP, cid, "manifest.json")
    return json.load(open(mp)).get("status") if os.path.exists(mp) else None


class Merger:
    """Appends part-GLB mesh data into the base GLB."""

    def __init__(self, g, blob):
        self.g = g
        self.blob = bytearray(blob)

    def _push_acc(self, pg, pblob, acc_i):
        a = dict(pg["accessors"][acc_i])
        bv = pg["bufferViews"][a["bufferView"]]
        data = pblob[bv.get("byteOffset", 0):
                     bv.get("byteOffset", 0) + bv["byteLength"]]
        off = (len(self.blob) + 3) & ~3
        self.blob += b"\0" * (off - len(self.blob)) + data
        self.g["bufferViews"].append({"buffer": 0, "byteOffset": off,
                                      "byteLength": bv["byteLength"]})
        a["bufferView"] = len(self.g["bufferViews"]) - 1
        a.pop("byteOffset", None)
        self.g["accessors"].append(a)
        return len(self.g["accessors"]) - 1

    def _material(self, pg, mat_i, matmap):
        name = pg["materials"][mat_i].get("name")
        if name in matmap:
            return matmap[name]
        self.g["materials"].append(
            json.loads(json.dumps(pg["materials"][mat_i])))
        matmap[name] = len(self.g["materials"]) - 1
        return matmap[name]

    def graft(self, pg, pblob, name2idx, matmap):
        """Append every mesh-bearing node of pg, re-parented under the
        same-named bone in self.g. Returns list of mesh-node names."""
        par = {}
        for i, n in enumerate(pg["nodes"]):
            for c in n.get("children", []):
                par[c] = i
        out = []
        for ni, n in enumerate(pg["nodes"]):
            if "mesh" not in n:
                continue
            pname = pg["nodes"][par[ni]].get("name") if ni in par else None
            if pname not in name2idx:
                raise SystemExit(
                    f"no base bone '{pname}' for mesh node "
                    f"'{n.get('name')}' — part built for a different "
                    "skeleton")
            sm = pg["meshes"][n["mesh"]]
            nprims = []
            for p in sm["primitives"]:
                np_ = {"mode": p.get("mode", 4), "attributes": {}}
                for att, ai in p["attributes"].items():
                    np_["attributes"][att] = self._push_acc(pg, pblob, ai)
                if "indices" in p:
                    np_["indices"] = self._push_acc(pg, pblob, p["indices"])
                if "material" in p:
                    np_["material"] = self._material(pg, p["material"],
                                                     matmap)
                nprims.append(np_)
            self.g["meshes"].append({"name": sm.get("name"),
                                     "primitives": nprims})
            nn = {"name": n.get("name"), "mesh": len(self.g["meshes"]) - 1}
            for k in ("translation", "rotation", "scale"):
                if k in n:
                    nn[k] = n[k]
            self.g["nodes"].append(nn)
            self.g["nodes"][name2idx[pname]].setdefault(
                "children", []).append(len(self.g["nodes"]) - 1)
            out.append(n.get("name"))
        return out


def main(char_id):
    cdir = os.path.join(COMP, char_id)
    brief = json.load(open(os.path.join(cdir, "brief.json")))
    spec = brief.get("assemble")
    if not spec:
        raise SystemExit(f"{char_id}: no assemble block in brief.json")
    base = _ref(spec["base"])
    g, blob = _read_glb(os.path.join(ROOT, base["glb"]))

    for n in g["nodes"]:
        n.pop("mesh", None)
    g["meshes"] = []
    name2idx = {n.get("name"): i for i, n in enumerate(g["nodes"])}
    matmap = {m.get("name"): i for i, m in
              enumerate(g.get("materials", []))}
    mg = Merger(g, blob)

    total, used = 0, []
    for slot, pid in sorted(spec["parts"].items()):
        if _status(pid) != "certified":
            raise SystemExit(f"{slot}: part '{pid}' not certified — "
                             "assemble accepts certified parts only")
        pexp = os.path.join(COMP, pid, "export", pid + ".glb")
        pg, pblob = _read_glb(pexp)
        before = len(g["meshes"])
        names = mg.graft(pg, pblob, name2idx, matmap)
        tris = sum(g["accessors"][p["indices"]]["count"] // 3
                   for m in g["meshes"][before:] for p in m["primitives"]
                   if "indices" in p)
        total += tris
        pbrief = json.load(open(os.path.join(COMP, pid, "brief.json")))
        used.append({"slot": slot, "id": pid, "meshes": names,
                     "covers": pbrief.get("part", {}).get("covers", []),
                     "tris": tris})
        print(f"  {slot}: {pid} -> {len(names)} meshes, {tris} tris")

    out = os.path.join(cdir, "export", char_id + ".glb")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    g["buffers"][0]["byteLength"] = len(mg.blob)
    _write_glb(g, bytes(mg.blob), out)
    atomic_json(os.path.join(cdir, "export", "assemble.json"),
                {"base": spec["base"], "parts": used, "tris": total})
    print(f"{char_id}: {len(used)} parts, {total} tris -> {out}")


if __name__ == "__main__":
    main(sys.argv[1])
