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
        base_name = name.split(".")[0] if name else name
        if base_name in matmap:
            return matmap[base_name]
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


class SkinnedMerger:
    """Merges skinned part GLBs onto the base skeleton.

    Every part GLB carries the full 60-joint skin (same armature exported
    per part). The merged GLB gets ONE skin: joints remapped to the base
    GLB's bone nodes by name, inverseBindMatrices copied verbatim from the
    first part (identical rest pose). Each part's skinned mesh is appended;
    its JOINTS_0 indices are remapped into the shared joint order when the
    part's skin ordering differs.
    """

    def __init__(self, g, blob):
        self.g = g
        self.blob = bytearray(blob)
        self.joints = None      # shared skin joints -> base node idx
        self.jname2slot = {}    # bone name -> slot in shared joint list
        self.skin_i = None

    _comp_size = {5120: 1, 5121: 1, 5122: 2, 5123: 2, 5125: 4, 5126: 4}

    def _acc_data(self, pg, pblob, acc_i):
        a = pg["accessors"][acc_i]
        bv = pg["bufferViews"][a["bufferView"]]
        ncomp = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4,
                 "MAT4": 16}[a["type"]]
        return (a, pblob[bv.get("byteOffset", 0) + a.get("byteOffset", 0):
                         bv.get("byteOffset", 0) + a.get("byteOffset", 0)
                         + bv["byteLength"]], ncomp)

    def _push_bytes(self, data):
        off = (len(self.blob) + 3) & ~3
        self.blob += b"\0" * (off - len(self.blob)) + data
        self.g["bufferViews"].append({"buffer": 0, "byteOffset": off,
                                      "byteLength": len(data)})
        return len(self.g["bufferViews"]) - 1

    def _push_acc(self, pg, pblob, acc_i):
        a, data, ncomp = self._acc_data(pg, pblob, acc_i)
        bv_i = self._push_bytes(data)
        na = dict(a)
        na["bufferView"] = bv_i
        na.pop("byteOffset", None)
        self.g["accessors"].append(na)
        return len(self.g["accessors"]) - 1

    def init_skin(self, pg, pblob, name2idx):
        """Build the shared skin from this part's skin."""
        sk = pg["skins"][0]
        self.joints = []
        for ji, node_i in enumerate(sk["joints"]):
            name = pg["nodes"][node_i].get("name")
            if name not in name2idx:
                raise SystemExit(f"skin joint '{name}' not in base skeleton")
            self.joints.append(name2idx[name])
            self.jname2slot[name] = ji
        ibm = self._push_acc(pg, pblob, sk["inverseBindMatrices"])
        self.g.setdefault("skins", []).append(
            {"joints": self.joints, "inverseBindMatrices": ibm,
             "name": "humanoid_v2"})
        self.skin_i = len(self.g["skins"]) - 1

    def graft(self, pg, pblob, name2idx, matmap, mesh_acc_cb):
        sk = pg["skins"][0]
        part_names = [pg["nodes"][j].get("name") for j in sk["joints"]]
        remap = {i: self.jname2slot[n] for i, n in enumerate(part_names)
                 if n in self.jname2slot}
        out = []
        for ni, n in enumerate(pg["nodes"]):
            if "mesh" not in n or "skin" not in n:
                continue
            sm = pg["meshes"][n["mesh"]]
            nprims = []
            for p in sm["primitives"]:
                np_ = {"mode": p.get("mode", 4), "attributes": {}}
                for att, ai in p["attributes"].items():
                    if att == "JOINTS_0":
                        np_["attributes"][att] = self._remap_joints(
                            pg, pblob, ai, remap)
                    else:
                        np_["attributes"][att] = self._push_acc(pg, pblob, ai)
                if "indices" in p:
                    np_["indices"] = self._push_acc(pg, pblob, p["indices"])
                if "material" in p:
                    np_["material"] = mesh_acc_cb(pg, p["material"], matmap)
                nprims.append(np_)
            self.g["meshes"].append({"name": sm.get("name"),
                                     "primitives": nprims})
            nn = {"name": n.get("name"),
                  "mesh": len(self.g["meshes"]) - 1,
                  "skin": self.skin_i}
            self.g["nodes"].append(nn)
            self.g["scenes"][self.g["scene"]]["nodes"].append(
                len(self.g["nodes"]) - 1)
            out.append(n.get("name"))
        return out

    def _remap_joints(self, pg, pblob, acc_i, remap):
        import struct
        a = pg["accessors"][acc_i]
        bv = pg["bufferViews"][a["bufferView"]]
        ct = a["componentType"]
        off = bv.get("byteOffset", 0) + a.get("byteOffset", 0)
        n = a["count"] * 4
        fmt = {5121: "B", 5123: "H"}[ct]
        idx = struct.unpack_from(f"<{n}{fmt}", pblob, off)
        idx = bytes(bytearray(
            struct.pack(f"<{n}{fmt}", *[remap.get(i, i) for i in idx])))
        bv_i = self._push_bytes(idx)
        na = dict(a)
        na["bufferView"] = bv_i
        na.pop("byteOffset", None)
        self.g["accessors"].append(na)
        return len(self.g["accessors"]) - 1


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
    rigid = Merger(g, blob)
    skinned = SkinnedMerger(g, blob)
    skinned.blob = rigid.blob  # share one binary buffer
    _mat = rigid._material

    total, used = 0, []
    for slot, pid in sorted(spec["parts"].items()):
        if _status(pid) != "certified":
            raise SystemExit(f"{slot}: part '{pid}' not certified — "
                             "assemble accepts certified parts only")
        pexp = os.path.join(COMP, pid, "export", pid + ".glb")
        pg, pblob = _read_glb(pexp)
        is_skinned = any("skin" in n for n in pg["nodes"] if "mesh" in n)
        before = len(g["meshes"])
        if is_skinned:
            if skinned.skin_i is None:
                skinned.init_skin(pg, pblob, name2idx)
            names = skinned.graft(pg, pblob, name2idx, matmap, _mat)
        else:
            names = rigid.graft(pg, pblob, name2idx, matmap)
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
    g["buffers"][0]["byteLength"] = len(rigid.blob)
    _write_glb(g, bytes(rigid.blob), out)
    atomic_json(os.path.join(cdir, "export", "assemble.json"),
                {"base": spec["base"], "parts": used, "tris": total})
    print(f"{char_id}: {len(used)} parts, {total} tris -> {out}")


if __name__ == "__main__":
    main(sys.argv[1])
