"""Hybrid pipeline stage 2: paint each Blender depth render through
ControlNet-depth (DreamShaper), then real alpha via BiRefNet — no green screen.

Prereq: ComfyUI server running WITHOUT --disable-all-custom-nodes.
Usage: python tools/hybrid_gen.py <comfyui_dir> <spec.json> <renders_dir> <out_dir>
"""
import json, urllib.request, time, sys, os, shutil

BASE = "http://127.0.0.1:8188"

def post(path, payload):
    req = urllib.request.Request(BASE + path, data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"})
    return json.load(urllib.request.urlopen(req))

def get(path):
    return json.load(urllib.request.urlopen(BASE + path))

def workflow(pose, spec, depth_img, seed):
    return {"prompt": {
        "1": {"class_type": "CheckpointLoaderSimple",
              "inputs": {"ckpt_name": "DreamShaper_8_pruned.safetensors"}},
        "2": {"class_type": "CLIPTextEncode", "inputs": {"text": spec["prompt"], "clip": ["1", 1]}},
        "3": {"class_type": "CLIPTextEncode", "inputs": {"text": spec["negative"], "clip": ["1", 1]}},
        "4": {"class_type": "ControlNetLoader",
              "inputs": {"control_net_name": "control_v11f1p_sd15_depth_fp16.safetensors"}},
        "5": {"class_type": "LoadImage", "inputs": {"image": depth_img}},
        "6": {"class_type": "ControlNetApply",
              "inputs": {"conditioning": ["2", 0], "control_net": ["4", 0],
                         "image": ["5", 0], "strength": 0.85}},
        "7": {"class_type": "EmptyLatentImage",
              "inputs": {"width": spec["camera"]["size"][0],
                         "height": spec["camera"]["size"][1], "batch_size": 1}},
        "8": {"class_type": "KSampler",
              "inputs": {"seed": seed, "steps": 28, "cfg": 7.0,
                         "sampler_name": "dpmpp_2m_sde", "scheduler": "karras",
                         "denoise": 1.0, "model": ["1", 0],
                         "positive": ["6", 0], "negative": ["3", 0],
                         "latent_image": ["7", 0]}},
        "9": {"class_type": "VAEDecode", "inputs": {"samples": ["8", 0], "vae": ["1", 2]}},
        "10": {"class_type": "BiRefNet_ModelLoader_Zho",
               "inputs": {"birefnet_model": "birefnet_general.pth"}},
        "11": {"class_type": "BiRefNet_Zho",
               "inputs": {"birefnetmodel": ["10", 0], "image": ["9", 0]}},
        "12": {"class_type": "SaveImage",
               "inputs": {"filename_prefix": f"painted_{pose}", "images": ["11", 0]}},
    }}

def main():
    comfy_dir, spec_path, renders, out_dir = sys.argv[1:5]
    spec = json.load(open(spec_path))
    os.makedirs(out_dir, exist_ok=True)
    input_dir = os.path.join(comfy_dir, "input")
    output_dir = os.path.join(comfy_dir, "output")
    get("/system_stats")  # fail fast

    for pose, cfg in spec["poses"].items():
        depth_src = os.path.join(renders, f"{pose}_depth.png")
        depth_dst = os.path.join(input_dir, f"{spec['name']}_{pose}_depth.png")
        shutil.copyfile(depth_src, depth_dst)
        print(f"[gen] {pose} (seed {cfg['seed']}) ...", flush=True)
        pid = post("/prompt", workflow(pose, spec, os.path.basename(depth_dst),
                                     cfg["seed"]))["prompt_id"]
        t0 = time.time()
        while True:
            time.sleep(1.5)
            hist = get(f"/history/{pid}")
            if pid in hist and any(n.get("images") for n in hist[pid]["outputs"].values()):
                break
            if time.time() - t0 > 600:
                sys.exit(f"timeout on {pose}")
        img = hist[pid]["outputs"]["12"]["images"][0]
        src = os.path.join(output_dir, img.get("subfolder", ""), img["filename"])
        dst = os.path.join(out_dir, f"{pose}.png")
        shutil.copyfile(src, dst)
        print(f"      -> {dst} ({time.time()-t0:.0f}s)")

if __name__ == "__main__":
    main()
