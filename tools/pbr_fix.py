"""PBR map cleanup for generated GLBs — fix the chrome/plastic look
at the source (the packed metallicRoughness texture), not with
lighting flags.

    python tools/pbr_fix.py <in.glb> <out.glb> [--ao ao.png]
                           [--floor 0.55] [--metal-keep 0.4]

Measured on hunyuan3d output: mean roughness ~0.26 over cloth — the
paint stage writes glossy values everywhere, so live lighting
produces chrome sheen regardless of shading mode. Metallic is
already sane (~0.7% hot pixels) — the fix is a roughness floor on
non-metal pixels, preserving metal/gem response:

    rough' = floor + (1 - floor) * rough   where metal < metal_keep
    rough' = rough                          where metal >= metal_keep

glTF packing: metallicRoughness texture G=roughness, B=metallic
(R unused). Base color is untouched — baked-in albedo highlights
are a separate documented limit, not removable without the
generator's lighting decomposition.

--ao injects a baked occlusion map (R channel) as the material's
occlusionTexture — the missing piece for toon ramp/shadow depth.
"""
import io
import json
import struct
import sys

import numpy as np
from PIL import Image

ARGV = sys.argv[1:]
SRC, OUT = ARGV[0], ARGV[1]
AO = ARGV[ARGV.index("--ao") + 1] if "--ao" in ARGV else None
FLOOR = float(ARGV[ARGV.index("--floor") + 1]) if "--floor" in ARGV else 0.55
MK = float(ARGV[ARGV.index("--metal-keep") + 1]) \
    if "--metal-keep" in ARGV else 0.4


def load_glb(path):
    d = open(path, "rb").read()
    jl = struct.unpack("<I", d[12:16])[0]
    return d, json.loads(d[20:20 + jl]), 20 + jl + 8


def tex_raw(gltf, d, bin_off, tex_index):
    tex = gltf["textures"][tex_index]
    img = gltf["images"][tex["source"]]
    bv = gltf["bufferViews"][img["bufferView"]]
    off = bin_off + bv.get("byteOffset", 0)
    return d[off:off + bv["byteLength"]], img


def rebuild(d, g, bin_off, replaced):
    """Repack the BIN payload view-by-view with 4-byte alignment;
    `replaced` maps bufferView index -> new bytes."""
    payload = d[bin_off:]
    out = bytearray()
    for i, b in enumerate(g["bufferViews"]):
        out += b"\x00" * ((4 - len(out) % 4) % 4)
        off, ln = b.get("byteOffset", 0), b["byteLength"]
        raw = replaced.get(i, payload[off:off + ln])
        b["byteOffset"] = len(out)
        b["byteLength"] = len(raw)
        out += raw
    out += b"\x00" * ((4 - len(out) % 4) % 4)
    g["buffers"][0]["byteLength"] = len(out)
    bin_chunk = struct.pack("<II", len(out), 0x004E4942) + bytes(out)
    js = json.dumps(g, separators=(",", ":")).encode()
    js += b" " * ((4 - len(js) % 4) % 4)
    json_chunk = struct.pack("<II", len(js), 0x4E4F534A) + js
    open(OUT, "wb").write(
        b"glTF" + struct.pack("<II", 2, 12 + len(json_chunk) + len(bin_chunk))
        + json_chunk + bin_chunk)


def main():
    d, g, bin_off = load_glb(SRC)
    mat = g["materials"][0]
    pbr = mat.get("pbrMetallicRoughness", {})
    mr_ref = pbr.get("metallicRoughnessTexture")
    if mr_ref is None:
        print("pbr_fix: no metallicRoughnessTexture — nothing to do")
        return
    raw, img_def = tex_raw(g, d, bin_off, mr_ref["index"])
    im = Image.open(io.BytesIO(raw))
    fmt = "JPEG" if img_def.get("mimeType") == "image/jpeg" else "PNG"
    px = np.asarray(im.convert("RGB")).astype(np.float32)
    rough, metal = px[:, :, 1] / 255.0, px[:, :, 2] / 255.0
    cloth = metal < MK
    px[:, :, 1][cloth] = np.clip(
        (FLOOR + (1.0 - FLOOR) * rough[cloth]) * 255.0, 0, 255)
    print("pbr_fix: rough mean %.2f -> %.2f (floor %.2f on %d%% cloth px)"
          % (rough.mean(), px[:, :, 1].mean() / 255.0, FLOOR,
             100 * cloth.mean()))
    buf = io.BytesIO()
    im2 = Image.fromarray(px.astype(np.uint8))
    im2.save(buf, fmt, quality=95) if fmt == "JPEG" else im2.save(buf, fmt)
    replaced = {img_def["bufferView"]: buf.getvalue()}

    if AO:
        ao = open(AO, "rb").read()
        # reuse the albedo/mr sampler; occlusion reads R channel
        g["images"].append({"mimeType": "image/png",
                            "bufferView": len(g["bufferViews"])})
        g["bufferViews"].append({"buffer": 0,
                                 "byteOffset": 0, "byteLength": len(ao)})
        g["textures"].append({"source": len(g["images"]) - 1})
        mat["occlusionTexture"] = {"index": len(g["textures"]) - 1}
        replaced[len(g["bufferViews"]) - 1] = ao
        print("pbr_fix: occlusionTexture injected (%d bytes)" % len(ao))

    rebuild(d, g, bin_off, replaced)
    print("pbr_fix ->", OUT)


main()
