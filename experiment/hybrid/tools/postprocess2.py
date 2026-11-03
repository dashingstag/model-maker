"""Hybrid pipeline stage 3: package painted sprites + geometry-derived normals.

For each pose:
  painted RGBA -> tight crop -> sprite_{pose}.png
  Blender normal render (cropped to beauty-alpha bbox, resized to painted bbox,
  painted alpha applied) -> sprite_{pose}_n.png

Run with ComfyUI venv python:
  venv/Scripts/python tools/postprocess2.py <painted_dir> <renders_dir> <spec> <assets_dir>
"""
import sys, os, json
from PIL import Image, ImageFilter
import numpy as np

painted_dir, renders, spec_path, assets = sys.argv[1:5]
spec = json.load(open(spec_path))
os.makedirs(assets, exist_ok=True)
manifest = {"name": spec["name"], "prompt": spec["prompt"],
            "model": "DreamShaper_8_pruned", "controlnet": "sd15_depth_fp16",
            "matting": "BiRefNet", "poses": {}}

for pose in spec["poses"]:
    painted = Image.open(os.path.join(painted_dir, f"{pose}.png")).convert("RGBA")
    sprite = painted.crop(painted.getbbox())

    beauty = Image.open(os.path.join(renders, f"{pose}_beauty.png")).convert("RGBA")
    normal = Image.open(os.path.join(renders, f"{pose}_normal.png")).convert("RGB")
    bb = beauty.split()[3].getbbox()
    nrm = normal.crop(bb).resize(sprite.size, Image.LANCZOS)
    nrm.putalpha(sprite.split()[3])

    sprite.save(os.path.join(assets, f"sprite_{pose}.png"))
    nrm.save(os.path.join(assets, f"sprite_{pose}_n.png"))
    manifest["poses"][pose] = {"seed": spec["poses"][pose]["seed"],
                               "sprite": f"sprite_{pose}.png",
                               "normal": f"sprite_{pose}_n.png",
                               "size": list(sprite.size)}
    print(f"{pose}: {sprite.size}")

json.dump(manifest, open(os.path.join(assets, "manifest.json"), "w"), indent=2)
print("packaged ->", assets)
