"""mock provider — procedural placeholder GLB, no GPU, no Blender.

Produces a box mesh sized to the brief's rough proportions so the whole
downstream path (unit render, glb instancing, sockets, publish, golden)
is testable without weights or hardware. Options: w,h,d (meters),
color [r,g,b].
"""
import base64
import json
import struct

def _cube_bin(w, h, d, color):
    x, y, z = w / 2, h / 2, d / 2
    v = [(-x, 0, -z), (x, 0, -z), (x, h, -z), (-x, h, -z),
         (-x, 0, z), (x, 0, z), (x, h, z), (-x, h, z)]
    idx = [0, 1, 2, 0, 2, 3, 4, 6, 5, 4, 7, 6, 0, 4, 5, 0, 5, 1,
           3, 2, 6, 3, 6, 7, 0, 3, 7, 0, 7, 4, 1, 5, 6, 1, 6, 2]
    vb = b"".join(struct.pack("<3f", *p) for p in v)
    ib = b"".join(struct.pack("<3H", *idx[i:i + 3]) for i in range(0, 36, 3))
    return vb + ib, len(vb), v, idx


def generate(cid, cdir, brief, opts, env, out):
    w, h, d = opts.get("w", 0.6), opts.get("h", 1.8), opts.get("d", 0.6)
    color = opts.get("color", [0.7, 0.7, 0.8])
    blob, vb_len, verts, _ = _cube_bin(w, h, d, color)
    gltf = {
        "asset": {"version": "2.0", "generator": "model-maker mock provider"},
        "scene": 0, "scenes": [{"nodes": [0]}],
        "nodes": [{"mesh": 0, "name": cid}],
        "meshes": [{"primitives": [{"attributes": {"POSITION": 0},
                                    "indices": 1, "material": 0}]}],
        "materials": [{"name": "mock",
                       "pbrMetallicRoughness": {
                           "baseColorFactor": [*color, 1.0],
                           "metallicFactor": 0.0, "roughnessFactor": 0.9}}],
        "accessors": [
            {"bufferView": 0, "componentType": 5126, "count": len(verts),
             "type": "VEC3",
             "min": [-w / 2, 0, -d / 2], "max": [w / 2, h, d / 2]},
            {"bufferView": 1, "componentType": 5123, "count": 36,
             "type": "SCALAR"}],
        "bufferViews": [
            {"buffer": 0, "byteOffset": 0, "byteLength": vb_len},
            {"buffer": 0, "byteOffset": vb_len,
             "byteLength": len(blob) - vb_len}],
        "buffers": [{"byteLength": len(blob),
                     "uri": "data:application/octet-stream;base64,"
                            + base64.b64encode(blob).decode()}]}
    js = json.dumps(gltf, separators=(",", ":")).encode()
    js += b" " * (-len(js) % 4)
    with open(out, "wb") as f:
        f.write(struct.pack("<III", 0x46546C67, 2, 12 + 8 + len(js)))
        f.write(struct.pack("<II", len(js), 0x4E4F534A))
        f.write(js)
