# One-shot helper (idle-seed triage): fg/bg metrics + labeled contact sheets.
# Not part of tools/ — safe to delete after curation.
import json, os, sys
from PIL import Image, ImageDraw

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CIDS = sys.argv[1:] or ["xx_immortal_m", "xx_immortal_f", "xx_azure_sage"]
OUT = os.path.join(ROOT, "reports", "contact")
os.makedirs(OUT, exist_ok=True)

def fg_mask(im):
    g = im.convert("RGB")
    px = g.load()
    w, h = g.size
    m = bytearray(w * h)
    for y in range(h):
        for x in range(w):
            r, gg, b = px[x, y]
            # figure = deviates from near-white bg (low max channel or colored)
            if max(r, gg, b) < 235 or (max(r, gg, b) - min(r, gg, b)) > 18:
                m[y * w + x] = 1
    return m, w, h

def blobs(m, w, h, min_px=200):
    seen = bytearray(w * h)
    out = []
    for i in range(w * h):
        if not m[i] or seen[i]:
            continue
        stack, n, x0, x1, y0, y1 = [i], 0, w, -1, h, -1
        while stack:
            j = stack.pop()
            if seen[j] or not m[j]:
                continue
            seen[j] = 1
            n += 1
            y, x = divmod(j, w)
            x0, x1, y0, y1 = min(x0, x), max(x1, x), min(y0, y), max(y1, y)
            for nb in (j - 1, j + 1, j - w, j + w):
                if 0 <= nb < w * h and not seen[nb] and m[nb]:
                    if abs((nb % w) - x) <= 1:
                        stack.append(nb)
        if n >= min_px:
            out.append((n, x0, y0, x1, y1))
    return sorted(out, reverse=True)

def analyze(path):
    im = Image.open(path)
    w, h = im.size
    m, w, h = fg_mask(im)
    bs = blobs(m, w, h)
    if not bs:
        return {"file": os.path.basename(path), "empty": True}
    x0 = min(b[1] for b in bs); y0 = min(b[2] for b in bs)
    x1 = max(b[3] for b in bs); y1 = max(b[4] for b in bs)
    edge = 6
    bt = sum(m[(h - 1 - k) * w + x] for k in range(edge) for x in range(w))
    tt = sum(m[k * w + x] for k in range(edge) for x in range(w))
    corners = 0
    tot = 0
    px = im.convert("RGB").load()
    for cy in range(0, 30):
        for cx in list(range(0, 30)) + list(range(w - 30, w)):
            for yy in (cy, h - 1 - cy):
                if yy < 0:
                    continue
                corners += sum(px[cx, yy]) / 3
                tot += 1
    return {"file": os.path.basename(path), "w": w, "h": h,
            "fig_bbox": [x0, y0, x1, y1],
            "fig_w_pct": round((x1 - x0) / w * 100, 1),
            "fig_h_pct": round((y1 - y0) / h * 100, 1),
            "feet_at_bottom_edge_px": bt,
            "head_at_top_edge_px": tt,
            "sig_blobs": len(bs),
            "blob_sizes": [b[0] for b in bs[:5]],
            "bg_corner_lum": round(corners / max(tot, 1), 1)}

def sheet(cid, files):
    tw, th, lab = 256, 320, 22
    s = Image.new("RGB", (tw * 2 + 12, (th + lab) * 2 + 16), "white")
    d = ImageDraw.Draw(s)
    for i, f in enumerate(files):
        im = Image.open(f).resize((tw, th))
        cx, cy = (i % 2) * (tw + 8) + 2, (i // 2) * (th + lab + 8) + lab + 2
        s.paste(im, (cx, cy))
        d.text((cx + 4, cy - lab + 4), os.path.basename(f)[:-4], fill="black")
    out = os.path.join(OUT, f"{cid}_idle.png")
    s.save(out)
    return out

report = {}
for cid in CIDS:
    cand = os.path.join(ROOT, "pipeline", "components", cid, "candidates")
    files = sorted(os.path.join(cand, f) for f in os.listdir(cand)
                   if f.startswith(f"{cid}_idle_s") and f.endswith(".png"))
    report[cid] = [analyze(f) for f in files]
    report[cid + "_sheet"] = sheet(cid, files)

print(json.dumps(report, indent=1))
