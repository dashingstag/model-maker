"""C2 Extract/build — accepted/ -> processed/ + manifest.json.

  venv-python tools/extract.py <component_id>

Per type:
  sprite         : accepted/<pose>.png (RGB w/ bg) -> rembg BiRefNet matte ->
                   despill+erode+tight crop -> processed/sprite_<pose>.png
                   (+ _n normal from _render)
  sprite_variant : palette-shift of base's processed sprite per vary rules
  ui_image       : center-crop -> processed/<id>.png
  parallax       : copy -> processed/bg.png (manifest carries factor)
  glb            : validate export/pirate.glb vs tri_budget -> manifest
"""
import json, os, sys
import numpy as np
from PIL import Image, ImageFilter
from scipy import ndimage
import colorsys
from pipelib import FileLock, LockHeld, atomic_json

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODELS = json.load(open(os.path.join(ROOT, "models.json")))

_session = None
def matte(img):
    """BiRefNet matting -> RGBA (rembg session, lazily built)."""
    global _session
    if _session is None:
        from rembg import new_session
        _session = new_session(MODELS["matting"]["birefnet"])
    from rembg import remove
    return remove(img, session=_session)

def despill_erode(img):
    """Clamp green spill on edge px, erode alpha 1px -> halo metric."""
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
    # residual fringe metric: translucent px with green-cyan hue
    fa = np.asarray(out).astype(np.float32)
    tr = (fa[..., 3] > 8) & (fa[..., 3] < 128)
    fringe = int(((fa[..., 1] > fa[..., 0] * 1.1) & (fa[..., 1] > fa[..., 2] * 1.1) & tr).sum())
    return out, fringe

def tight_crop(img, pad=2):
    bb = img.getbbox()
    if not bb: return img
    return img.crop((max(0, bb[0]-pad), max(0, bb[1]-pad),
                     min(img.width, bb[2]+pad), min(img.height, bb[3]+pad)))

def load(cdir, *p):
    return Image.open(os.path.join(cdir, *p)).convert("RGBA")

def main(cid):
    cdir = os.path.join(ROOT, "pipeline", "components", cid)
    b = json.load(open(os.path.join(cdir, "brief.json")))
    proc = os.path.join(cdir, "processed")
    os.makedirs(proc, exist_ok=True)
    t = b["type"]
    manifest = {"id": cid, "type": t, "status": "processed", "rev": 1}

    if t == "sprite":
        fringes = {}
        manifest["pivot"] = b.get("pivot", "feet")
        manifest["h_px"] = b.get("h_px")
        for pose in b["poses"]:
            img, fr = despill_erode(tight_crop(matte(load(cdir, "accepted", f"{pose}.png"))))
            img.save(os.path.join(proc, f"sprite_{pose}.png"))
            fringes[pose] = fr
            nrm_p = os.path.join(cdir, "candidates", "_render", f"{pose}_normal.png")
            if os.path.exists(nrm_p):
                nrm = Image.open(nrm_p).convert("RGB")
                beauty = Image.open(os.path.join(cdir, "candidates", "_render",
                                    f"{pose}_beauty.png")).convert("RGBA")
                bb = beauty.split()[3].getbbox()
                n = nrm.crop(bb).resize(img.size, Image.LANCZOS)
                n.putalpha(img.split()[3])
                n.save(os.path.join(proc, f"sprite_{pose}_n.png"))
        manifest["fringe_px"] = fringes
        manifest["collider"] = "alpha-bounds-10pct"
        manifest["gate"] = {"fringe_ok": all(v < 50 for v in fringes.values())}

    elif t == "sprite_variant":
        base_id = b["of"]
        srcdir = os.path.join(ROOT, "pipeline", "components", base_id, "processed")
        count = int(b.get("count", 5))
        hues = [0.5, 0.62, 0.08, 0.78, 0.35]          # crew coat hues
        trims = [(1,1,1), (0.9,0.85,0.6), (0.7,0.8,1), (1,0.8,0.7), (0.8,1,0.8)]
        manifest["variants"] = []
        for i in range(count):
            for pose in ("idle", "walk_a", "walk_b"):
                sp = os.path.join(srcdir, f"sprite_{pose}.png")
                if not os.path.exists(sp): continue
                img = Image.open(sp).convert("RGBA")
                a = np.asarray(img).astype(np.float32)
                # shift red-dominant coat px toward crew hue, keep others
                # coat-red only: hue in [0.90,1.0], saturated, opaque — skin/beard untouched
                mx = a[..., :3].max(-1); mn = a[..., :3].min(-1)
                sat = np.where(mx > 0.01, (mx - mn) / np.maximum(mx, 1), 0)
                hue = np.zeros_like(sat)
                d = np.maximum(mx - mn, 1)
                r_, g_, b_ = a[...,0], a[...,1], a[...,2]
                m_r = (mx == r_); m_g = (mx == g_) & ~m_r; m_b = ~(m_r | m_g)
                hue[m_r] = ((g_ - b_)[m_r] / d[m_r]) % 6
                hue[m_g] = (b_ - r_)[m_g] / d[m_g] + 2
                hue[m_b] = (r_ - g_)[m_b] / d[m_b] + 4
                hue /= 6.0
                mask = (hue >= 0.90) & (sat > 0.4) & (mx < 200) & (a[...,3] > 128)
                px = a[mask]
                if len(px) == 0:
                    continue
                hsv = np.array([colorsys.rgb_to_hsv(*(p/255.0)) for p in px[:, :3]])
                hsv[:, 0] = hues[i % len(hues)]
                rgb = np.array([colorsys.hsv_to_rgb(*p) for p in hsv]) * 255
                a[mask, 0], a[mask, 1], a[mask, 2] = rgb[:,0], rgb[:,1], rgb[:,2]
                out = Image.fromarray(a.astype(np.uint8), "RGBA")
                outdir = os.path.join(proc, f"crew_{i+1:02d}")
                os.makedirs(outdir, exist_ok=True)
                out.save(os.path.join(outdir, f"sprite_{pose}.png"))
                np_ = os.path.join(srcdir, f"sprite_{pose}_n.png")
                if os.path.exists(np_):
                    import shutil; shutil.copyfile(np_, os.path.join(outdir, f"sprite_{pose}_n.png"))
            manifest["variants"].append(f"crew_{i+1:02d}")
        manifest["of"] = base_id

    elif t == "ui_image":
        img = load(cdir, "accepted", "src.png").convert("RGB")
        s = min(img.size)
        img = img.crop(((img.width-s)//2, (img.height-s)//2,
                        (img.width+s)//2, (img.height+s)//2))
        img = img.resize((b.get("h_px",256), b.get("h_px",256)), Image.LANCZOS)
        img.save(os.path.join(proc, "portrait.png"))

    elif t == "parallax":
        import shutil
        shutil.copyfile(os.path.join(cdir, "accepted", "src.png"),
                        os.path.join(proc, "bg.png"))
        manifest["factor"] = b.get("factor")
        manifest["min_visible_pct"] = b.get("min_visible_pct")

    elif t == "glb":
        import struct, shutil
        shutil.copyfile(os.path.join(cdir, "export", "pirate.glb"),
                        os.path.join(proc, "pirate.glb"))
        d = open(os.path.join(cdir, "export", "pirate.glb"), "rb").read()
        clen, _ = struct.unpack("<II", d[12:20])
        j = json.loads(d[20:20+clen])
        tris = 0
        for m in j["meshes"]:
            for prim in m["primitives"]:
                if "indices" in prim:
                    acc = j["accessors"][prim["indices"]]
                    tris += acc["count"] // 3
        anims = [a["name"] for a in j.get("animations", [])]
        manifest.update({"meshes": len(j["meshes"]), "tris": tris,
                         "animations": anims,
                         "tri_budget": b.get("tri_budget"),
                         "gate": {"tris_ok": tris <= b.get("tri_budget", 1e9)}})

    atomic_json(os.path.join(cdir, "manifest.json"), manifest)
    print(json.dumps(manifest, indent=1)[:900])

def acquire_locks(cid):
    """Claim the component (+ its `of` base for variants) before work."""
    cdir = os.path.join(ROOT, "pipeline", "components", cid)
    b = json.load(open(os.path.join(cdir, "brief.json")))
    goal = sys.argv[sys.argv.index("--goal") + 1] if "--goal" in sys.argv else "manual"
    if goal != "manual" and b.get("goal") not in (None, goal):
        sys.exit(f"{cid}: claimed by goal '{b['goal']}' (this run: '{goal}')")
    wait = int(sys.argv[sys.argv.index("--wait") + 1]) if "--wait" in sys.argv else 0
    deps = {cid, b.get("of") or cid}
    locks = []
    for d in sorted(deps):
        locks.append(FileLock(
            os.path.join(ROOT, "pipeline", "components", d + ".lock"),
            owner=f"{goal}:extract", timeout=wait).acquire())
    return locks

if __name__ == "__main__":
    locks = []
    try:
        locks = acquire_locks(sys.argv[1])
        main(sys.argv[1])
    except LockHeld as e:
        sys.exit(str(e))
    finally:
        for l in reversed(locks):
            l.release()
