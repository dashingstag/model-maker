"""Scratch helper: build 2x2 contact sheets for card candidates.

Run: "C:/Workspace/ComfyUI/venv/Scripts/python" reports/contact/_make_sheets.py
Writes reports/contact/<id>.png for each component id in IDS.
"""
import os
from PIL import Image, ImageDraw

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
IDS = [
    "xx_card_blade",
    "xx_card_archivist",
    "xx_card_venom",
    "xx_card_mirror",
    "xx_card_monk",
    "xx_card_planets",
    "xx_card_azure_sage",
]
LABEL_H = 22
PAD = 6
COLS = 2

for cid in IDS:
    cand = os.path.join(ROOT, "pipeline", "components", cid, "candidates")
    files = sorted(f for f in os.listdir(cand)
                   if f.endswith(".png") and not f.startswith("_"))
    if not files:
        print(f"{cid}: no candidates, skipped")
        continue
    imgs = [Image.open(os.path.join(cand, f)) for f in files]
    w, h = imgs[0].size
    rows = (len(imgs) + COLS - 1) // COLS
    sheet_w = COLS * w + (COLS + 1) * PAD
    sheet_h = rows * (h + LABEL_H) + (rows + 1) * PAD
    sheet = Image.new("RGB", (sheet_w, sheet_h), (20, 16, 16))
    draw = ImageDraw.Draw(sheet)
    for i, (img, f) in enumerate(zip(imgs, files)):
        r, c = divmod(i, COLS)
        x = PAD + c * (w + PAD)
        y = PAD + r * (h + LABEL_H + PAD)
        sheet.paste(img, (x, y))
        draw.text((x + 4, y + h + 4), f, fill=(232, 224, 212))
    out = os.path.join(ROOT, "reports", "contact", f"{cid}.png")
    sheet.save(out)
    print(f"{cid}: {len(files)} imgs -> {out}")
