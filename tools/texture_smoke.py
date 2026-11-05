"""texture:smoke check — the headless Blender post-step, no GPU/weights.

mock provider cube + generated checker PNG -> blender_texture.py ->
assert a GLB comes out with an embedded baseColorTexture. Covers the
parts that broke before: background-mode UV projection, bake targets,
image packing. Run via tools/check.py texture:smoke.
"""
import json
import os
import struct
import subprocess
import sys
import tempfile
import zlib

TOOLS = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(TOOLS)
sys.path.insert(0, TOOLS)
from providers import base  # noqa: E402


def _png(path, n=64):
    """Minimal RGBA PNG: vertical indigo/white split, opaque."""
    raw = b""
    for y in range(n):
        raw += b"\x00"
        for x in range(n):
            c = (40, 50, 120, 255) if x < n // 2 else (230, 230, 235, 255)
            raw += bytes(c)
    def chunk(tag, data):
        c = tag + data
        return struct.pack(">I", len(data)) + c + struct.pack(
            ">I", zlib.crc32(c) & 0xFFFFFFFF)
    hdr = struct.pack(">IIBBBBB", n, n, 8, 6, 0, 0, 0)
    with open(path, "wb") as f:
        f.write(b"\x89PNG\r\n\x1a\n")
        f.write(chunk(b"IHDR", hdr))
        f.write(chunk(b"IDAT", zlib.compress(raw)))
        f.write(chunk(b"IEND", b""))


def main():
    env = json.load(open(os.path.join(TOOLS, "env.json")))
    blender = env.get("blender") or "blender"
    tmp = tempfile.mkdtemp(prefix="texsmoke_")
    cdir = os.path.join(tmp, "comp")
    os.makedirs(os.path.join(cdir, "accepted"))
    ref = os.path.join(cdir, "accepted", "ref.png")
    _png(ref)
    base.generate("smoke", cdir, {"provider": "mock"}, env)
    src = os.path.join(cdir, "export", "smoke.glb")
    dst = os.path.join(tmp, "out.glb")
    r = subprocess.run(
        [blender, "--background", "--python",
         os.path.join(TOOLS, "blender_texture.py"), "--",
         src, dst, ref],
        capture_output=True, text=True, timeout=300)
    if r.returncode != 0 or not os.path.exists(dst):
        print(r.stdout[-3000:])
        print(r.stderr[-1000:])
        raise SystemExit("blender_texture.py failed")
    blob = open(dst, "rb").read()
    assert blob[:4] == b"glTF", "not a GLB"
    jlen = struct.unpack("<I", blob[12:16])[0]
    gltf = blob[20:20 + jlen]
    assert b"baseColorTexture" in gltf and b'"images"' in gltf, \
        "no embedded texture in output"
    print("texture:smoke PASS —", len(blob), "bytes, texture embedded")


main()
