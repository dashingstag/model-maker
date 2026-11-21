"""hunyuan3d provider — image->3D via Tencent Hunyuan3D-2-mini (mymeshy
adapter pattern). Real backend for the mannequin->production path.

generate(): accepted/<pick>.png -> hy3dgen shape (1.3M faces) -> quadric
decimate to tri_budget -> texture stage -> export/<cid>.glb.
Verified on RTX 5060 Ti 16GB: ~74s shape gen, ~5s decimate, ~40s
projection bake, ~4min PBR paint (mmgp offload). Still no skeleton —
rigged actors need retopo/rig work after this stage.

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
tri_budget (default brief.tri_budget or 30000), texture (default
'project' — Blender projection-bakes the accepted image to albedo;
'paint' — Hunyuan3D-2.1 PBR multiview paint in the dedicated
hy3dpaint-venv via mmgp offload, env hy3dpaint_python; paint_views/
paint_res tune it), retopo (default false — Quadriflow to tri_budget
quads, for actor-bound meshes; ignored under texture='paint', which
remeshes itself), view ('front'|'turntable', default front),
rig (default none): 'conform' shrinks rig_template (a rigged
humanoid_v1 GLB) to the generated silhouette and bakes the albedo
across — output keeps our skeleton/weights/clips; 'reskin' runs
conform first to produce a weight source sitting on the silhouette,
then skins the PAINTED mesh itself via nearest-conformed-part vertex
transfer (real vertex weights; keeps the painted textures and the
full silhouette instead of template geometry); 'tokenrig' runs
VAST-AI SkinTokens (env skintokens_python/skintokens_dir) — generates
its OWN skeleton (31 bones, generic names), for non-humanoid assets.
post (default []): ordered finishing steps on the final GLB —
'face' adds eye/brow/lip cards bone-parented to `head` (humanoid
rigs only), 'faceplate' adds a sculpted face-plate mesh under the
cards — the hy3d shell has no real face surface (recessed tris are
inner backfaces), so the plate shrink-wraps onto the hood shell with
gaussian relief and re-seats the card stack (tools/face_plate.py),
metallicRoughness map, 'ao' bakes ambient occlusion in Blender and
injects it as occlusionTexture (ao_res tunes bake size), 'tcao' does
the same via texturecraft-cli's GPU ray-traced bake (seconds vs
minutes; also dumps curvature map beside the GLB), 'design'
repaints the atlas per-triangle keyed on model position (cape
gradient/trim, hood unify, face->mask, stray-texel cleanup —
tools/design_pass.py, xianxia-indigo palette). 'tcdesign' runs the
TextureCraft paint stack instead: imported albedo + generator-masked
detail layers (curvature cavities, edge rim, banded gold) exported
with native gutter dilation (tools/tc_design.py).
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

    tex = opts.get("texture", "project")
    tex = "project" if tex is True else ("paint" if tex == "paint" else None)
    blender = env.get("blender") or "blender"

    if tex == "paint":
        # Hunyuan3D-2.1 multiview-diffusion paint in its own venv — the
        # process can segfault at torch+bpy teardown after writing the
        # file, so success = a non-trivial GLB existing, not rc == 0.
        paint_py = env.get("hy3dpaint_python")
        if not paint_py:
            raise RuntimeError(
                "texture='paint' needs env hy3dpaint_python "
                "(dedicated venv, torch 2.7+cu128)")
        raw = out + ".paint_src.glb"
        mesh.export(raw)
        # if paint dies before writing `out`, a stale export there would
        # still pass the existence check below — remove it first
        if os.path.exists(out):
            os.remove(out)
        r = subprocess.run(
            [paint_py, os.path.join(_TOOLS, "hy3d_paint.py"),
             raw, src, out,
             "--views", str(opts.get("paint_views", 6)),
             "--res", str(opts.get("paint_res", 512))],
            capture_output=True, text=True)
        for stale in (raw,
                      os.path.join(os.path.dirname(raw) or ".",
                                   "white_mesh_remesh.obj"),
                      out.replace(".glb", ".mtl"),
                      out.replace(".glb", ".jpg")):
            if os.path.exists(stale):
                os.remove(stale)
        ok = (os.path.exists(out) and os.path.getsize(out) > 4
              and open(out, "rb").read(4) == b"glTF")
        if not ok:
            raise RuntimeError(
                f"hunyuan3d paint step failed for {cid} "
                f"(rc={r.returncode}):\n"
                + (r.stdout or "")[-2000:] + (r.stderr or "")[-1000:])
    elif tex or opts.get("retopo", False):
        # post-step in Blender: Quadriflow retopo + projection-bake albedo
        raw = out + ".raw.glb"
        mesh.export(raw)
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
    else:
        mesh.export(out)
        return

    rig = opts.get("rig")
    if rig == "conform":
        template = opts.get("rig_template")
        if not template or not os.path.exists(template):
            raise RuntimeError(
                f"rig='conform' needs rig_template=<rigged humanoid_v1 "
                f"glb> for {cid}")
        r = subprocess.run(
            [blender, "--background", "--python",
             os.path.join(_TOOLS, "blender_conform.py"), "--",
             os.path.abspath(template), out, out],
            capture_output=True, text=True)
        if r.returncode != 0 or not os.path.exists(out):
            raise RuntimeError(
                f"hunyuan3d conform step failed for {cid}:\n"
                + (r.stdout or "")[-2000:] + (r.stderr or "")[-1000:])
    elif rig == "reskin":
        template = opts.get("rig_template")
        if not template or not os.path.exists(template):
            raise RuntimeError(
                f"rig='reskin' needs rig_template=<rigged humanoid "
                f"glb> for {cid}")
        painted = out + ".painted.glb"
        conformed = out + ".conform.glb"
        os.replace(out, painted)
        try:
            r = subprocess.run(
                [blender, "--background", "--python",
                 os.path.join(_TOOLS, "blender_conform.py"), "--",
                 os.path.abspath(template), painted, conformed],
                capture_output=True, text=True)
            if r.returncode != 0 or not os.path.exists(conformed):
                raise RuntimeError(
                    f"hunyuan3d reskin: conform stage failed for {cid}:\n"
                    + (r.stdout or "")[-2000:] + (r.stderr or "")[-1000:])
            r = subprocess.run(
                [blender, "--background", "--python",
                 os.path.join(_TOOLS, "blender_reskin.py"), "--",
                 conformed, painted, out],
                capture_output=True, text=True)
            if r.returncode != 0 or not os.path.exists(out):
                raise RuntimeError(
                    f"hunyuan3d reskin stage failed for {cid}:\n"
                    + (r.stdout or "")[-2000:] + (r.stderr or "")[-1000:])
        finally:
            for tmp in (painted, conformed):
                if os.path.exists(tmp):
                    os.remove(tmp)
    elif rig == "tokenrig":
        st_py = env.get("skintokens_python")
        st_dir = env.get("skintokens_dir")
        if not st_py or not st_dir:
            raise RuntimeError(
                "rig='tokenrig' needs env skintokens_python/skintokens_dir")
        tmp = out + ".rig.glb"
        r = subprocess.run(
            [st_py, os.path.join(st_dir, "demo.py"),
             "--input", out, "--output", tmp],
            cwd=st_dir, capture_output=True, text=True)
        if r.returncode != 0 or not os.path.exists(tmp):
            raise RuntimeError(
                f"hunyuan3d tokenrig step failed for {cid}:\n"
                + (r.stdout or "")[-2000:] + (r.stderr or "")[-1000:])
        os.replace(tmp, out)
    elif rig:
        raise RuntimeError(f"unknown rig mode '{rig}' for {cid}")

    for step in opts.get("post") or []:
        tmp = out + ".post.glb"
        if step == "face":
            # eye/brow/lip cards bone-parented to `head` (humanoid only)
            cmd = [blender, "--background", "--python",
                   os.path.join(_TOOLS, "blender_face.py"), "--", out, tmp]
        elif step == "faceplate":
            # sculpted face-plate mesh + card re-seat (needs 'face' first)
            cmd = [sys.executable,
                   os.path.join(_TOOLS, "face_plate.py"), out, tmp]
        elif step == "pbr":
            cmd = [sys.executable,
                   os.path.join(_TOOLS, "pbr_fix.py"), out, tmp]
        elif step == "design":
            # texture-space repaint keyed on model position — cape
            # gradient/trim, hood unify, face->mask, stray face-texel
            # cleanup. Palette is xianxia indigo (design_pass.py)
            cmd = [sys.executable,
                   os.path.join(_TOOLS, "design_pass.py"), out, tmp]
        elif step == "ao":
            ao_png = out + ".ao.png"
            r = subprocess.run(
                [blender, "--background", "--python",
                 os.path.join(_TOOLS, "blender_ao.py"), "--",
                 out, ao_png, str(opts.get("ao_res", 1024))],
                capture_output=True, text=True)
            if r.returncode != 0 or not os.path.exists(ao_png):
                raise RuntimeError(
                    f"hunyuan3d ao bake failed for {cid}:\n"
                    + (r.stdout or "")[-2000:] + (r.stderr or "")[-1000:])
            cmd = [sys.executable,
                   os.path.join(_TOOLS, "pbr_fix.py"), out, tmp,
                   "--ao", ao_png]
        elif step == "tcao":
            # texturecraft-cli GPU bake + occlusionTexture inject
            cmd = [sys.executable,
                   os.path.join(_TOOLS, "tc_bake.py"), out, tmp]
        elif step == "tcdesign":
            # texturecraft-cli paint stack: curvature/edge/position
            # generator-masked detail layers over the current albedo,
            # exported with native gutter dilation, re-injected
            cmd = [sys.executable,
                   os.path.join(_TOOLS, "tc_design.py"), out, tmp]
        else:
            raise RuntimeError(f"unknown post step '{step}' for {cid}")
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode != 0 or not os.path.exists(tmp):
            raise RuntimeError(
                f"hunyuan3d post '{step}' failed for {cid}:\n"
                + (r.stdout or "")[-2000:] + (r.stderr or "")[-1000:])
        os.replace(tmp, out)
        if step == "ao" and os.path.exists(out + ".ao.png"):
            os.remove(out + ".ao.png")
