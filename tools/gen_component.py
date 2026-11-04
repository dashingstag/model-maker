"""C1 Generate — batch seeds per component into candidates/.

  python tools/gen_component.py <component_id> [--seeds N] [--goal G] [--wait S]
                                [--comfy C:/Workspace/ComfyUI]

Type routing (reads pipeline/components/<id>/brief.json):
  sprite      -> Blender depth render from the brief's `guide_from` glb
                 component (default captain_3d) + ControlNet-depth +
                 DreamShaper (matte happens later, at extract)
  ui_image    -> plain txt2img (DreamShaper)
  parallax    -> plain txt2img (DreamShaper)
  sprite_variant -> skipped (transform at extract stage)
  glb         -> registered builder (GLB_BUILDERS) -> build/ + export/<id>.glb

Prompt = prompt_core + prompt_extra + must_have + per-pose prompt_extra +
style suffix + palette hints; negative = style negative + neg_extra +
must_not. Seeds default to the brief's `seeds` (else 3). Every candidate
is logged incrementally to candidates/index.json; seeds already on disk
are skipped (resume).
"""
import json, os, sys, time, shutil, subprocess, urllib.request
from pipelib import FileLock, LockHeld, atomic_json, name_of

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENV = json.load(open(os.path.join(ROOT, "tools", "env.json")))
BASE = ENV["comfyui_url"]
BLENDER = ENV["blender"]
MODELS = json.load(open(os.path.join(ROOT, "models.json")))
POSES = {}
for _pf in sorted(os.listdir(os.path.join(ROOT, "shared", "poses"))):
    if _pf.endswith(".json"):
        POSES.update(json.load(open(os.path.join(ROOT, "shared", "poses", _pf)))
                     .get("poses", {}))
SAMPLER = {"steps": 28, "cfg": 7.0, "sampler_name": "dpmpp_2m_sde",
           "scheduler": "karras", "cn_strength": 0.85}
# glb builders by component id; components without one need tooling first
GLB_BUILDERS = {"captain_3d": "blender_pirate.py",
                "guide_humanoid": "blender_mannequin.py",
                "xx_azure_sage_3d": "blender_hero.py",
                "xx_sage_staff_3d": {"script": "blender_prop.py", "args": ["--kind", "staff"]},
                "xx_jian_3d": {"script": "blender_prop.py", "args": ["--kind", "jian"]}}

def comp_dir(cid):
    return os.path.join(ROOT, "pipeline", "components", cid)

def glb_path(cid):
    """export/<id>.glb, falling back to the legacy export/pirate.glb."""
    for name in (f"{cid}.glb", "pirate.glb"):
        p = os.path.join(comp_dir(cid), "export", name)
        if os.path.exists(p):
            return p
    raise FileNotFoundError(f"{cid}: no export/<id>.glb")

def post(path, payload):
    req = urllib.request.Request(BASE + path, data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"})
    return json.load(urllib.request.urlopen(req))

def get(path):
    return json.load(urllib.request.urlopen(BASE + path))

def wait_done(pid, timeout=900):
    t0 = time.time()
    while True:
        time.sleep(1.5)
        hist = get(f"/history/{pid}")
        if pid in hist:
            st = hist[pid].get("status", {})
            if st.get("status_str") == "error" or st.get("completed") is False:
                msgs = [m[1].get("exception_message", "") for m in st.get("messages", [])
                        if m[0] == "execution_error"]
                raise RuntimeError(f"ComfyUI job {pid} failed: {msgs}")
            if any(n.get("images") for n in hist[pid].get("outputs", {}).values()):
                return hist[pid]
        if time.time() - t0 > timeout:
            raise TimeoutError(pid)

def copy_out(comfy, img_meta, dst):
    src = os.path.join(comfy, "output", img_meta.get("subfolder", ""), img_meta["filename"])
    shutil.copyfile(src, dst)

def _ksampler(seed, model, pos, neg, latent):
    return {"class_type": "KSampler", "inputs": {
        "seed": seed, "steps": SAMPLER["steps"], "cfg": SAMPLER["cfg"],
        "sampler_name": SAMPLER["sampler_name"], "scheduler": SAMPLER["scheduler"],
        "denoise": 1.0, "model": model, "positive": pos, "negative": neg,
        "latent_image": latent}}

def wf_txt2img(prompt, neg, w, h, seed, prefix):
    ckpt = MODELS["checkpoints"]["dreamshaper8"]
    return {"prompt": {
        "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": ckpt}},
        "2": {"class_type": "CLIPTextEncode", "inputs": {"text": prompt, "clip": ["1", 1]}},
        "3": {"class_type": "CLIPTextEncode", "inputs": {"text": neg, "clip": ["1", 1]}},
        "4": {"class_type": "EmptyLatentImage", "inputs": {"width": w, "height": h, "batch_size": 1}},
        "5": _ksampler(seed, ["1", 0], ["2", 0], ["3", 0], ["4", 0]),
        "6": {"class_type": "VAEDecode", "inputs": {"samples": ["5", 0], "vae": ["1", 2]}},
        "7": {"class_type": "SaveImage", "inputs": {"filename_prefix": prefix, "images": ["6", 0]}},
    }}

def wf_sprite(prompt, neg, w, h, seed, prefix, depth_img, init_img=None, denoise=1.0):
    """ControlNet-depth sprite. With init_img: img2img from an accepted
    pose (identity lock — same face/outfit, new pose from the depth)."""
    ckpt = MODELS["checkpoints"]["dreamshaper8"]
    cn = MODELS["controlnets"]["sd15_depth"]
    wf = _wf_sprite(prompt, neg, w, h, seed, prefix, depth_img, ckpt, cn)
    if init_img:
        p = wf["prompt"]
        p["11"] = {"class_type": "LoadImage", "inputs": {"image": init_img}}
        p["12"] = {"class_type": "ImageScale", "inputs": {
            "image": ["11", 0], "upscale_method": "lanczos", "width": w, "height": h,
            "crop": "disabled"}}
        p["13"] = {"class_type": "VAEEncode", "inputs": {"pixels": ["12", 0], "vae": ["1", 2]}}
        p["8"]["inputs"]["latent_image"] = ["13", 0]
        p["8"]["inputs"]["denoise"] = denoise
    return wf

def _wf_sprite(prompt, neg, w, h, seed, prefix, depth_img, ckpt, cn):
    return {"prompt": {
        "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": ckpt}},
        "2": {"class_type": "CLIPTextEncode", "inputs": {"text": prompt, "clip": ["1", 1]}},
        "3": {"class_type": "CLIPTextEncode", "inputs": {"text": neg, "clip": ["1", 1]}},
        "4": {"class_type": "ControlNetLoader", "inputs": {"control_net_name": cn}},
        "5": {"class_type": "LoadImage", "inputs": {"image": depth_img}},
        "6": {"class_type": "ControlNetApply", "inputs": {"conditioning": ["2", 0],
              "control_net": ["4", 0], "image": ["5", 0], "strength": SAMPLER["cn_strength"]}},
        "7": {"class_type": "EmptyLatentImage", "inputs": {"width": w, "height": h, "batch_size": 1}},
        "8": _ksampler(seed, ["1", 0], ["6", 0], ["3", 0], ["7", 0]),
        "9": {"class_type": "VAEDecode", "inputs": {"samples": ["8", 0], "vae": ["1", 2]}},
        "10": {"class_type": "SaveImage", "inputs": {"filename_prefix": prefix, "images": ["9", 0]}},
    }}

def wf_img2img(prompt, neg, w, h, seed, prefix, init_img=None, denoise=1.0):
    """Guide-free sprite path: txt2img when init_img is None; img2img
    (identity-lock repaint from an accepted pose) when set."""
    ckpt = MODELS["checkpoints"]["dreamshaper8"]
    p = {"prompt": {
        "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": ckpt}},
        "2": {"class_type": "CLIPTextEncode", "inputs": {"text": prompt, "clip": ["1", 1]}},
        "3": {"class_type": "CLIPTextEncode", "inputs": {"text": neg, "clip": ["1", 1]}},
        "7": {"class_type": "EmptyLatentImage", "inputs": {"width": w, "height": h, "batch_size": 1}},
        "8": _ksampler(seed, ["1", 0], ["2", 0], ["3", 0], ["7", 0]),
        "9": {"class_type": "VAEDecode", "inputs": {"samples": ["8", 0], "vae": ["1", 2]}},
        "10": {"class_type": "SaveImage", "inputs": {"filename_prefix": prefix, "images": ["9", 0]}},
    }}["prompt"]
    if init_img:
        p["11"] = {"class_type": "LoadImage", "inputs": {"image": init_img}}
        p["12"] = {"class_type": "ImageScale", "inputs": {
            "image": ["11", 0], "upscale_method": "lanczos", "width": w, "height": h,
            "crop": "disabled"}}
        p["13"] = {"class_type": "VAEEncode", "inputs": {"pixels": ["12", 0], "vae": ["1", 2]}}
        p["8"]["inputs"]["latent_image"] = ["13", 0]
        p["8"]["inputs"]["denoise"] = denoise
    return {"prompt": p}

PROP_SUFFIX = ("fantasy game prop concept art, single isolated object only, no people, "
               "clean product presentation, painterly detail, masterpiece")
PROP_NEG = ("person, human, character, figure, woman, female, girl, man, male, boy, "
            "portrait, face, eyes, hair, hands, arms, body, legs, dress, robes worn, "
            "wielder, wielding, holding")

def build_prompts(b):
    style, palette = b["style"], b["palette"]
    suffix = (style.get("prop_suffix") or PROP_SUFFIX) if b.get("prop") else style["suffix"]
    hints = palette.get("prop_hints", palette["prompt_hints"]) if b.get("prop") else palette["prompt_hints"]
    parts = [b["prompt_core"], b.get("prompt_extra"), ", ".join(b.get("must_have", [])),
             suffix, hints]
    neg = [style["negative"], PROP_NEG if b.get("prop") else None,
           b.get("neg_extra"), ", ".join(b.get("must_not", []))]
    return ", ".join(p for p in parts if p), ", ".join(n for n in neg if n)

def render_depths(cdir, guide, spec):
    """Run blender_render.py for the poses -> candidates/_render/<pose>_*.png"""
    render_dir = os.path.join(cdir, "candidates", "_render")
    spec_path = os.path.join(cdir, "candidates", "_spec.json")
    glb = os.path.join(cdir, "candidates", "_guide.glb")
    shutil.copyfile(glb_path(guide), glb)
    atomic_json(spec_path, spec)
    subprocess.run([BLENDER, "--background", "--python",
                    os.path.join(ROOT, "tools", "blender_render.py"), "--",
                    "--spec", spec_path, "--glb", glb, "--out", render_dir],
                   check=True, capture_output=True)

class Index:
    """candidates/index.json — incremental provenance log, resume-aware."""
    def __init__(self, cand):
        self.path = os.path.join(cand, "index.json")
        self.data = json.load(open(self.path)) if os.path.exists(self.path) \
            else {"candidates": []}
    def has(self, fname):
        return any(c["file"] == fname for c in self.data["candidates"])
    def add(self, rec):
        self.data["candidates"].append(rec)
        atomic_json(self.path, self.data)

def run_seed(idx, cand, comfy, wf, out_node, rec):
    fname = rec["file"]
    if idx.has(fname) and os.path.exists(os.path.join(cand, fname)):
        print(f"skip {fname} (on disk)"); return
    t0 = time.time()
    pid = post("/prompt", wf)["prompt_id"]
    hist = wait_done(pid)
    copy_out(comfy, hist["outputs"][out_node]["images"][0], os.path.join(cand, fname))
    rec.update({"elapsed_s": round(time.time() - t0, 1), "ts": time.time(),
                "device": ENV.get("versions", {}).get("comfyui_device"),
                "comfyui": ENV.get("versions", {}).get("comfyui"),
                "model": MODELS["checkpoints"]["dreamshaper8"], **SAMPLER})
    idx.add(rec)
    print(fname)

def main():
    cid = sys.argv[1]
    cdir = comp_dir(cid)
    b = json.load(open(os.path.join(cdir, "brief.json")))
    seeds_n = int(sys.argv[sys.argv.index("--seeds") + 1]) if "--seeds" in sys.argv \
        else int(b.get("seeds", 3))
    comfy = sys.argv[sys.argv.index("--comfy") + 1] if "--comfy" in sys.argv else ENV["comfyui_dir"]
    cand = os.path.join(cdir, "candidates")
    os.makedirs(cand, exist_ok=True)
    t = b["type"]

    if t == "sprite_variant":
        if b.get("method") != "parts":
            print("sprite_variant: transform-only, nothing to generate"); return
        # parts: render geometry region masks from the base's guide glb +
        # pose spec, so recolor never depends on painted-hue thresholds
        base = comp_dir(b["of"])
        bspec = json.load(open(os.path.join(base, "candidates", "_spec.json")))
        guide = json.load(open(os.path.join(base, "brief.json"))).get("guide_from")
        if not guide:
            sys.exit(f"{cid}: parts masks need base '{b['of']}' to declare guide_from")
        masks = {k: (v["materials"] if isinstance(v, dict) else v)
                 for k, v in b.get("regions", {}).items()}
        spec = dict(bspec, passes=["beauty"], masks=masks)
        render_depths(cdir, guide, spec)
        print("parts masks ->", os.path.join(cand, "_render")); return
    if t == "glb":
        builder = GLB_BUILDERS.get(cid)
        if not builder:
            sys.exit(f"{cid}: no glb builder registered (skeleton/prop tooling is "
                     f"backlog) — mark needs_human or add to GLB_BUILDERS")
        os.makedirs(os.path.join(cdir, "build"), exist_ok=True)
        os.makedirs(os.path.join(cdir, "export"), exist_ok=True)
        out = os.path.join(cdir, "build", f"{cid}.glb")
        spec = GLB_BUILDERS.get(cid) if isinstance(builder, str) else builder
        script = spec["script"] if isinstance(spec, dict) else spec
        extra = spec.get("args", []) if isinstance(spec, dict) else []
        r = subprocess.run([BLENDER, "--background", "--python",
                            os.path.join(ROOT, "tools", script), "--",
                            "--out", out,
                            "--brief", os.path.join(cdir, "brief.json")]
                           + extra, capture_output=True, text=True)
        if r.returncode or not os.path.exists(out):
            sys.exit(f"{cid}: blender builder failed\n{r.stderr[-2000:]}")
        shutil.copyfile(out, os.path.join(cdir, "export", f"{cid}.glb"))
        print("glb built ->", out); return

    prompt, neg = build_prompts(b)
    get("/system_stats")
    idx = Index(cand)

    if t == "sprite":
        guide = b.get("guide_from")
        poses = {}
        for i, p in enumerate(b.get("poses") or ["idle"]):
            name = name_of(p)
            o = p if isinstance(p, dict) else {}
            poses[name] = {"seed": 1000 + i * 100,
                           "bones": POSES.get(name, {}).get("bones", {}),
                           "prompt_extra": o.get("prompt_extra"),
                           "init_from": o.get("init_from"),
                           "denoise": o.get("denoise", 0.55)}
        spec = {"name": cid, "prompt": prompt, "negative": neg,
                "camera": {"ortho_scale": 2.4, "location": [0, -4.2, 1.0], "size": [512, 640]},
                "poses": {n: {"seed": c["seed"], "bones": c["bones"]} for n, c in poses.items()}}
        only = sys.argv[sys.argv.index("--poses") + 1].split(",") if "--poses" in sys.argv else None
        if guide:
            render_depths(cdir, guide, spec)
        w, h = spec["camera"]["size"]
        for pose, pc in poses.items():
            if only and pose not in only:
                continue
            depth_dst = None
            if guide:
                depth_dst = f"{cid}_{pose}_depth.png"
                shutil.copyfile(os.path.join(cand, "_render", f"{pose}_depth.png"),
                                os.path.join(comfy, "input", depth_dst))
            init_dst = None
            if pc["init_from"]:
                init_src = os.path.join(cdir, "accepted", f"{pc['init_from']}.png")
                if not os.path.exists(init_src):
                    sys.exit(f"{cid}/{pose}: init_from '{pc['init_from']}' not accepted yet")
                init_dst = f"{cid}_{pose}_init.png"
                shutil.copyfile(init_src, os.path.join(comfy, "input", init_dst))
            p_full = ", ".join(x for x in (prompt, b["style"]["subject_bg"],
                                           pc["prompt_extra"]) if x)
            # guided i2i: the depth must be able to restructure the init
            # silhouette, so the identity-lock repaint needs a denoise floor
            denoise = (max(pc["denoise"], 0.75) if (guide and init_dst)
                       else pc["denoise"] if init_dst else 1.0)
            tag = "_i2i" if init_dst else ""
            for i in range(seeds_n):
                seed = pc["seed"] + i
                prefix = f"{cid}_{pose}{tag}_s{seed}"
                wf = (wf_sprite(p_full, neg, w, h, seed, prefix, depth_dst,
                                init_dst, denoise)
                      if guide else
                      wf_img2img(p_full, neg, w, h, seed, prefix,
                                 init_dst, denoise))
                run_seed(idx, cand, comfy, wf, "10",
                         {"file": f"{prefix}.png", "pose": pose, "seed": seed,
                          "prompt": p_full, "negative": neg, "w": w, "h": h,
                          "guide": guide,
                          "controlnet": MODELS["controlnets"]["sd15_depth"] if guide else None,
                          "init_from": pc["init_from"],
                          "denoise": denoise})
    else:
        w, h = (512, 512) if t == "ui_image" else (768, 512)
        if t == "ui_image" and b.get("w_px"):
            # honor card aspect (e.g. 340x512 -> 384x512 gen grid, snapped /64)
            w = max(64, int(b["w_px"] / b.get("h_px", 512) * 512 + 31) // 64 * 64)
        extra = b["style"]["subject_bg"] if t == "ui_image" else b["style"]["scene_suffix"]
        p_full = f"{extra}, {prompt}"
        for i in range(seeds_n):
            seed = 5000 + i
            prefix = f"{cid}_s{seed}"
            run_seed(idx, cand, comfy, wf_txt2img(p_full, neg, w, h, seed, prefix), "7",
                     {"file": f"{prefix}.png", "seed": seed, "prompt": p_full,
                      "negative": neg, "w": w, "h": h})

def acquire_locks(cid, locks):
    """Claim the component (+ its guide glb for sprites) before work.
    --goal asserts brief.json ownership; --wait N polls for the lock.
    Appends into the caller's list so a partial acquire is still released."""
    b = json.load(open(os.path.join(comp_dir(cid), "brief.json")))
    goal = sys.argv[sys.argv.index("--goal") + 1] if "--goal" in sys.argv else "manual"
    if goal != "manual" and b.get("goal") not in (None, goal):
        sys.exit(f"{cid}: claimed by goal '{b['goal']}' (this run: '{goal}')")
    wait = int(sys.argv[sys.argv.index("--wait") + 1]) if "--wait" in sys.argv else 0
    deps = {cid}
    if b.get("type") == "sprite" and b.get("guide_from"):
        deps.add(b["guide_from"])  # depth source
    elif b.get("type") == "sprite_variant" and b.get("method") == "parts":
        base_b = json.load(open(os.path.join(comp_dir(b["of"]), "brief.json")))
        deps |= {b["of"], base_b.get("guide_from")}
    deps.discard(None)
    for d in sorted(deps):
        locks.append(FileLock(comp_dir(d) + ".lock",
                              owner=f"{goal}:gen_component", timeout=wait).acquire())

if __name__ == "__main__":
    locks = []
    try:
        acquire_locks(sys.argv[1], locks)
        main()
    except LockHeld as e:
        sys.exit(str(e))
    finally:
        for l in reversed(locks):
            l.release()
