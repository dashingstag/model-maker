"""TC detail pass — TextureCraft paint stack on top of a GLB's existing
albedo. Adds the shading a per-tri repaint can't express:

  python tools/tc_design.py <in.glb> <out.glb> [--res 2048] [--keep-work]

Layers (all masked by baked mesh maps / position generators):
  * cavity_shade — cool dark on `curvature` cavities: the shell cloud
    bakes AO~1 (open shells) so concave curvature carries the shading
    the flat design_pass fills lack.
  * edge_rim — pale warm fill on `edgeWear`: painterly edge light on
    convex shell edges.
  * band_gold — gold fill on `edgeWear` multiplied by a `position`
    y-band: gilded edges confined to the shoulder/chest zone where the
    concept's filigree lives.

Exports baseColor with `padding: dilation` (native gutter padding —
the #90 mip-bleed fix, handled by the exporter) and re-injects it into
the body's baseColorTexture bufferView; joints/anims/cards untouched.

Requires tools/env.json["texturecraft_cli"].
"""
import io
import json
import os
import sys
import tempfile

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from tc_bake import (ROOT, load_glb, write_glb, patch_uvs, run,
                     _env_path)

ARGV = sys.argv[1:]
SRC, OUT = ARGV[0], ARGV[1]
RES = int(ARGV[ARGV.index("--res") + 1]) if "--res" in ARGV else 2048
KEEP = "--keep-work" in ARGV


def acc(gltf, d, bo, ai):
    a = gltf["accessors"][ai]
    bv = gltf["bufferViews"][a["bufferView"]]
    off = bo + bv.get("byteOffset", 0) + a.get("byteOffset", 0)
    dt = {5126: np.float32, 5123: np.uint16, 5125: np.uint32,
          5121: np.uint8}[a["componentType"]]
    nc = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4}[a["type"]]
    return np.frombuffer(d, dt, a["count"] * nc, off).reshape(a["count"], nc)


def y_to_signal(yw, cy, r):
    """World y -> position-generator signal s = pos·ŷ*0.5+0.5 where
    pos = (s.pos - center)/r, r = half the bbox diagonal."""
    return float((yw - cy) / r * 0.5 + 0.5)


def gen(kind, **kw):
    """params for effect.add.generator on the selected layer's mask"""
    e = {"target": "mask", "generator": kind}
    e.update(kw)
    return {"effect.add.generator": e}


def main():
    env = json.load(open(_env_path()))
    cli = env["texturecraft_cli"]
    d, g, binc = load_glb(SRC)

    # body mesh + albedo image bufferView (the only textured material)
    mi = max(range(len(g["meshes"])), key=lambda i: sum(
        g["accessors"][p["indices"]]["count"]
        for p in g["meshes"][i]["primitives"]))
    pr = g["meshes"][mi]["primitives"][0]
    bo = bo_of(d)
    pos = acc(g, d, bo, pr["attributes"]["POSITION"])
    img_ref = g["images"][g["textures"][g["materials"][0][
        "pbrMetallicRoughness"]["baseColorTexture"]["index"]]["source"]]
    bv = g["bufferViews"][img_ref["bufferView"]]
    raw = d[bo + bv.get("byteOffset", 0):
            bo + bv.get("byteOffset", 0) + bv["byteLength"]]
    albedo = Image.open(io.BytesIO(raw)).convert("RGB")

    # bbox -> generator level conversion (TC normalizes pos by the
    # bbox centre and half-diagonal, see compose/eval.rs coords())
    lo, hi = pos.min(axis=0), pos.max(axis=0)
    center, r = (lo + hi) * 0.5, max(np.linalg.norm(hi - lo) * 0.5, 1e-4)

    work = tempfile.mkdtemp(prefix="tcdesign_")
    pbr = os.path.join(work, "pbr")
    os.makedirs(pbr)
    albedo.save(os.path.join(pbr, "body_baseColor.png"))

    _, g2, binc2 = load_glb(SRC)
    n_patch = patch_uvs(g2, binc2)
    fixed = os.path.join(work, "in.glb")
    write_glb(fixed, g2, binc2)
    proj = os.path.join(work, "proj.tcraft")
    outdir = os.path.join(work, "out")

    # shoulder/chest filigree band ~y 1.4..2.05 world -> signal band
    s_lo = y_to_signal(1.40, center[1], r)
    s_hi = y_to_signal(2.05, center[1], r)

    steps = [
        {"file.importPbrFolder": {"path": pbr.replace(os.sep, "/")}},
        {"bake.run": {"ts": 0, "maps": ["ambientOcclusion", "curvature"]}},
        # --- cavity_shade: cool dark in concave shell valleys — the
        # shell cloud's real signal is curvature, not occlusion (open
        # shells bake AO~1; concave valleys carry the actual shading)
        {"layer.add.fill": {"name": "cavity_shade", "color": "#1a2438"}},
        {"mask.add.white": {}},
        gen("curvature", mode="cavities", level=0.45, softness=0.30),
        {"layer.blend": {"channel": "baseColor", "opacity": 0.45}},
        # --- edge_rim: warm rim on convex edges
        {"layer.add.fill": {"name": "edge_rim", "color": "#e8ddc8"}},
        {"mask.add.white": {}},
        gen("edgeWear", level=0.30, softness=0.25),
        {"layer.blend": {"channel": "baseColor", "opacity": 0.55}},
        # --- band_gold: gilded edges confined to the shoulder band
        {"layer.add.fill": {"name": "band_gold", "color": "#d4a34a"}},
        {"mask.add.white": {}},
        gen("edgeWear", level=0.45, softness=0.15),
        gen("position", direction=[0.0, 1.0, 0.0],
            level=round(1.0 - s_lo, 4), softness=0.06,
            blend="multiply"),
        gen("position", direction=[0.0, 1.0, 0.0],
            level=round(1.0 - s_hi, 4), softness=0.06,
            invert=True, blend="multiply"),
        {"layer.blend": {"channel": "baseColor", "opacity": 0.90}},
        {"file.exportTextures": {
            "dir": outdir.replace(os.sep, "/"), "ts": 0,
            "padding": "dilation", "dilation": 16,
            "preset": {"name": "albedo", "maps": [{
                "file": "$textureSet_baseColor", "format": "Png",
                "bit_depth": 8,
                "channels": [
                    ["R", {"Channel": {"channel": "BaseColor",
                                       "component": 0}}],
                    ["G", {"Channel": {"channel": "BaseColor",
                                       "component": 1}}],
                    ["B", {"Channel": {"channel": "BaseColor",
                                       "component": 2}}]]}]}}},
    ]
    script = {"open": proj.replace(os.sep, "/"),
              "steps": [{"id": list(s)[0], "params": list(s.values())[0]}
                        for s in steps],
              "save": proj.replace(os.sep, "/")}
    js = os.path.join(work, "script.json")
    json.dump(script, open(js, "w"))

    run(cli, ["new", fixed, proj, "--resolution", str(RES)], "new")
    run(cli, ["batch", js], "batch")

    outs = [f for f in os.listdir(outdir) if f.endswith(".png")]
    if not outs:
        raise RuntimeError("tc_design: no baseColor exported")
    img = Image.open(os.path.join(outdir, outs[0])).convert("RGB")
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=95)
    n = inject_albedo(g, binc, img_ref["bufferView"], buf.getvalue())
    write_glb(OUT, g, binc)
    print(f"tc_design: albedo repainted ({n} image), {n_patch} UVs patched"
          f" -> {OUT}")
    if KEEP:
        print("tc_design: work dir kept:", work)


def bo_of(d):
    jlen = int.from_bytes(d[12:16], "little")
    return 20 + jlen + 8


def inject_albedo(g, binc, buffer_view, png_or_jpg):
    """Replace the albedo image's bufferView contents in-place: swap the
    bufferView bytes and fix every later view's offset."""
    bv = g["bufferViews"][buffer_view]
    off, old_len = bv.get("byteOffset", 0), bv["byteLength"]
    binc[off:off + old_len] = png_or_jpg
    delta = len(png_or_jpg) - old_len
    if delta:
        for b2 in g["bufferViews"]:
            if b2.get("byteOffset", 0) > off:
                b2["byteOffset"] = b2.get("byteOffset", 0) + delta
        bv["byteLength"] = len(png_or_jpg)
    return 1


if __name__ == "__main__":
    main()
