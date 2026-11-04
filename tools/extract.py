"""C2 Extract/build — accepted/ -> processed/ + manifest.json.

  venv-python tools/extract.py <component_id> [--goal G] [--wait S]

Per type:
  sprite         : accepted/<pose>.png (RGB w/ bg) -> rembg BiRefNet matte ->
                   despill+erode+tight crop -> processed/sprite_<pose>.png
                   (+ _n normal from _render)
  sprite_variant : recolor the base's processed sprites per brief `variants`
                   (targets are @palettes refs). method "parts" uses geometry
                   region masks rendered at C1 (candidates/_render/
                   <pose>_mask_<region>.png); method "palette" falls back to
                   a hue-threshold mask (fragile on painterly art).
  ui_image       : cover-crop to w_px x h_px (square fallback) -> processed/portrait.png
  parallax       : copy -> processed/bg.png (manifest carries factor)
  glb            : validate export/<id>.glb vs tri_budget -> manifest

Re-running on a component with a manifest archives the previous processed/
+ manifest to history/rev<n>/ and bumps rev.
"""
import hashlib, json, os, shutil, struct, sys, time
import numpy as np
from PIL import Image, ImageFilter
from pipelib import FileLock, LockHeld, atomic_json, name_of, resolve_ref

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODELS = json.load(open(os.path.join(ROOT, "models.json")))
ENV = json.load(open(os.path.join(ROOT, "tools", "env.json")))
CONSTRAINT_KEYS = ("type", "h_px", "pivot", "anims", "poses", "tri_budget",
                   "factor", "collision", "method", "of", "vary", "variants",
                   "count", "skeleton", "attachments", "prop", "guide_from")
FRINGE_RATIO_MAX = 0.02

_session = None
def matte(img):
    """BiRefNet matting -> RGBA (rembg session, lazily built)."""
    global _session
    if _session is None:
        # onnxruntime loads cudnn64_9.dll by name via the process PATH; torch
        # ships it but doesn't register its lib dir -> prepend before import
        torch_lib = os.path.join(sys.prefix, "Lib", "site-packages",
                                 "torch", "lib")
        if os.path.isdir(torch_lib) and torch_lib not in os.environ["PATH"]:
            os.environ["PATH"] = torch_lib + os.pathsep + os.environ["PATH"]
        from rembg import new_session
        _session = new_session(MODELS["matting"]["birefnet"])
    from rembg import remove
    return remove(img, session=_session)

def sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return "sha256:" + h.hexdigest()

def fringe_ratio(img):
    """Fraction of the soft-alpha band with green spill (WORKFLOW C2)."""
    a = np.asarray(img).astype(np.float32)
    band = (a[..., 3] > 0) & (a[..., 3] < 255)
    n = int(band.sum())
    if not n:
        return 0.0
    spill = (a[..., 1] - np.maximum(a[..., 0], a[..., 2]) > 20) & band
    return round(float(spill.sum()) / n, 5)

def despill_erode(img):
    """Clamp green spill on edge px, soft-erode alpha; returns (img, px, ratio)."""
    a = np.asarray(img).astype(np.float32)
    r, g, b, al = a[..., 0], a[..., 1], a[..., 2], a[..., 3]
    edge = (al > 0) & (al < 255)
    spill = (g > np.maximum(r, b) * 1.1) & edge
    g[spill] = np.maximum(r, b)[spill] * 1.05
    a[..., 1] = g
    al_new = np.asarray(
        Image.fromarray(al.astype(np.uint8)).filter(ImageFilter.MinFilter(3)),
        dtype=np.float32)
    a[..., 3] = np.where(edge, np.minimum(al, al_new + 30), al_new)
    out = Image.fromarray(a.astype(np.uint8), "RGBA")
    fa = np.asarray(out).astype(np.float32)
    tr = (fa[..., 3] > 8) & (fa[..., 3] < 128)
    px = int(((fa[..., 1] > fa[..., 0] * 1.1) & (fa[..., 1] > fa[..., 2] * 1.1) & tr).sum())
    return out, px, fringe_ratio(out)

def tight_crop(img, pad=2):
    bb = img.getbbox()
    if not bb: return img
    return img.crop((max(0, bb[0]-pad), max(0, bb[1]-pad),
                     min(img.width, bb[2]+pad), min(img.height, bb[3]+pad)))

def cover_crop(img, tw, th):
    """Center-biased cover-crop to the target aspect, then resize."""
    ta = tw / th
    if img.width / img.height > ta:
        nw = int(img.height * ta)
        img = img.crop(((img.width - nw) // 2, 0, (img.width + nw) // 2, img.height))
    else:
        nh = int(img.width / ta)
        img = img.crop((0, (img.height - nh) // 2, img.width, (img.height + nh) // 2))
    return img.resize((tw, th), Image.LANCZOS)

def align_to_sprite(render_png, beauty_png, size):
    """Crop a _render pass to the beauty alpha bbox, resize to the sprite."""
    beauty = Image.open(beauty_png).convert("RGBA")
    bb = beauty.split()[3].getbbox()
    return Image.open(render_png).crop(bb).resize(size, Image.LANCZOS)

def hex_rgb(h):
    h = h.lstrip("#")
    return np.array([int(h[i:i+2], 16) for i in (0, 2, 4)], np.float32)

def recolor(a, mask, target):
    """Shading-preserving recolor: target * (luma / mean masked luma)."""
    if mask.sum() < 1:
        return a
    luma = a[..., :3] @ np.array([0.299, 0.587, 0.114], np.float32)
    m = mask > 0.5
    ref = max(float(luma[m].mean()), 1.0)
    shade = (luma / ref)[..., None] * target
    out = a.copy()
    k = mask[..., None]
    out[..., :3] = np.clip(a[..., :3] * (1 - k) + shade * k, 0, 255)
    return out

def hsv_arrays(a):
    rgb = a[..., :3]
    mx = rgb.max(-1); mn = rgb.min(-1)
    d = np.maximum(mx - mn, 1)
    sat = np.where(mx > 0.01, (mx - mn) / np.maximum(mx, 1), 0)
    r_, g_, b_ = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    hue = np.zeros_like(sat)
    m_r = mx == r_; m_g = (mx == g_) & ~m_r; m_b = ~(m_r | m_g)
    hue[m_r] = ((g_ - b_)[m_r] / d[m_r]) % 6
    hue[m_g] = (b_ - r_)[m_g] / d[m_g] + 2
    hue[m_b] = (r_ - g_)[m_b] / d[m_b] + 4
    return hue / 6.0, sat, mx

def color_gate(a, spec):
    """Region color gate {hue:[lo,hi] (wraps), min_sat, min_val} -> 0/1."""
    hue, sat, val = hsv_arrays(a)
    g = np.ones(hue.shape, np.float32)
    if "hue" in spec:
        lo, hi = spec["hue"]
        g *= ((hue >= lo) | (hue <= hi)) if lo > hi else ((hue >= lo) & (hue <= hi))
    g *= sat >= spec.get("min_sat", 0)
    g *= val >= spec.get("min_val", 0)
    return g.astype(np.float32)

def hue_mask(a):
    """Legacy 'palette' method mask: saturated red hues (coat)."""
    rgb = a[..., :3]
    mx = rgb.max(-1); mn = rgb.min(-1)
    d = np.maximum(mx - mn, 1)
    sat = np.where(mx > 0.01, (mx - mn) / np.maximum(mx, 1), 0)
    r_, g_, b_ = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    hue = np.zeros_like(sat)
    m_r = mx == r_; m_g = (mx == g_) & ~m_r; m_b = ~(m_r | m_g)
    hue[m_r] = ((g_ - b_)[m_r] / d[m_r]) % 6
    hue[m_g] = (b_ - r_)[m_g] / d[m_g] + 2
    hue[m_b] = (r_ - g_)[m_b] / d[m_b] + 4
    hue /= 6.0
    return ((hue >= 0.90) & (sat > 0.4) & (mx < 200)).astype(np.float32)

def load(cdir, *p):
    return Image.open(os.path.join(cdir, *p)).convert("RGBA")

def archive_previous(cdir):
    """Move the prior rev's processed/ + manifest into history/rev<n>/."""
    mpath = os.path.join(cdir, "manifest.json")
    if not os.path.exists(mpath):
        return 1, []
    old = json.load(open(mpath))
    rev = int(old.get("rev", 1))
    hdir = os.path.join(cdir, "history", f"rev{rev}")
    os.makedirs(hdir, exist_ok=True)
    proc = os.path.join(cdir, "processed")
    if os.path.isdir(proc):
        shutil.move(proc, os.path.join(hdir, "processed"))
    shutil.copyfile(mpath, os.path.join(hdir, "manifest.json"))
    hist = old.get("history", []) + [{"rev": rev, "ts": time.time(),
                                      "status": old.get("status")}]
    return rev + 1, hist

def main(cid):
    cdir = os.path.join(ROOT, "pipeline", "components", cid)
    b = json.load(open(os.path.join(cdir, "brief.json")))
    t = b["type"]
    rev, history = archive_previous(cdir)
    proc = os.path.join(cdir, "processed")
    os.makedirs(proc, exist_ok=True)
    manifest = {"schema_v": 1, "id": cid, "type": t, "status": "processed",
                "rev": rev,
                "constraints": {k: b[k] for k in CONSTRAINT_KEYS if k in b},
                "inputs": {}, "artifacts": {}, "metrics": {},
                "gate_mode": {}, "waiver": None, "history": history,
                "toolchain": {k: ENV.get("versions", {}).get(k)
                              for k in ("blender", "comfyui", "comfyui_device")}}
    manifest["toolchain"]["matting"] = MODELS["matting"].get("birefnet")

    if t == "sprite":
        manifest["pivot"] = b.get("pivot", "feet")
        manifest["h_px"] = b.get("h_px")
        manifest["poses"] = [name_of(p) for p in (b.get("poses") or ["idle"])]
        fringes, ratios = {}, {}
        for pose in manifest["poses"]:
            src = os.path.join(cdir, "accepted", f"{pose}.png")
            manifest["inputs"][f"accepted/{pose}.png"] = sha(src)
            img, px, ratio = despill_erode(tight_crop(matte(load(cdir, "accepted", f"{pose}.png"))))
            img.save(os.path.join(proc, f"sprite_{pose}.png"))
            fringes[pose], ratios[pose] = px, ratio
            rdir = os.path.join(cdir, "candidates", "_render")
            nrm_p = os.path.join(rdir, f"{pose}_normal.png")
            if os.path.exists(nrm_p):
                n = align_to_sprite(nrm_p, os.path.join(rdir, f"{pose}_beauty.png"),
                                    img.size).convert("RGB")
                n.putalpha(img.split()[3])
                n.save(os.path.join(proc, f"sprite_{pose}_n.png"))
        manifest["fringe_px"] = fringes
        manifest["metrics"]["fringe_ratio"] = ratios
        manifest["collider"] = "alpha-bounds-10pct"
        manifest["gate"] = {"fringe_ok": all(v <= FRINGE_RATIO_MAX for v in ratios.values())}
        manifest["gate_mode"]["fringe_ok"] = "enforced"

    elif t == "sprite_variant":
        base_id = b["of"]
        bdir = os.path.join(ROOT, "pipeline", "components", base_id)
        srcdir = os.path.join(bdir, "processed")
        bman_path = os.path.join(bdir, "manifest.json")
        if not os.path.exists(bman_path):
            sys.exit(f"{cid}: base '{base_id}' has no manifest.json — run "
                     f"extract.py {base_id} first")
        base_man = json.load(open(bman_path))
        manifest["inputs"][f"{base_id}/manifest.json"] = sha(bman_path)
        poses = base_man.get("poses") or [
            f[len("sprite_"):-4] for f in sorted(os.listdir(srcdir))
            if f.startswith("sprite_") and not f.endswith("_n.png")]
        method = b.get("method", "palette")
        variants = b.get("variants") or [{"id": f"{cid}_{i+1:02d}"}
                                         for i in range(int(b.get("count", 0)))]
        mdir = os.path.join(cdir, "candidates", "_render")
        manifest.update({"of": base_id, "method": method, "variants": [],
                         "targets": {}})
        if method == "controlnet":
            # regenerated art, not a recolor: the variant's own accepted/
            # holds one curated pick per member — accepted/<vid>_<pose>.png
            # for sprite bases, accepted/<vid>.png for ui_image bases —
            # which then runs the same post the type's own art would.
            bb = json.load(open(os.path.join(bdir, "brief.json")))
            base_type = bb.get("type", "sprite")
            if base_type not in ("sprite", "ui_image"):
                sys.exit(f"{cid}: controlnet variants of '{base_type}' bases "
                         f"({base_id}) are unsupported")
            tw = bb.get("w_px") or bb.get("h_px") or b.get("w_px") \
                or b.get("h_px") or 256
            th = bb.get("h_px") or b.get("h_px") or 256
            fringes, ratios = {}, {}
            for v in variants:
                vid = v["id"]
                manifest["targets"][vid] = {
                    r: resolve_ref(ROOT, v[r])
                    if str(v[r]).startswith("@") else v[r]
                    for r in b.get("vary", []) if r in v}
                outdir = os.path.join(proc, vid)
                os.makedirs(outdir, exist_ok=True)
                if base_type == "ui_image":
                    apath = f"accepted/{vid}.png"
                    src = os.path.join(cdir, "accepted", f"{vid}.png")
                    if not os.path.exists(src):
                        sys.exit(f"{cid}: missing {apath} — curate a "
                                 f"gen_variant candidate for variant '{vid}' "
                                 "into accepted/ first")
                    manifest["inputs"][apath] = sha(src)
                    cover_crop(Image.open(src).convert("RGB"), tw, th).save(
                        os.path.join(outdir, "portrait.png"))
                else:
                    for pose in poses:
                        sp = os.path.join(srcdir, f"sprite_{pose}.png")
                        if not os.path.exists(sp):
                            continue
                        apath = f"accepted/{vid}_{pose}.png"
                        src = os.path.join(cdir, "accepted",
                                           f"{vid}_{pose}.png")
                        if not os.path.exists(src):
                            sys.exit(f"{cid}: missing {apath} — curate a "
                                     f"gen_variant candidate for variant "
                                     f"'{vid}' pose '{pose}' first")
                        manifest["inputs"][apath] = sha(src)
                        img, px, ratio = despill_erode(tight_crop(matte(
                            load(cdir, "accepted", f"{vid}_{pose}.png"))))
                        img.save(os.path.join(outdir, f"sprite_{pose}.png"))
                        fringes[f"{vid}/{pose}"] = px
                        ratios[f"{vid}/{pose}"] = ratio
                        np_ = os.path.join(srcdir, f"sprite_{pose}_n.png")
                        if os.path.exists(np_):
                            shutil.copyfile(np_, os.path.join(
                                outdir, f"sprite_{pose}_n.png"))
                manifest["variants"].append(vid)
            if base_type == "sprite":
                manifest["fringe_px"] = fringes
                manifest["metrics"]["fringe_ratio"] = ratios
                manifest["gate"] = {"fringe_ok": all(
                    r <= FRINGE_RATIO_MAX for r in ratios.values())}
                manifest["gate_mode"]["fringe_ok"] = "enforced"
        else:
            coverage = {}
            for v in variants:
                vid = v["id"]
                targets = {r: resolve_ref(ROOT, v[r]) if str(v[r]).startswith("@") else v[r]
                           for r in b.get("vary", []) if r in v}
                manifest["targets"][vid] = targets
                outdir = os.path.join(proc, vid)
                os.makedirs(outdir, exist_ok=True)
                for pose in poses:
                    sp = os.path.join(srcdir, f"sprite_{pose}.png")
                    if not os.path.exists(sp):
                        continue
                    img = Image.open(sp).convert("RGBA")
                    a = np.asarray(img).astype(np.float32)
                    alpha = (a[..., 3] > 128).astype(np.float32)
                    def geom(region):
                        mp = os.path.join(mdir, f"{pose}_mask_{region}.png")
                        if not os.path.exists(mp):
                            sys.exit(f"{cid}: missing {mp} — run gen_component {cid} first")
                        return np.asarray(align_to_sprite(
                            mp, os.path.join(mdir, f"{pose}_beauty.png"), img.size)
                            .convert("L"), np.float32) / 255.0
                    for region, hexcol in targets.items():
                        if method == "parts":
                            rspec = b.get("regions", {}).get(region, {})
                            rspec = rspec if isinstance(rspec, dict) else {}
                            # geometry says WHERE the region can be; the color
                            # gate rejects painted pixels that aren't region
                            # paint (skin-toned hands under sleeve geometry)
                            mk = geom(region) * color_gate(a, rspec)
                            if rspec.get("clip_below"):
                                rows = np.where(geom(rspec["clip_below"]).max(1) > 0.5)[0]
                                if rows.size:
                                    mk[rows.min():, :] = 0
                            mk = np.asarray(Image.fromarray((mk * 255).astype(np.uint8))
                                            .filter(ImageFilter.GaussianBlur(1.2)),
                                            np.float32) / 255.0
                        elif region == "coat":
                            mk = hue_mask(a)
                        else:
                            continue  # palette method only knows the coat
                        mk = mk * alpha
                        coverage[f"{vid}/{pose}/{region}"] = round(float(mk.sum() / max(alpha.sum(), 1)), 4)
                        a = recolor(a, mk, hex_rgb(hexcol))
                    Image.fromarray(a.astype(np.uint8), "RGBA").save(
                        os.path.join(outdir, f"sprite_{pose}.png"))
                    np_ = os.path.join(srcdir, f"sprite_{pose}_n.png")
                    if os.path.exists(np_):
                        shutil.copyfile(np_, os.path.join(outdir, f"sprite_{pose}_n.png"))
                manifest["variants"].append(vid)
            manifest["metrics"]["region_coverage"] = coverage
        manifest["poses"] = poses

    elif t == "ui_image":
        src = os.path.join(cdir, "accepted", "src.png")
        manifest["inputs"]["accepted/src.png"] = sha(src)
        img = Image.open(src).convert("RGB")
        tw, th = b.get("w_px", b.get("h_px", 256)), b.get("h_px", 256)
        # cover-crop to the target aspect, then resize (center-biased)
        cover_crop(img, tw, th).save(os.path.join(proc, "portrait.png"))

    elif t == "parallax":
        src = os.path.join(cdir, "accepted", "src.png")
        manifest["inputs"]["accepted/src.png"] = sha(src)
        shutil.copyfile(src, os.path.join(proc, "bg.png"))
        manifest["factor"] = b.get("factor")
        manifest["min_visible_pct"] = b.get("min_visible_pct")

    elif t == "glb":
        src = next((os.path.join(cdir, "export", n) for n in (f"{cid}.glb", "pirate.glb")
                    if os.path.exists(os.path.join(cdir, "export", n))), None)
        if not src:
            sys.exit(f"{cid}: no export/{cid}.glb — run gen_component first")
        manifest["inputs"][f"export/{os.path.basename(src)}"] = sha(src)
        manifest["glb"] = os.path.basename(src)
        shutil.copyfile(src, os.path.join(proc, manifest["glb"]))
        d = open(src, "rb").read()
        clen, _ = struct.unpack("<II", d[12:20])
        j = json.loads(d[20:20+clen])
        tris = sum(j["accessors"][p["indices"]]["count"] // 3
                   for m in j["meshes"] for p in m["primitives"] if "indices" in p)
        manifest.update({"meshes": len(j["meshes"]), "tris": tris,
                         "animations": [a["name"] for a in j.get("animations", [])],
                         "tri_budget": b.get("tri_budget"),
                         "gate": {"tris_ok": tris <= b.get("tri_budget", 1e9)}})
        manifest["gate_mode"]["tris_ok"] = "enforced"

    for dp, _, files in os.walk(proc):
        for f in files:
            p = os.path.join(dp, f)
            manifest["artifacts"][os.path.relpath(p, cdir).replace("\\", "/")] = sha(p)
    atomic_json(os.path.join(cdir, "manifest.json"), manifest)
    print(json.dumps({k: manifest[k] for k in ("id", "type", "status", "rev")}),
          json.dumps(manifest.get("gate", {})), json.dumps(manifest["metrics"])[:600])

def acquire_locks(cid, locks):
    """Claim the component (+ its `of` base for variants) before work."""
    cdir = os.path.join(ROOT, "pipeline", "components", cid)
    b = json.load(open(os.path.join(cdir, "brief.json")))
    goal = sys.argv[sys.argv.index("--goal") + 1] if "--goal" in sys.argv else "manual"
    if goal != "manual" and b.get("goal") not in (None, goal):
        sys.exit(f"{cid}: claimed by goal '{b['goal']}' (this run: '{goal}')")
    wait = int(sys.argv[sys.argv.index("--wait") + 1]) if "--wait" in sys.argv else 0
    for d in sorted({cid, b.get("of") or cid}):
        locks.append(FileLock(
            os.path.join(ROOT, "pipeline", "components", d + ".lock"),
            owner=f"{goal}:extract", timeout=wait).acquire())

if __name__ == "__main__":
    locks = []
    try:
        acquire_locks(sys.argv[1], locks)
        main(sys.argv[1])
    except LockHeld as e:
        sys.exit(str(e))
    finally:
        for l in reversed(locks):
            l.release()
