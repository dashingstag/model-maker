"""Face-region albedo detail pass — sharpen painted facial features on
generated (blob-topology) meshes, in texture space.

    python tools/face_detail.py <in.glb> <out.glb> [--dry]

Generated faces arrive as blurred paint on convex blobs: no eye
sockets, no iris geometry, lips as color smudges. Geometric eye cards
float on such a surface and double-draw over the painted features —
the honest fix at this fidelity tier is repainting the features *in
the texture* (same class as deterministic palette transforms).

Landmark detection is self-locating: the generator already painted
(weak) eyes/lips — those regions read as dark/saturated patches under
the UVs of front-facing head verts. We cluster those, then draw:

  * eyes: crisp iris disc + dark lash arc + white catchlight, per side
  * lips: hue lift + soft edge toward the painted lip color
  * chin/neck: desaturate stray tint bleed (hy3d greenish shadow)

Everything is parameterized by head-region windows in model space —
recorded per-asset via --inspect if a different sculpt needs tuning.
Fails soft: missing landmarks skip that feature (advisory, not fail).
"""
import io
import json
import math
import struct
import sys

import numpy as np
from PIL import Image, ImageDraw

ARGV = sys.argv[1:]
SRC, OUT = ARGV[0], ARGV[1]
DRY = "--dry" in ARGV


def load_glb(path):
    d = open(path, "rb").read()
    jl = struct.unpack("<I", d[12:16])[0]
    gltf = json.loads(d[20:20 + jl])
    return d, gltf, 20 + jl + 8


def acc_arr(gltf, d, bin_off, ai):
    a = gltf["accessors"][ai]
    bv = gltf["bufferViews"][a["bufferView"]]
    off = bin_off + bv.get("byteOffset", 0) + a.get("byteOffset", 0)
    dt = {5126: np.float32, 5123: np.uint16, 5121: np.uint8,
          5125: np.uint32}[a["componentType"]]
    nc = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4}[a["type"]]
    return np.frombuffer(d, dt, a["count"] * nc, off).reshape(a["count"], nc)


def albedo_image(gltf, d, bin_off):
    img_i = gltf["materials"][0]["pbrMetallicRoughness"][
        "baseColorTexture"]["index"]
    tex = gltf["textures"][img_i]
    img = gltf["images"][tex["source"]]
    bv = gltf["bufferViews"][img["bufferView"]]
    raw = d[bin_off + bv.get("byteOffset", 0):
            bin_off + bv.get("byteOffset", 0) + bv["byteLength"]]
    return Image.open(io.BytesIO(raw)).convert("RGB"), img


def main():
    d, g, bin_off = load_glb(SRC)
    prim = g["meshes"][0]["primitives"][0]
    pos = acc_arr(g, d, bin_off, prim["attributes"]["POSITION"])
    nrm = acc_arr(g, d, bin_off, prim["attributes"]["NORMAL"])
    uv = acc_arr(g, d, bin_off, prim["attributes"]["TEXCOORD_0"])
    im, img_def = albedo_image(g, d, bin_off)
    W, H = im.size
    px = np.asarray(im).astype(np.float32)

    ymax, ymin = pos[:, 1].max(), pos[:, 1].min()
    span = ymax - ymin
    # glTF is y-up, forward +Z: the face = top verts pointing +Z
    front = nrm[:, 2] > 0.35
    head_y = pos[:, 1] > ymax - span * 0.16
    face = np.where(front & head_y)[0]
    if len(face) < 30:
        print("face_detail: only %d front-head verts — no-op" % len(face))
        return
    fpos = pos[face]
    fuv = uv[face]

    # landmark by model-space position, not texture darkness: the eye
    # is the face vert nearest a canonical eye point (front of the
    # head, upper-mid band). Texture-side detection smears across the
    # shell-cloud's scattered islands.
    yc = (fpos[:, 1].max() + fpos[:, 1].min()) / 2
    ysp = np.ptp(fpos[:, 1])
    eye_y = yc + ysp * 0.10
    front_z = np.percentile(fpos[:, 2], 92)
    dr = ImageDraw.Draw(im, "RGBA")

    def draw_eye(side, name):
        want = np.array([side * 0.045, eye_y, front_z])
        d3 = np.linalg.norm(fpos - want, axis=1)
        k = int(np.argmin(d3))
        if d3[k] > 0.05:
            print("face_detail: no %s eye vert within 5cm (d=%.3f)"
                  % (name, d3[k]))
            return
        cx = int(np.clip(fuv[k, 0] * W, 0, W - 1))
        cy = int(np.clip(fuv[k, 1] * H, 0, H - 1))
        ex, ey = 22, 13
        print("face_detail: %s eye at uv(%.0f,%.0f) r(%.0f,%.0f)"
              % (name, cx, cy, ex, ey))
        # lash line — dark arc across the upper eye
        dr.arc([cx - ex, cy - ey * 1.5, cx + ex, cy + ey * 1.1],
               start=200, end=340, fill=(28, 20, 24, 220), width=max(2, int(ey * 0.28)))
        # iris disc — cool grey-cyan matching the sage palette
        dr.ellipse([cx - ex * 0.62, cy - ey * 0.85, cx + ex * 0.62,
                    cy + ey * 0.85], fill=(52, 96, 104, 255))
        dr.ellipse([cx - ex * 0.30, cy - ey * 0.45, cx + ex * 0.30,
                    cy + ey * 0.45], fill=(16, 18, 22, 255))
        # catchlight
        dr.ellipse([cx - ex * 0.22, cy - ey * 0.72, cx - ex * 0.02,
                    cy - ey * 0.42], fill=(235, 245, 250, 235))

    draw_eye(-1.0, "l")
    draw_eye(1.0, "r")

    # lips: the face vert nearest the midline below eye level
    want_lip = np.array([0.0, eye_y - 0.055, front_z])
    d3 = np.linalg.norm(fpos - want_lip, axis=1)
    k = int(np.argmin(d3))
    if d3[k] < 0.05:
        lx = int(np.clip(fuv[k, 0] * W, 0, W - 1))
        ly = int(np.clip(fuv[k, 1] * H, 0, H - 1))
        lw, lh = 16, 7
        print("face_detail: lips at uv(%.0f,%.0f) r(%.0f,%.0f)" % (lx, ly, lw, lh))
        dr.ellipse([lx - lw, ly - lh * 0.4, lx + lw, ly + lh * 0.6],
                   fill=(150, 62, 58, 70))
    else:
        print("face_detail: no lip vert within 5cm")

    # chin/neck tint cleanup — desaturate greenish bleed below the face
    us = np.clip((fuv[:, 0] * W).astype(int), 0, W - 1)
    vs = np.clip((fuv[:, 1] * H).astype(int), 0, H - 1)
    chin = (np.abs(fpos[:, 0]) < 0.05) & (fpos[:, 1] < ymax - span * 0.10) \
           & (nrm[face, 2] > 0.2)
    for i in np.where(chin)[0][:400]:
        x, y = us[i], vs[i]
        c = px[y, x]
        if c[1] > c[0] * 1.08 and c[1] > c[2] * 1.05:
            gmean = c.mean()
            px[y, x] = c * 0.55 + np.array([gmean * 0.9, gmean, gmean * 0.75]) * 0.45
    im2 = Image.fromarray(px.astype(np.uint8))

    if DRY:
        im2.resize((W // 4, H // 4)).save("C:/tmp/face_detail_dry.png")
        print("face_detail: --dry wrote C:/tmp/face_detail_dry.png")
        return

    # re-embed: rebuild the BIN payload view-by-view with 4-byte
    # alignment — splicing in place misaligns every accessor after the
    # (arbitrarily sized) image and produces garbage indices
    buf = io.BytesIO()
    fmt = "JPEG" if img_def.get("mimeType") == "image/jpeg" else "PNG"
    im2.save(buf, fmt, quality=95) if fmt == "JPEG" else im2.save(buf, fmt)
    raw = buf.getvalue()
    payload = d[bin_off:]  # bin_off already lands past the chunk header
    img_bvi = img_def["bufferView"]
    new_payload = bytearray()
    for i, b in enumerate(g["bufferViews"]):
        pad = (4 - len(new_payload) % 4) % 4
        new_payload += b"\x00" * pad
        off, ln = b.get("byteOffset", 0), b["byteLength"]
        b["byteOffset"] = len(new_payload)
        new_payload += (raw if i == img_bvi
                        else payload[off:off + ln])
        b["byteLength"] = len(raw) if i == img_bvi else ln
    new_payload += b"\x00" * ((4 - len(new_payload) % 4) % 4)
    g["buffers"][0]["byteLength"] = len(new_payload)
    bin_chunk = struct.pack("<II", len(new_payload), 0x004E4942) + new_payload
    js = json.dumps(g, separators=(",", ":")).encode()
    js += b" " * ((4 - len(js) % 4) % 4)
    json_chunk = struct.pack("<II", len(js), 0x4E4F534A) + js
    total = 12 + len(json_chunk) + len(bin_chunk)
    open(OUT, "wb").write(
        b"glTF" + struct.pack("<II", 2, total) + json_chunk + bin_chunk)
    print("face_detail ->", OUT)


main()
