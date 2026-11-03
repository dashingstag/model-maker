"""Post-processes ComfyUI output for the Godot project.
Run with the ComfyUI venv python (has Pillow + numpy):

  C:/Workspace/ComfyUI/venv/Scripts/python tools/postprocess.py <gen_dir> <assets_dir>

- pirate_char.png  -> chroma-key green -> sprite_pirate.png (RGBA)
                   -> cutout_pirate.png (same alpha, larger) + normal map
- pirate_portrait  -> center-crop -> portrait.png
- bg_sky / bg_deck -> copied through as parallax layers
"""
import sys, os
from PIL import Image, ImageFilter
import numpy as np
from scipy import ndimage

gen, assets = sys.argv[1], sys.argv[2]
os.makedirs(assets, exist_ok=True)

def load(name):
    return Image.open(os.path.join(gen, name)).convert("RGBA")

def chroma_key(img, lo=90, tol=1.6):
    """Remove bright green screen -> alpha."""
    a = np.asarray(img).astype(np.float32)
    r, g, b = a[..., 0], a[..., 1], a[..., 2]
    mask = (g > lo) & (g > r * tol) & (g > b * tol)
    alpha = np.where(mask, 0, 255).astype(np.uint8)
    # soften edges
    edge = Image.fromarray(alpha).filter(ImageFilter.GaussianBlur(1.2))
    out = img.copy()
    out.putalpha(edge)
    return out

def largest_component(img):
    """Keep only the largest connected alpha blob (drops stray bg objects)."""
    alpha = np.asarray(img.split()[3]) > 8
    lab, n = ndimage.label(alpha)
    if n <= 1:
        return img
    biggest = max(range(1, n + 1), key=lambda i: (lab == i).sum())
    keep = (lab == biggest).astype(np.uint8) * 255
    keep = np.asarray(Image.fromarray(keep).filter(ImageFilter.GaussianBlur(1.0))) > 0
    a = np.asarray(img).copy()
    a[..., 3] = np.where(keep, a[..., 3], 0)
    return Image.fromarray(a, "RGBA")

def tight_crop(img):
    return img.crop(img.getbbox())

def normal_map(img):
    """Cheap tangent-space normal map from luminance (for PointLight2D)."""
    lum = np.asarray(img.convert("L")).astype(np.float32) / 255.0
    gy, gx = np.gradient(lum)
    strength = 4.0
    nx, ny = -gx * strength, -gy * strength
    nz = np.ones_like(lum)
    n = np.stack([nx, ny, nz], -1)
    n /= np.linalg.norm(n, axis=-1, keepdims=True)
    n = (n * 0.5 + 0.5) * 255
    alpha = np.asarray(img.split()[3])
    out = np.dstack([n.astype(np.uint8), alpha])
    return Image.fromarray(out, "RGBA")

# --- character ---
char = tight_crop(largest_component(chroma_key(load("pirate_char.png"))))
char.save(os.path.join(assets, "sprite_pirate.png"))
cut = char.resize((char.width * 2, char.height * 2), Image.LANCZOS)
cut.save(os.path.join(assets, "cutout_pirate.png"))
normal_map(cut).save(os.path.join(assets, "cutout_pirate_n.png"))

# --- portrait ---
p = load("pirate_portrait.png").convert("RGB")
s = min(p.size)
p = p.crop(((p.width - s)//2, (p.height - s)//2, (p.width + s)//2, (p.height + s)//2))
p.resize((256, 256), Image.LANCZOS).save(os.path.join(assets, "portrait.png"))

# --- parallax backgrounds ---
load("bg_sky.png").convert("RGB").save(os.path.join(assets, "bg_sky.png"))
load("bg_deck.png").convert("RGB").save(os.path.join(assets, "bg_deck.png"))

print("postprocess done ->", assets)
