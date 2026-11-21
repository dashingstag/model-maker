"""Survey an arbitrary (possibly unrigged) GLB: ortho turnaround renders +
measurements JSON for reference analysis.

  blender.exe --background --python tools/blender_survey.py -- \
        --glb <model.glb> --out <dir> [--name <prefix>] [--size 768]

Emits <out>/<name>_{front,back,left,right,three_quarter}.png (transparent bg)
and <out>/<name>_survey.json with bbox, vertex stats, a height-sliced
silhouette profile, and derived landmarks (neck/shoulder/waist/hip widths).
"""
import bpy, json, math, os, sys
import numpy as np
from mathutils import Vector

argv = sys.argv[sys.argv.index("--") + 1:]
GLB = argv[argv.index("--glb") + 1]
OUT = argv[argv.index("--out") + 1]
NAME = argv[argv.index("--name") + 1] if "--name" in argv else "survey"
SIZE = int(argv[argv.index("--size") + 1]) if "--size" in argv else 768
os.makedirs(OUT, exist_ok=True)

bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=GLB)

meshes = [o for o in bpy.data.objects if o.type == 'MESH']
for o in bpy.data.objects:
    if "-colonly" in o.name:
        o.hide_render = True
        o.hide_set(True)
meshes = [o for o in meshes if not o.hide_render]
assert meshes, "no renderable meshes"

# ---------- world-space vertex cloud ----------
parts = []
tris = 0
for o in meshes:
    n = len(o.data.vertices)
    a = np.empty(n * 3, dtype=np.float32)
    o.data.vertices.foreach_get("co", a)
    a = a.reshape(-1, 3)
    m = np.asarray(o.matrix_world, dtype=np.float32)
    parts.append(a @ m[:3, :3].T + m[:3, 3])
    o.data.calc_loop_triangles()
    tris += len(o.data.loop_triangles)
V = np.vstack(parts)
vmin, vmax = V.min(axis=0), V.max(axis=0)
size = vmax - vmin
center = (vmin + vmax) / 2
height = float(size[2])
assert height > 1e-6, "degenerate Z extent — model not Z-up?"

# ---------- silhouette profile along +Z ----------
BINS = 96
z0, z1 = float(vmin[2]), float(vmax[2])
idx = np.clip(((V[:, 2] - z0) / (z1 - z0) * BINS).astype(int), 0, BINS - 1)
profile = []
for b in range(BINS):
    sel = V[idx == b]
    if len(sel) == 0:
        profile.append({"z": round(b / BINS, 4), "x_width": 0.0,
                        "y_depth": 0.0, "vcount": 0})
        continue
    profile.append({"z": round(b / BINS, 4),
                    "x_width": round(float(sel[:, 0].max() - sel[:, 0].min()), 4),
                    "y_depth": round(float(sel[:, 1].max() - sel[:, 1].min()), 4),
                    "vcount": int(len(sel))})

def band(lo, hi):
    return [p for p in profile if lo <= p["z"] <= hi and p["vcount"] > 0]

def widest(b):  return max(b, key=lambda p: p["x_width"])
def narrowest(b): return min(b, key=lambda p: p["x_width"])

neck = narrowest(band(0.82, 0.90))
shoulder = widest(band(0.72, 0.86))
waist = narrowest(band(0.52, 0.70))
hip = widest(band(0.42, 0.58))
head_h = (1.0 - neck["z"]) * height
landmarks = {
    "neck_z_frac": neck["z"], "neck_width": neck["x_width"],
    "shoulder_z_frac": shoulder["z"], "shoulder_width": shoulder["x_width"],
    "waist_z_frac": waist["z"], "waist_width": waist["x_width"],
    "hip_z_frac": hip["z"], "hip_width": hip["x_width"],
    "head_height_est": round(head_h, 4),
    "head_ratio_est": round(height / head_h, 2) if head_h > 1e-6 else None,
    "shoulder_to_height": round(shoulder["x_width"] / height, 3),
    "hip_to_height": round(hip["x_width"] / height, 3),
    "note": "neck = min x_width in z[0.82,0.90]; unreliable for tilted heads / asymmetric hair — verify against renders",
}

# ---------- materials ----------
mats = []
for m in bpy.data.materials:
    imgs = [n.image.name for n in (m.node_tree.nodes if m.node_tree else [])
            if n.type == 'TEX_IMAGE' and n.image]
    mats.append({"name": m.name, "images": imgs})

# ---------- camera + turnaround ----------
cam_data = bpy.data.cameras.new("cam")
cam_data.type = 'ORTHO'
cam_data.ortho_scale = height * 1.08
cam_data.clip_start = 0.01
cam_data.clip_end = 200
cam = bpy.data.objects.new("cam", cam_data)
bpy.context.collection.objects.link(cam)
bpy.context.scene.camera = cam

sun = bpy.data.objects.new("sun", bpy.data.lights.new("sun", 'SUN'))
sun.data.energy = 3.0
sun.rotation_euler = (math.radians(50), 0, math.radians(-30))
bpy.context.collection.objects.link(sun)
world = bpy.data.worlds.new("w")
world.use_nodes = True
world.node_tree.nodes["Background"].inputs[0].default_value = (1, 1, 1, 1)
world.node_tree.nodes["Background"].inputs[1].default_value = 0.35
bpy.context.scene.world = world

scene = bpy.context.scene
scene.render.engine = 'BLENDER_EEVEE_NEXT'
scene.render.film_transparent = True
scene.render.resolution_x = scene.render.resolution_y = SIZE

DIST = max(size) * 4 + 2.0
VIEWS = {
    "front": Vector((0, -1, 0)),
    "back": Vector((0, 1, 0)),
    "left": Vector((-1, 0, 0)),
    "right": Vector((1, 0, 0)),
    "three_quarter": Vector((-0.7071, -0.7071, 0.15)).normalized(),
}
cpos = Vector((float(center[0]), float(center[1]), float(center[2])))
for name, d in VIEWS.items():
    cam.location = cpos + d * DIST
    aim = cpos - cam.location
    cam.rotation_euler = aim.to_track_quat('-Z', 'Y').to_euler()
    scene.render.filepath = os.path.join(OUT, f"{NAME}_{name}.png")
    bpy.ops.render.render(write_still=True)

survey = {
    "glb": os.path.abspath(GLB),
    "counts": {"mesh_objects": len(meshes),
               "verts": int(len(V)), "tris": int(tris)},
    "bbox": {"min": [round(float(x), 4) for x in vmin],
             "max": [round(float(x), 4) for x in vmax],
             "size": [round(float(x), 4) for x in size]},
    "up_axis": "Z", "height": round(height, 4),
    "landmarks": landmarks,
    "profile": profile,
    "materials": mats,
}
with open(os.path.join(OUT, f"{NAME}_survey.json"), "w") as f:
    json.dump(survey, f, indent=2)
print("SURVEY OK", json.dumps(survey["counts"]), "h=", survey["height"])
