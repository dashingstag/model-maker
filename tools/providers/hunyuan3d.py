"""hunyuan3d provider — image->3D via Tencent Hunyuan3D-2-mini (mymeshy
adapter pattern). Real backend for the mannequin->production path.

generate(): accepted/<pick>.png -> hy3dgen shape (1.3M faces) -> quadric
decimate to tri_budget -> export/<cid>.glb. Verified on RTX 5060 Ti
16GB: ~74s shape gen, ~5s decimation. Produces static mesh only — no
skeleton, no texture (texgen paint stage needs the custom_rasterizer
CUDA extension; Windows build is the known friction). Best fit today:
prop components and organic set pieces; rigged actors still need
retopo/rig work after this stage.

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
tri_budget (default brief.tri_budget or 30000), texture (reserved —
paint stage not installed).
"""
import os

_SUBFOLDER = "hunyuan3d-dit-v2-mini"


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
    mesh.export(out)
