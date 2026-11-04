"""C1 variant gen — 'controlnet' sprite_variant members via img2img regen.

  python tools/gen_variant.py <variant_cid> --goal G [--wait S] [--seeds N]
                              [--poses p1,p2] [--comfy C:/Workspace/ComfyUI]

Reads pipeline/components/<cid>/brief.json (must be type sprite_variant,
method "controlnet" — palette/parts are transform-only at extract, parts
masks render via gen_component.py). For each member of `variants`:

  sprite base   -> img2img from <of>/accepted/<pose>.png at denoise ~0.45.
                   When the base's depth render survives in
                   <of>/candidates/_render/<pose>_depth.png the same
                   ControlNet-depth guide is re-applied on top (the method
                   namesake: same silhouette, different paint); otherwise
                   falls back to plain img2img and records controlnet:null
                   in the index.
                   -> candidates/<vid>_<pose>_s<seed>.png
  ui_image base -> img2img from <of>/accepted/src.png (roster cards keep a
                   single accepted frame; no depth source exists)
                   -> candidates/<vid>_s<seed>.png

Prompt = base prompt_core + variant prompt_extra (+ base per-pose
prompt_extra) + base must_have + style suffix + palette hints +
subject_bg — the same assembly order as gen_component.build_prompts, with
style/palette taken from the variant brief's own resolved snapshot when
present (identical text in current briefs), falling back to the base's.
Negative = style negative + base neg_extra + base must_not.

Seeds: 1000 + variant_index*100 + j for j < --seeds (default the brief's
`seeds`, else 3). Every candidate is logged to candidates/index.json via
gen_component.Index (atomic_json, resume-aware). Locks: the variant dir
AND the `of` base dir, acquired sorted by path, owner
"<goal>:gen_variant:<cid>", released on exit.
"""
import json, os, shutil, struct, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from gen_component import (ENV, MODELS, comp_dir, get, run_seed, Index,
                           wf_sprite, _ksampler)
from pipelib import FileLock, LockHeld, name_of

DENOISE = 0.45


def _arg(flag, default=None):
    return sys.argv[sys.argv.index(flag) + 1] if flag in sys.argv else default


def png_size(path):
    """(w, h) from the PNG IHDR — no PIL needed under the system python."""
    with open(path, "rb") as f:
        d = f.read(24)
    if d[:8] != b"\x89PNG\r\n\x1a\n":
        sys.exit(f"not a PNG: {path}")
    return struct.unpack(">II", d[16:24])


def wf_img2img(prompt, neg, w, h, seed, prefix, init_img, denoise):
    """Plain img2img (no ControlNet): LoadImage -> scale -> VAEEncode ->
    KSampler(latent). Same topology as gen_component.wf_txt2img."""
    ckpt = MODELS["checkpoints"]["dreamshaper8"]
    ks = _ksampler(seed, ["1", 0], ["2", 0], ["3", 0], ["6", 0])
    ks["inputs"]["denoise"] = denoise
    return {"prompt": {
        "1": {"class_type": "CheckpointLoaderSimple",
              "inputs": {"ckpt_name": ckpt}},
        "2": {"class_type": "CLIPTextEncode",
              "inputs": {"text": prompt, "clip": ["1", 1]}},
        "3": {"class_type": "CLIPTextEncode",
              "inputs": {"text": neg, "clip": ["1", 1]}},
        "4": {"class_type": "LoadImage", "inputs": {"image": init_img}},
        "5": {"class_type": "ImageScale", "inputs": {
              "image": ["4", 0], "upscale_method": "lanczos",
              "width": w, "height": h, "crop": "disabled"}},
        "6": {"class_type": "VAEEncode",
              "inputs": {"pixels": ["5", 0], "vae": ["1", 2]}},
        "7": ks,
        "8": {"class_type": "VAEDecode",
              "inputs": {"samples": ["7", 0], "vae": ["1", 2]}},
        "9": {"class_type": "SaveImage",
              "inputs": {"filename_prefix": prefix, "images": ["8", 0]}},
    }}


def variant_prompts(b, base_b, v, pose_extra=None):
    """base prompt_core + v.prompt_extra (+ pose extra) + must_have +
    style suffix + palette hints + subject_bg; negative = style negative +
    neg_extra + must_not. Style/palette resolve from the variant brief's
    snapshot first, then the base's. v.prompt_override replaces the base
    prompt_core for repaint variants where the base's own color vocabulary
    would anchor the wrong palette."""
    style = b.get("style") or base_b.get("style") or {}
    palette = b.get("palette") or base_b.get("palette") or {}
    parts = [v.get("prompt_override") or base_b.get("prompt_core"),
             v.get("prompt_extra"), pose_extra,
             ", ".join(base_b.get("must_have", [])),
             style.get("suffix"), palette.get("prompt_hints"),
             style.get("subject_bg")]
    neg = [style.get("negative"), base_b.get("neg_extra"),
           ", ".join(base_b.get("must_not", []))]
    return (", ".join(p for p in parts if p),
            ", ".join(n for n in neg if n))


def main(cid):
    cdir = comp_dir(cid)
    bpath = os.path.join(cdir, "brief.json")
    if not os.path.exists(bpath):
        sys.exit(f"{cid}: no brief.json at {bpath}")
    b = json.load(open(bpath))
    if b.get("type") != "sprite_variant":
        sys.exit(f"{cid}: type is '{b.get('type')}', not 'sprite_variant' — "
                 "gen_variant only generates variant members")
    method = b.get("method")
    if method != "controlnet":
        why = {"parts": "region masks render via gen_component.py "
                        "(transform itself happens at extract)",
               "palette": "transform-only — handled by extract.py",
               "modulate": "runtime tint — nothing to generate"}.get(
            method, "no generator registered for this method")
        sys.exit(f"{cid}: method is '{method}' — {why}; "
                 "gen_variant only runs method 'controlnet'")
    base_id = b.get("of")
    if not base_id:
        sys.exit(f"{cid}: brief has no 'of' — controlnet variants need a "
                 "base component to regen from")
    bdir = comp_dir(base_id)
    bbpath = os.path.join(bdir, "brief.json")
    if not os.path.exists(bbpath):
        sys.exit(f"{cid}: base '{base_id}' has no brief.json at {bbpath}")
    base_b = json.load(open(bbpath))
    base_type = base_b.get("type")
    if base_type not in ("sprite", "ui_image"):
        sys.exit(f"{cid}: controlnet variants of '{base_type}' bases "
                 f"({base_id}) are unsupported — need sprite or ui_image")

    variants = b.get("variants") or [
        {"id": f"{cid}_{i + 1:02d}"} for i in range(int(b.get("count", 0)))]
    if not variants:
        sys.exit(f"{cid}: brief declares no variants (empty 'variants' "
                 "and no 'count')")

    seeds_n = int(_arg("--seeds") or b.get("seeds", 3))
    comfy = _arg("--comfy", ENV["comfyui_dir"])
    only = _arg("--poses").split(",") if "--poses" in sys.argv else None
    cand = os.path.join(cdir, "candidates")
    os.makedirs(cand, exist_ok=True)
    accdir = os.path.join(bdir, "accepted")

    # --- resolve base inputs up front: fail before touching ComfyUI ----
    poses, pose_extras = [], {}
    if base_type == "sprite":
        declared = [name_of(p) for p in base_b.get("poses", [])]
        accepted = ({os.path.splitext(f)[0]
                     for f in os.listdir(accdir) if f.endswith(".png")}
                    if os.path.isdir(accdir) else set())
        if only:
            bad = [p for p in only if p not in accepted]
            if bad:
                sys.exit(f"{cid}: base '{base_id}' has no accepted art for "
                         f"poses {bad} — expected "
                         f"{accdir}/<pose>.png (curate {base_id} first)")
        pool = declared or sorted(accepted)
        poses = [p for p in pool if p in accepted]
        skipped = [p for p in pool if p not in accepted]
        if not poses:
            sys.exit(f"{cid}: base '{base_id}' has no accepted sprite art "
                     f"— expected {accdir}/<pose>.png for poses "
                     f"{pool or '(none declared)'}; curate {base_id} "
                     "candidates into accepted/ first")
        if skipped:
            print(f"{cid}: base poses not yet accepted, skipped: {skipped}")
        for p in base_b.get("poses", []):
            if isinstance(p, dict):
                pose_extras[name_of(p)] = p.get("prompt_extra")
        jobs = [(v, pose) for v in variants for pose in poses]
    else:
        src = os.path.join(accdir, "src.png")
        if not os.path.exists(src):
            sys.exit(f"{cid}: base '{base_id}' has no accepted art — "
                     f"expected {src} (curate {base_id} candidates into "
                     "accepted/src.png first)")
        jobs = [(v, None) for v in variants]

    try:
        get("/system_stats")
    except Exception as e:
        sys.exit(f"{cid}: ComfyUI unreachable at {ENV['comfyui_url']} "
                 f"({e}) — is the server running?")

    idx = Index(cand)
    vidx_of = {v["id"]: i for i, v in enumerate(variants)}
    for v, pose in jobs:
        vid = v["id"]
        den = float(v.get("denoise", b.get("denoise", DENOISE)))
        init_src = (src if pose is None
                    else os.path.join(accdir, f"{pose}.png"))
        w, h = png_size(init_src)
        tag_in = f"{cid}_{vid}_{pose}" if pose else f"{cid}_{vid}"
        init_name = f"{tag_in}_init.png"
        shutil.copyfile(init_src, os.path.join(comfy, "input", init_name))
        depth_name = depth_src = None
        if pose:
            d = os.path.join(bdir, "candidates", "_render",
                             f"{pose}_depth.png")
            if os.path.exists(d):
                depth_src, depth_name = d, f"{tag_in}_depth.png"
                shutil.copyfile(d, os.path.join(comfy, "input",
                                                depth_name))
        pos, neg = variant_prompts(b, base_b, v, pose_extras.get(pose))
        for j in range(seeds_n):
            seed = 1000 + vidx_of[vid] * 100 + j
            prefix = f"{tag_in}_s{seed}"
            if depth_name:
                wf = wf_sprite(pos, neg, w, h, seed, prefix, depth_name,
                               init_name, den)
                out_node, cn = "10", MODELS["controlnets"]["sd15_depth"]
            else:
                wf = wf_img2img(pos, neg, w, h, seed, prefix, init_name, den)
                out_node, cn = "9", None
            run_seed(idx, cand, comfy, wf, out_node,
                     {"file": f"{prefix}.png", "variant": vid, "pose": pose,
                      "seed": seed, "prompt": pos, "negative": neg,
                      "w": w, "h": h, "of": base_id,
                      "init_from": os.path.relpath(init_src, bdir)
                      .replace("\\", "/"),
                      "denoise": den, "controlnet": cn,
                      "depth": (os.path.relpath(depth_src, bdir)
                                .replace("\\", "/")
                                if depth_src else None)})


def acquire_locks(cid, locks):
    """Claim the variant component AND its `of` base (reads accepted/),
    sorted by path like the other stage tools. --goal asserts brief
    ownership; --wait N polls instead of failing fast."""
    cdir = comp_dir(cid)
    bpath = os.path.join(cdir, "brief.json")
    if not os.path.exists(bpath):
        sys.exit(f"{cid}: no brief.json at {bpath}")
    b = json.load(open(bpath))
    goal = _arg("--goal", "manual")
    if goal != "manual" and b.get("goal") not in (None, goal):
        sys.exit(f"{cid}: claimed by goal '{b['goal']}' (this run: '{goal}')")
    wait = int(_arg("--wait", 0))
    paths = {cdir + ".lock"}
    if b.get("of"):
        paths.add(comp_dir(b["of"]) + ".lock")
    for p in sorted(paths):
        locks.append(FileLock(p, owner=f"{goal}:gen_variant:{cid}",
                              timeout=wait).acquire())


if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1].startswith("--"):
        sys.exit(__doc__)
    locks = []
    try:
        acquire_locks(sys.argv[1], locks)
        main(sys.argv[1])
    except LockHeld as e:
        sys.exit(str(e))
    finally:
        for l in reversed(locks):
            l.release()
