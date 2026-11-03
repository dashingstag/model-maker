"""Drives a running ComfyUI server (127.0.0.1:8188, CPU) via the /prompt API.
Generates the painted textures for the sprites + cutout pipeline approaches.
Stdlib only — run with any python.

Usage: python tools/comfy_gen.py <comfyui_dir> <out_dir>
"""
import json, urllib.request, urllib.parse, time, sys, os, glob, shutil

BASE = "http://127.0.0.1:8188"
CKPT = "v1-5-pruned-emaonly.safetensors"
NEG = ("photorealistic, photo, watermark, text, signature, blurry, deformed, "
       "extra limbs, cropped head, low quality")

JOBS = [
    # (filename_prefix, prompt, seed, w, h)
    ("pirate_char",
     "full body cartoon pirate captain standing, facing viewer, red coat, "
     "tricorn hat, eyepatch, beard, painted game art style, clean silhouette, "
     "isolated on plain solid bright green background, flat even lighting", 11, 512, 512),
    ("pirate_portrait",
     "portrait painting of a pirate captain, tricorn hat, eyepatch, grey beard, "
     "dramatic rim light, painted game art style, bust shot, dark teal background", 22, 512, 512),
    ("bg_sky",
     "painted sunset sky over the sea, orange and purple clouds, distant pirate "
     "ship silhouettes, game background art, no characters, wide view", 33, 512, 512),
    ("bg_deck",
     "pirate ship wooden deck and railings overlooking ocean, painted game "
     "background art, warm dusk light, no characters", 44, 512, 512),
]

def workflow(prefix, prompt, seed, w, h):
    return {"prompt": {
        "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": CKPT}},
        "2": {"class_type": "CLIPTextEncode", "inputs": {"text": prompt, "clip": ["1", 1]}},
        "3": {"class_type": "CLIPTextEncode", "inputs": {"text": NEG, "clip": ["1", 1]}},
        "4": {"class_type": "EmptyLatentImage", "inputs": {"width": w, "height": h, "batch_size": 1}},
        "5": {"class_type": "KSampler", "inputs": {"seed": seed, "steps": 16, "cfg": 7.0,
              "sampler_name": "euler", "scheduler": "normal", "denoise": 1.0,
              "model": ["1", 0], "positive": ["2", 0], "negative": ["3", 0], "latent_image": ["4", 0]}},
        "6": {"class_type": "VAEDecode", "inputs": {"samples": ["5", 0], "vae": ["1", 2]}},
        "7": {"class_type": "SaveImage", "inputs": {"filename_prefix": prefix, "images": ["6", 0]}},
    }}

def post(path, payload):
    req = urllib.request.Request(BASE + path, data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"})
    return json.load(urllib.request.urlopen(req))

def get(path):
    return json.load(urllib.request.urlopen(BASE + path))

def main():
    comfy_dir, out_dir = sys.argv[1], sys.argv[2]
    os.makedirs(out_dir, exist_ok=True)
    gen_dir = os.path.join(comfy_dir, "output")

    try:
        get("/system_stats")
    except Exception as e:
        sys.exit(f"ComfyUI not reachable at {BASE}: {e}")

    for prefix, prompt, seed, w, h in JOBS:
        print(f"[gen] {prefix} ({w}x{h}, seed {seed}) ...", flush=True)
        pid = post("/prompt", workflow(prefix, prompt, seed, w, h))["prompt_id"]
        t0 = time.time()
        while True:
            time.sleep(2)
            hist = get(f"/history/{pid}")
            if pid in hist:
                outs = hist[pid]["outputs"]
                if any(n.get("images") for n in outs.values()):
                    break
            if time.time() - t0 > 900:
                sys.exit(f"timeout waiting for {prefix}")
        fname = outs["7"]["images"][0]["filename"]
        src = os.path.join(gen_dir, outs["7"]["images"][0].get("subfolder", ""), fname)
        dst = os.path.join(out_dir, f"{prefix}.png")
        shutil.copyfile(src, dst)
        print(f"      -> {dst}  ({time.time()-t0:.0f}s)")

if __name__ == "__main__":
    main()
