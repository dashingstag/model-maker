"""Hunyuan3D-2.1 paint driver — runs in the hy3dpaint-venv (py3.11,
torch 2.7.1+cu128 — newest cu12 torch the visualbruno cp311 extension
wheels still load under, and the first cu line with sm_120 kernels for
the RTX 5060 Ti; mmgp offload keeps it inside 16GB VRAM).

    hy3dpaint-venv/Scripts/python tools/hy3d_paint.py <mesh.glb>
        <ref.png> <out.glb> [--views 6] [--res 512]

Keeps the multiview diffusion pipeline CPU-resident and streams it via
mmgp so texture gen fits ~6GB VRAM headroom. Requires
env.json: hy3dpaint_dir (repo with hy3dpaint/), hy3dpaint_python.
"""
import argparse
import os
import sys

PAINT = os.environ.get("HY3DPAINT_DIR",
                       r"C:\Workspace\Hunyuan3D-2.1\hy3dpaint")
sys.path.insert(0, PAINT)
os.chdir(PAINT)

p = argparse.ArgumentParser()
p.add_argument("mesh")
p.add_argument("image")
p.add_argument("out")
p.add_argument("--views", type=int, default=6)
p.add_argument("--res", type=int, default=512)
args = p.parse_args()

# Windows: are_symlinks_supported() probes a hardlink, but real symlink
# creation then fails with WinError 1314 (not caught as PermissionError).
# Force the hub's copy fallback for cache snapshot pointers.
import huggingface_hub.file_download as _hfd  # noqa: E402

_hfd.are_symlinks_supported = lambda *a, **k: False

# The prebuilt wheel installs mesh_inpaint_processor top-level, but the
# official code imports it as a DifferentiableRenderer submodule — alias it.
import mesh_inpaint_processor  # noqa: E402
import DifferentiableRenderer  # noqa: E402

sys.modules["DifferentiableRenderer.mesh_inpaint_processor"] = (
    mesh_inpaint_processor)

from mmgp import offload, profile_type  # noqa: E402
from textureGenPipeline import (  # noqa: E402
    Hunyuan3DPaintConfig, Hunyuan3DPaintPipeline)

conf = Hunyuan3DPaintConfig(args.views, args.res)
conf.device = "cpu"
conf.multiview_cfg_path = os.path.join(PAINT, "cfgs",
                                       "hunyuan-paint-pbr.yaml")
pipe = Hunyuan3DPaintPipeline(conf)
try:
    core = pipe.models["multiview_model"].pipeline
    offload.profile(core, profile_type.LowRAM_LowVRAM)
except Exception as e:
    print("mmgp profile failed, running without offload:", e)
pipe(mesh_path=args.mesh, image_path=args.image,
     output_mesh_path=args.out)
print("painted ->", args.out)
