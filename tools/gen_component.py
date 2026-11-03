"""C1 Generate — batch seeds per component into candidates/.

  python tools/gen_component.py <component_id> [--seeds 4] [--comfy C:/Workspace/ComfyUI]

Type routing (reads pipeline/components/<id>/brief.json):
  sprite      -> Blender depth render (from the 'of'/captain_3d glb) +
                 ControlNet-depth + DreamShaper + BiRefNet alpha
  ui_image    -> plain txt2img (DreamShaper)
  parallax    -> plain txt2img (DreamShaper)
  sprite_variant -> skipped (transform at extract stage)
  glb         -> blender_pirate.py -> build/ + export/
"""
import json, os, sys, time, shutil, subprocess, urllib.request
from pipelib import FileLock, LockHeld, atomic_json

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENV = json.load(open(os.path.join(ROOT, "tools", "env.json")))
BASE = ENV["comfyui_url"]
BLENDER = ENV["blender"]
MODELS = json.load(open(os.path.join(ROOT, "models.json")))
POSES = json.load(open(os.path.join(ROOT, "shared", "poses", "walk_cycle.json")))["poses"]

def post(path, payload):
    req = urllib.request.Request(BASE + path, data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"})
    return json.load(urllib.request.urlopen(req))

def get(path):
    return json.load(urllib.request.urlopen(BASE + path))

def wait_done(pid, timeout=600):
    t0 = time.time()
    while True:
        time.sleep(1.5)
        hist = get(f"/history/{pid}")
        if pid in hist:
            st = hist[pid].get("status", {})
            if st.get("status_str") == "error" or st.get("completed") is False and st.get("status_str") == "error":
                msgs = [m[1].get("exception_message", "") for m in st.get("messages", []) if m[0] == "execution_error"]
                raise RuntimeError(f"ComfyUI job {pid} failed: {msgs}")
            if any(n.get("images") for n in hist[pid]["outputs"].values()):
                return hist[pid]
        if time.time() - t0 > timeout:
            raise TimeoutError(pid)

def copy_out(comfy, img_meta, dst):
    src = os.path.join(comfy, "output", img_meta.get("subfolder", ""), img_meta["filename"])
    shutil.copyfile(src, dst)

def wf_txt2img(prompt, neg, w, h, seed, prefix):
    ckpt = MODELS["checkpoints"]["dreamshaper8"]
    return {"prompt": {
        "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": ckpt}},
        "2": {"class_type": "CLIPTextEncode", "inputs": {"text": prompt, "clip": ["1", 1]}},
        "3": {"class_type": "CLIPTextEncode", "inputs": {"text": neg, "clip": ["1", 1]}},
        "4": {"class_type": "EmptyLatentImage", "inputs": {"width": w, "height": h, "batch_size": 1}},
        "5": {"class_type": "KSampler", "inputs": {"seed": seed, "steps": 28, "cfg": 7.0,
              "sampler_name": "dpmpp_2m_sde", "scheduler": "karras", "denoise": 1.0,
              "model": ["1", 0], "positive": ["2", 0], "negative": ["3", 0], "latent_image": ["4", 0]}},
        "6": {"class_type": "VAEDecode", "inputs": {"samples": ["5", 0], "vae": ["1", 2]}},
        "7": {"class_type": "SaveImage", "inputs": {"filename_prefix": prefix, "images": ["6", 0]}},
    }}

def wf_sprite(prompt, neg, w, h, seed, prefix, depth_img):
    ckpt = MODELS["checkpoints"]["dreamshaper8"]
    cn = MODELS["controlnets"]["sd15_depth"]
    return {"prompt": {
        "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": ckpt}},
        "2": {"class_type": "CLIPTextEncode", "inputs": {"text": prompt, "clip": ["1", 1]}},
        "3": {"class_type": "CLIPTextEncode", "inputs": {"text": neg, "clip": ["1", 1]}},
        "4": {"class_type": "ControlNetLoader", "inputs": {"control_net_name": cn}},
        "5": {"class_type": "LoadImage", "inputs": {"image": depth_img}},
        "6": {"class_type": "ControlNetApply", "inputs": {"conditioning": ["2", 0],
              "control_net": ["4", 0], "image": ["5", 0], "strength": 0.85}},
        "7": {"class_type": "EmptyLatentImage", "inputs": {"width": w, "height": h, "batch_size": 1}},
        "8": {"class_type": "KSampler", "inputs": {"seed": seed, "steps": 28, "cfg": 7.0,
              "sampler_name": "dpmpp_2m_sde", "scheduler": "karras", "denoise": 1.0,
              "model": ["1", 0], "positive": ["6", 0], "negative": ["3", 0], "latent_image": ["7", 0]}},
        "9": {"class_type": "VAEDecode", "inputs": {"samples": ["8", 0], "vae": ["1", 2]}},
        "10": {"class_type": "SaveImage", "inputs": {"filename_prefix": prefix, "images": ["9", 0]}},
    }}

def render_depths(cdir, spec, poses, render_size):
    """Run blender_render.py for the poses -> candidates/_render/<pose>_depth.png"""
    render_dir = os.path.join(cdir, "candidates", "_render")
    spec_path = os.path.join(cdir, "candidates", "_spec.json")
    glb = os.path.join(cdir, "candidates", "_pirate.glb")
    src_glb = os.path.join(ROOT, "pipeline", "components", "captain_3d", "export", "pirate.glb")
    shutil.copyfile(src_glb, glb)
    atomic_json(spec_path, spec)
    subprocess.run([BLENDER, "--background", "--python",
                    os.path.join(ROOT, "tools", "blender_render.py"), "--",
                    "--spec", spec_path, "--glb", glb, "--out", render_dir],
                   check=True, capture_output=True)

def main():
    cid = sys.argv[1]
    seeds_n = int(sys.argv[sys.argv.index("--seeds") + 1]) if "--seeds" in sys.argv else 4
    comfy = sys.argv[sys.argv.index("--comfy") + 1] if "--comfy" in sys.argv else ENV["comfyui_dir"]
    cdir = os.path.join(ROOT, "pipeline", "components", cid)
    b = json.load(open(os.path.join(cdir, "brief.json")))
    style, palette = b["style"], b["palette"]
    cand = os.path.join(cdir, "candidates")
    t = b["type"]

    if t == "sprite_variant":
        print("sprite_variant: transform-only, nothing to generate"); return
    if t == "glb":
        os.makedirs(os.path.join(cdir, "build"), exist_ok=True)
        out = os.path.join(cdir, "build", "pirate.glb")
        r = subprocess.run([BLENDER, "--background", "--python",
                            os.path.join(ROOT, "tools", "blender_pirate.py"),
                            "--", "--out", out], capture_output=True, text=True)
        os.makedirs(os.path.join(cdir, "export"), exist_ok=True)
        shutil.copyfile(out, os.path.join(cdir, "export", "pirate.glb"))
        print("glb built ->", out); return

    prompt = f'{b["prompt_core"]}, {style["suffix"]}, {palette["prompt_hints"]}'
    neg = style["negative"]
    get("/system_stats")

    if t == "sprite":
        # multipass renders drive ControlNet — build spec on the fly
        poses = {p: {"seed": 1000 + i * 100,
                     "bones": POSES.get(p, {}).get("bones", {})}
                 for i, p in enumerate(b["poses"])}
        spec = {"name": cid, "prompt": prompt, "negative": neg,
                "camera": {"ortho_scale": 2.4, "location": [0, -4.2, 1.0], "size": [512, 640]},
                "poses": poses}
        render_depths(cdir, spec, poses, spec["camera"]["size"])
        w, h = spec["camera"]["size"]
        for pose, pc in poses.items():
            depth_dst = f"{cid}_{pose}_depth.png"
            shutil.copyfile(os.path.join(cand, "_render", f"{pose}_depth.png"),
                            os.path.join(comfy, "input", depth_dst))
            for i in range(seeds_n):
                seed = pc["seed"] + i
                prefix = f"{cid}_{pose}_s{seed}"
                pid = post("/prompt", wf_sprite(
                    prompt + f", {style['subject_bg']}", neg, w, h, seed, prefix,
                    depth_dst))["prompt_id"]
                hist = wait_done(pid)
                copy_out(comfy, hist["outputs"]["10"]["images"][0],
                         os.path.join(cand, f"{prefix}.png"))
                print(f"{prefix}.png")
    else:
        w, h = (512, 512) if t == "ui_image" else (768, 512)
        for i in range(seeds_n):
            seed = 5000 + i
            prefix = f"{cid}_s{seed}"
            extra = f", {style['subject_bg']}" if t == "ui_image" else f", {style['scene_suffix']}"
            pid = post("/prompt", wf_txt2img(prompt + extra, neg, w, h, seed, prefix))["prompt_id"]
            hist = wait_done(pid)
            copy_out(comfy, hist["outputs"]["7"]["images"][0],
                     os.path.join(cand, f"{prefix}.png"))
            print(f"{prefix}.png")

def acquire_locks(cid):
    """Claim the component (+ its glb sibling for sprites) before work.
    --goal asserts brief.json ownership; --wait N polls for the lock."""
    cdir = os.path.join(ROOT, "pipeline", "components", cid)
    b = json.load(open(os.path.join(cdir, "brief.json")))
    goal = sys.argv[sys.argv.index("--goal") + 1] if "--goal" in sys.argv else "manual"
    if goal != "manual" and b.get("goal") not in (None, goal):
        sys.exit(f"{cid}: claimed by goal '{b['goal']}' (this run: '{goal}')")
    wait = int(sys.argv[sys.argv.index("--wait") + 1]) if "--wait" in sys.argv else 0
    deps = {cid}
    if b.get("type") == "sprite":
        deps.add("captain_3d")  # depth source — protect against mid-rebuild
    locks = []
    for d in sorted(deps):
        locks.append(FileLock(
            os.path.join(ROOT, "pipeline", "components", d + ".lock"),
            owner=f"{goal}:gen_component", timeout=wait).acquire())
    return locks

if __name__ == "__main__":
    locks = []
    try:
        locks = acquire_locks(sys.argv[1])
        main()
    except LockHeld as e:
        sys.exit(str(e))
    finally:
        for l in reversed(locks):
            l.release()
