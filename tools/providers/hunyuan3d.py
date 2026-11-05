"""hunyuan3d provider — image->3D via Tencent Hunyuan3D-2-mini (mymeshy
adapter pattern). Real backend for the mannequin->production path.

generate(): accepted/<pick>.png -> hy3dgen shape (1.3M faces) -> quadric
decimate to tri_budget -> Blender post-step (tools/blender_texture.py:
optional Quadriflow retopo + smart UV + projection-bake of the accepted
image to albedo, normal-weighted across views) -> export/<cid>.glb with
embedded texture. Verified on RTX 5060 Ti 16GB: ~74s shape gen, ~5s
decimate, ~40s Blender post-step. Still no skeleton — rigged actors
need retopo/rig work after this stage; projection albedo is a degrade
path, not PBR (Hunyuan3D-2.1 paint needs ~21GB VRAM).

Env contract (version pins verified 2026-11, ComfyUI venv):
    pip install --no-deps hy3dgen
    pip install transformers==4.49.0 diffusers==0.33.1
    pip install trimesh pymeshlab pygltflib xatlas onnxruntime ninja \
        pybind11 accelerate omegaconf opencv-python-headless \
        fast-simplification
    # checkpoint encoder keys were written for transformers 4.x naming;
    # 5.x renames q_proj/k_proj and the load fails — do not upgrade.
    # weights: public, snapshot_download('tencent/Hunyuan3D-2mini') ~4GB

Options: subfolder (default 'hunyuan3d-dit-v2-mini'; '-turbo' and
'-fast' variants exist), image (accepted filename, default first .png),
tri_budget (default brief.tri_budget or 30000), texture (default true —
projection-bakes the accepted image to albedo via Blender),
retopo (default false — Quadriflow to tri_budget quads, for
actor-bound meshes), view ('front'|'turntable', default front).
"""
import os
import subprocess
import sys

_SUBFOLDER = "hunyuan3d-dit-v2-mini"
_TOOLS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _accepted_image(cdir, opts):
    adir = os.path.join(cdir, "accepted")
    name = opts.get("image")
    if name:
        return os.path.join(adir, name)
    for f in sorted(os.listdir(adir)):
        if f.lower().endswith(".png"):
            return os.path.join(adir, f)
    raise RuntimeError(f"no accepted image under {adir} for hunyuan3d")


def generate(cid, cdir, brief, opts, env, out):
    from PIL import Image
    import trimesh
    from hy3dgen.shapegen import Hunyuan3DDiTFlowMatchingPipeline

    src = _accepted_image(cdir, opts)
    img = Image.open(src).convert("RGBA")
    bg = Image.new("RGBA", img.size, (255, 255, 255, 255))
    img = Image.alpha_composite(bg, img).convert("RGB")

    pipe = Hunyuan3DDiTFlowMatchingPipeline.from_pretrained(
        "tencent/Hunyuan3D-2mini",
        subfolder=opts.get("subfolder", _SUBFOLDER))
    scene = pipe(image=img)[0]

    meshes = scene.geometry.values() if hasattr(scene, "geometry") else [scene]
    mesh = trimesh.util.concatenate(list(meshes))
    budget = int(opts.get("tri_budget") or brief.get("tri_budget") or 30000)
    if len(mesh.faces) > budget:
        mesh = mesh.simplify_quadric_decimation(face_count=budget)

    if not opts.get("texture", True) and not opts.get("retopo", False):
        mesh.export(out)
        return
    # post-step in Blender: Quadriflow retopo + projection-bake albedo
    raw = out + ".raw.glb"
    mesh.export(raw)
    blender = env.get("blender") or "blender"
    cmd = [blender, "--background", "--python",
           os.path.join(_TOOLS, "blender_texture.py"), "--",
           raw, out, src]
    if opts.get("retopo", False):
        cmd += ["--faces", str(budget)]
    if opts.get("view"):
        cmd += ["--view", str(opts["view"])]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0 or not os.path.exists(out):
        raise RuntimeError(
            f"hunyuan3d blender post-step failed for {cid}:\n"
            + (r.stdout or "")[-2000:] + (r.stderr or "")[-1000:])
    os.remove(raw)
