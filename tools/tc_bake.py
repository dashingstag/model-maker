"""Bake ambient occlusion with texturecraft-cli and inject it into a GLB.

  python tools/tc_bake.py <in.glb> <out.glb> [--res 2048] [--maps ao,curvature]

Why: blender_ao.py runs a Cycles bake (minutes); texturecraft-cli ray-traces
the same mesh maps on the GPU (seconds) and also gives curvature/thickness/
bentNormal for later passes. The injected AO lands on the model's ORIGINAL
atlas UVs — TextureCraft only auto-unwraps when a primitive lacks UVs, so
any UV-less primitives (e.g. blender_face cards) get a degenerate UV patch
in a temp copy first.

--maps also dumps the extra mesh maps next to <out> for inspection/future
use (curvature feeds edge-wear masks in a tc_design pass).

Requires tools/env.json["texturecraft_cli"] pointing at texturecraft-cli(.exe).
"""
import json
import os
import struct
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

MAP_ID = {"ao": "AmbientOcclusion", "curvature": "Curvature",
          "thickness": "Thickness", "position": "Position",
          "bentNormal": "BentNormal", "worldNormal": "WorldNormal"}


def load_glb(path):
    d = open(path, "rb").read()
    jlen = struct.unpack_from("<I", d, 12)[0]
    g = json.loads(d[20:20 + jlen])
    off = 20 + jlen + 8
    blen = struct.unpack_from("<I", d, 20 + jlen)[0]
    return d, g, bytearray(d[off:off + blen])


def write_glb(path, g, binc):
    g["buffers"][0]["byteLength"] = len(binc)
    j = json.dumps(g, separators=(",", ":")).encode()
    while len(j) % 4:
        j += b" "
    b = bytearray()
    b += struct.pack("<4s", b"glTF") + struct.pack("<II", 2, 0)
    b += struct.pack("<I", len(j)) + b"JSON" + j
    b += struct.pack("<I", len(binc)) + b"BIN\x00" + bytes(binc)
    struct.pack_into("<I", b, 8, len(b))
    open(path, "wb").write(b)


def patch_uvs(g, binc):
    """Degenerate TEXCOORD_0 on every primitive that lacks one so TC keeps
    the real atlas instead of auto-unwrapping the whole mesh."""
    while len(binc) % 4:
        binc.append(0)
    patched = 0
    for mesh in g["meshes"]:
        for prim in mesh["primitives"]:
            a = prim["attributes"]
            if "TEXCOORD_0" in a or "POSITION" not in a:
                continue
            n = g["accessors"][a["POSITION"]]["count"]
            uv = struct.pack(f"<{n * 2}f", *([0.5, 0.5] * n))
            g["bufferViews"].append({"buffer": 0, "byteOffset": len(binc),
                                     "byteLength": len(uv), "target": 34962})
            binc += uv
            while len(binc) % 4:
                binc.append(0)
            g["accessors"].append({
                "bufferView": len(g["bufferViews"]) - 1, "byteOffset": 0,
                "componentType": 5126, "count": n, "type": "VEC2",
                "min": [0.5, 0.5], "max": [0.5, 0.5]})
            a["TEXCOORD_0"] = len(g["accessors"]) - 1
            patched += 1
    return patched


def inject_ao(g, binc, png):
    """Attach <png> as occlusionTexture on every material that has a
    metallicRoughness base (the painted body; cards carry no texture)."""
    n = 0
    for mat in g.get("materials", []):
        mr = mat.get("pbrMetallicRoughness")
        # only textured materials — cards with degenerate UVs would sample
        # whatever texel sits at (0.5, 0.5) of the atlas
        if not mr or "baseColorTexture" not in mr:
            continue
        g["bufferViews"].append({"buffer": 0, "byteOffset": len(binc),
                                 "byteLength": len(png)})
        binc += png
        while len(binc) % 4:
            binc.append(0)
        g["images"].append({"bufferView": len(g["bufferViews"]) - 1,
                            "mimeType": "image/png"})
        g["textures"].append({"source": len(g["images"]) - 1})
        mat["occlusionTexture"] = {"index": len(g["textures"]) - 1}
        n += 1
    return n


def run(cli, args, what):
    r = subprocess.run([cli] + args, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(
            f"texturecraft-cli {what} failed:\n"
            + (r.stdout or "")[-2000:] + (r.stderr or "")[-1000:])
    return r.stdout


def main():
    argv = sys.argv[1:]
    src, out = argv[0], argv[1]
    res = int(argv[argv.index("--res") + 1]) if "--res" in argv else 2048
    maps = (argv[argv.index("--maps") + 1].split(",")
            if "--maps" in argv else ["ao"])
    env = json.load(open(os.path.join(_env_path())))
    cli = env["texturecraft_cli"]
    _, g, binc = load_glb(src)
    patched = patch_uvs(g, binc)
    if patched:
        print(f"tc_bake: patched UVs on {patched} primitives")

    work = tempfile.mkdtemp(prefix="tcbake_")
    fixed = os.path.join(work, "in.glb")
    write_glb(fixed, g, binc)
    proj = os.path.join(work, "proj.tcraft")

    run(cli, ["new", fixed, proj, "--resolution", str(res)], "new")
    run(cli, ["bake", proj, "--resolution", str(res)], "bake")

    # export each requested map on texture set 0 (the generated body —
    # card materials carry no atlas and their maps are unusable anyway)
    outdir = os.path.join(work, "maps")
    maps = [{"file": f"$textureSet_{m}", "format": "Png", "bit_depth": 8,
             "channels": [["L", {"Baked": {"map": MAP_ID[m]}}]]}
            if m not in ("position", "worldNormal", "bentNormal") else
            {"file": f"$textureSet_{m}", "format": "Png", "bit_depth": 8,
             "channels": [["R", {"Baked": {"map": MAP_ID[m], "component": 0}}],
                          ["G", {"Baked": {"map": MAP_ID[m], "component": 1}}],
                          ["B", {"Baked": {"map": MAP_ID[m], "component": 2}}]]}
            for m in maps]
    preset = json.dumps({"name": "tcbake", "maps": maps})
    out = run(cli, ["run", proj, "file.exportTextures",
                    json.dumps({"dir": outdir, "preset": json.loads(preset),
                                "ts": 0})], "export")

    files = sorted(os.listdir(outdir))
    body_name = None
    for f in files:
        if f.endswith("_ao.png") or (maps == ["ao"] and f.endswith(".png")):
            body_name = f
    if body_name is None:
        raise RuntimeError(f"tc_bake: no AO map exported, got {files}")
    ao = open(os.path.join(outdir, body_name), "rb").read()

    # extra maps kept beside <out> for inspection/future passes
    for f in files:
        if f != body_name:
            dst = out + "." + f.rsplit("_", 1)[-1]
            open(dst, "wb").write(open(os.path.join(outdir, f), "rb").read())

    _, g2, binc2 = load_glb(src)  # fresh copy: real atlas, real geometry
    n = inject_ao(g2, binc2, ao)
    if n == 0:
        raise RuntimeError("tc_bake: no pbrMetallicRoughness material to "
                           "attach occlusionTexture")
    write_glb(out, g2, binc2)
    print(f"tc_bake: AO injected on {n} material(s) -> {out}")


def _env_path():
    return os.path.join(ROOT, "tools", "env.json")


if __name__ == "__main__":
    main()
