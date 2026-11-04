"""Headless Blender script: builds the Azure Sage hero GLB — a styled
rigged humanoid on the shared/skeletons/humanoid_v1 bone names, with the
brief's `anims` baked as pose-keyframed clips (shared/poses/*.json).

This is an honest first-pass rigged model (mannequin-grade primitives,
not sculpted art): it exists so the hero contract — skeleton, animation
clips with event times, socketed-prop attachment — is exercised end to
end. Visual fidelity beyond silhouette is a backlog item.

Props are NOT baked in: attachments resolve at runtime via Godot
BoneAttachment3D on the named socket bone.

Run:  blender.exe --background --python tools/blender_hero.py -- \
        --out <abs path>.glb --brief <abs brief.json>
"""
import bpy
import json
import math
import os
import sys

argv = sys.argv[sys.argv.index("--") + 1:]
OUT = argv[argv.index("--out") + 1] if "--out" in argv else "hero.glb"
BRIEF = argv[argv.index("--brief") + 1] if "--brief" in argv else None

bpy.ops.wm.read_factory_settings(use_empty=True)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
brief = json.load(open(BRIEF)) if BRIEF else {}

def mat(name, rgb, rough=0.8, emit=None):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    bsdf = m.node_tree.nodes["Principled BSDF"]
    bsdf.inputs["Base Color"].default_value = (*rgb, 1.0)
    bsdf.inputs["Roughness"].default_value = rough
    if emit:
        bsdf.inputs["Emission Color"].default_value = (*emit, 1.0)
        bsdf.inputs["Emission Strength"].default_value = 1.5
    return m

# Azure Sage styling — indigo/silver robes, white hair, dark crown, jade gem
MATS = {
    "cloth":   mat("robe_indigo",  (0.16, 0.18, 0.34)),
    "sleeve":  mat("sleeve_silver",(0.55, 0.58, 0.68)),
    "trim":    mat("trim_silver",  (0.70, 0.72, 0.80)),
    "skin":    mat("skin",         (0.82, 0.72, 0.64)),
    "hair":    mat("hair_white",   (0.88, 0.90, 0.94)),
    "crown":   mat("crown_dark",   (0.12, 0.10, 0.16), rough=0.35),
    "gem":     mat("gem_jade",     (0.15, 0.55, 0.60), rough=0.2,
                   emit=(0.10, 0.45, 0.55)),
    "steel":   mat("steel",        (0.65, 0.68, 0.72)),
}

parts = []

def sphere(name, loc, scale, material):
    bpy.ops.mesh.primitive_uv_sphere_add(segments=14, ring_count=10, location=loc)
    o = bpy.context.object
    o.name = name
    o.scale = scale
    bpy.ops.object.transform_apply(scale=True)
    o.data.materials.append(material)
    parts.append(o)
    return o

def cyl(name, loc, radius, depth, material, rot=None):
    bpy.ops.mesh.primitive_cylinder_add(vertices=10, radius=radius, depth=depth,
                                        location=loc, rotation=rot or (0, 0, 0))
    o = bpy.context.object
    o.name = name
    o.data.materials.append(material)
    parts.append(o)
    return o

def cone(name, loc, r1, r2, depth, material, rot=None):
    bpy.ops.mesh.primitive_cone_add(vertices=12, radius1=r1, radius2=r2,
                                  depth=depth, location=loc, rotation=rot or (0, 0, 0))
    o = bpy.context.object
    o.name = name
    o.data.materials.append(material)
    parts.append(o)
    return o

def cube(name, loc, scale, material, rot=None):
    bpy.ops.mesh.primitive_cube_add(location=loc, rotation=rot or (0, 0, 0))
    o = bpy.context.object
    o.name = name
    o.scale = scale
    bpy.ops.object.transform_apply(scale=True)
    o.data.materials.append(material)
    parts.append(o)
    return o

# ---------------- body (~1.75m, origin at feet, faces -Y) ----------------
sphere("pelvis", (0, 0, 0.98), (0.15, 0.11, 0.12), MATS["cloth"])
sphere("chest_m", (0, 0, 1.33), (0.17, 0.12, 0.16), MATS["cloth"])
sphere("head_m", (0, 0, 1.64), (0.12, 0.11, 0.13), MATS["skin"])
cyl("neck_m", (0, 0, 1.48), 0.05, 0.10, MATS["skin"])
# silver-white hair: crown knot + long fall down the back
sphere("topknot", (0, 0.01, 1.80), (0.04, 0.04, 0.055), MATS["hair"])
cone("hair_fall", (0, 0.10, 1.52), 0.045, 0.085, 0.55, MATS["hair"],
     rot=(0.35, 0, 0))
sphere("hair_cap", (0, 0.02, 1.68), (0.125, 0.115, 0.13), MATS["hair"])
# dark crown ornament + jade brow gem
cube("crown", (0, -0.02, 1.86), (0.05, 0.03, 0.05), MATS["crown"])
sphere("brow_gem", (0, -0.115, 1.70), (0.02, 0.012, 0.02), MATS["gem"])
# wide sleeves (upper arm -> elbow flare)
cone("sleeve_up_l", (-0.26, 0, 1.36), 0.075, 0.10, 0.28, MATS["cloth"], rot=(0, 0.5, 0))
cone("sleeve_lo_l", (-0.50, 0, 1.18), 0.17, 0.07, 0.32, MATS["sleeve"], rot=(0, 0.6, 0))
cone("sleeve_up_r", ( 0.26, 0, 1.36), 0.075, 0.10, 0.28, MATS["cloth"], rot=(0, -0.5, 0))
cone("sleeve_lo_r", ( 0.50, 0, 1.18), 0.17, 0.07, 0.32, MATS["sleeve"], rot=(0, -0.6, 0))
sphere("hand_l", (-0.60, 0, 1.06), (0.05, 0.045, 0.05), MATS["skin"])
sphere("hand_r", ( 0.60, 0, 1.06), (0.05, 0.045, 0.05), MATS["skin"])
# layered robes: inner hakama + outer draped layer + sash
cone("hakama_l", (-0.11, 0, 0.55), 0.17, 0.13, 0.85, MATS["cloth"])
cone("hakama_r", ( 0.11, 0, 0.55), 0.17, 0.13, 0.85, MATS["cloth"])
cone("robe_outer", (0, 0.02, 0.85), 0.30, 0.19, 0.95, MATS["trim"])
cyl("sash", (0, 0, 1.05), 0.155, 0.07, MATS["gem"])
cube("foot_l", (-0.11, -0.05, 0.04), (0.06, 0.12, 0.04), MATS["crown"])
cube("foot_r", ( 0.11, -0.05, 0.04), (0.06, 0.12, 0.04), MATS["crown"])

# ---------------- armature (humanoid_v1 names) ----------------
bpy.ops.object.armature_add(location=(0, 0, 0))
arm = bpy.context.object
arm.name = "humanoid_armature"

bpy.ops.object.mode_set(mode='EDIT')
eb = arm.data.edit_bones
root_b = arm.data.edit_bones['Bone']
root_b.name = "root"
root_b.head, root_b.tail = (0, 0, 0.95), (0, 0, 1.05)

def bone(name, head, tail, parent):
    b = eb.new(name)
    b.head, b.tail, b.parent = head, tail, parent
    return b

spine   = bone("spine", (0, 0, 1.05), (0, 0, 1.25), root_b)
chest   = bone("chest", (0, 0, 1.25), (0, 0, 1.44), spine)
neck    = bone("neck",  (0, 0, 1.44), (0, 0, 1.53), chest)
head_b  = bone("head",  (0, 0, 1.53), (0, 0, 1.76), neck)
sh_l    = bone("shoulder.l", (-0.07, 0, 1.42), (-0.16, 0, 1.42), chest)
ua_l    = bone("upper_arm.l", (-0.16, 0, 1.42), (-0.38, 0, 1.28), sh_l)
fa_l    = bone("forearm.l", (-0.38, 0, 1.28), (-0.57, 0, 1.10), ua_l)
hand_l  = bone("hand.l", (-0.57, 0, 1.10), (-0.65, 0, 1.04), fa_l)
sh_r    = bone("shoulder.r", (0.07, 0, 1.42), (0.16, 0, 1.42), chest)
ua_r    = bone("upper_arm.r", (0.16, 0, 1.42), (0.38, 0, 1.28), sh_r)
fa_r    = bone("forearm.r", (0.38, 0, 1.28), (0.57, 0, 1.10), ua_r)
hand_r  = bone("hand.r", (0.57, 0, 1.10), (0.65, 0, 1.04), fa_r)
th_l    = bone("thigh.l", (-0.11, 0, 0.95), (-0.11, 0, 0.52), root_b)
sn_l    = bone("shin.l", (-0.11, 0, 0.52), (-0.11, 0, 0.10), th_l)
ft_l    = bone("foot.l", (-0.11, 0, 0.10), (-0.11, -0.16, 0.04), sn_l)
th_r    = bone("thigh.r", (0.11, 0, 0.95), (0.11, 0, 0.52), root_b)
sn_r    = bone("shin.r", (0.11, 0, 0.52), (0.11, 0, 0.10), th_r)
ft_r    = bone("foot.r", (0.11, 0, 0.10), (0.11, -0.16, 0.04), sn_r)

bpy.ops.object.mode_set(mode='OBJECT')

BONE_OF = {
    "pelvis": "root", "chest_m": "chest", "head_m": "head", "neck_m": "neck",
    "topknot": "head", "hair_fall": "head", "hair_cap": "head",
    "crown": "head", "brow_gem": "head",
    "sleeve_up_l": "upper_arm.l", "sleeve_lo_l": "forearm.l", "hand_l": "hand.l",
    "sleeve_up_r": "upper_arm.r", "sleeve_lo_r": "forearm.r", "hand_r": "hand.r",
    "hakama_l": "thigh.l", "hakama_r": "thigh.r", "robe_outer": "root",
    "sash": "root",
    "foot_l": "foot.l", "foot_r": "foot.r",
}
for o in parts:
    mw = o.matrix_world.copy()
    o.parent = arm
    o.parent_type = 'BONE'
    o.parent_bone = BONE_OF[o.name]
    o.matrix_world = mw

# ---------------- animation clips (pose-keyframed from shared/poses) ----------------
POSES = {}
pdir = os.path.join(ROOT, "shared", "poses")
for pf in sorted(os.listdir(pdir)):
    if pf.endswith(".json"):
        POSES.update(json.load(open(os.path.join(pdir, pf))).get("poses", {}))

FPS = 24

def pose_at(cfg):
    """(eulers, locs) dicts for a pose spec."""
    return cfg.get("bones", {}), cfg.get("loc", {})

def blend(a, b, t):
    return tuple(x + (y - x) * t for x, y in zip(a, b))

def key_bones(action, frame, pose_cfgs):
    """Key every bone at `frame` toward blended pose configs (rest = zeros)."""
    eulers, locs = {}, {}
    for cfg, w in pose_cfgs:
        e, l = pose_at(cfg)
        for k, v in e.items():
            eulers[k] = blend(eulers.get(k, (0, 0, 0)), v, w)
        for k, v in l.items():
            locs[k] = blend(locs.get(k, (0, 0, 0)), v, w)
    for pb in arm.pose.bones:
        pb.rotation_mode = 'XYZ'
        pb.rotation_euler = eulers.get(pb.name, (0, 0, 0))
        pb.location = locs.get(pb.name, (0, 0, 0))
        pb.keyframe_insert('rotation_euler', frame=frame)
        pb.keyframe_insert('location', frame=frame)

def P(name, w=1.0):
    return (POSES[name], w)

# clip spec: (name, duration_s, keys[(t_frac, [(pose_cfg, weight)])])
def clip_frames(dur):
    return int(round(dur * FPS)) + 1

ANIM_KEYS = {
    "idle": (1.0, [(0.0, [P("idle")]), (0.5, [P("idle"), ({"bones": {"spine": [0.03, 0, 0]}}, 1.0)]),
                   (1.0, [P("idle")])]),
    "walk": (1.0, [(0.0, [P("walk_a")]), (0.5, [P("walk_b")]), (1.0, [P("walk_a")])]),
    "channel_water": (2.0, [(0.0, []), (0.3, [P("channel_water")]),
                            (0.7, [P("channel_water")]), (1.0, [])]),
    "staff_salute": (1.2, [(0.0, []), (0.4, [P("staff_stance")]),
                           (0.75, [P("staff_stance")]), (1.0, [])]),
    "seated_meditate": (4.0, [(0.0, [P("seated_meditation")]),
                              (0.5, [P("seated_meditation")]),
                              (1.0, [P("seated_meditation")])]),
}

arm.animation_data_create()
for spec in brief.get("anims", []):
    name = spec["name"]
    if name not in ANIM_KEYS:
        continue
    dur = spec.get("duration") or 1.0
    action = bpy.data.actions.new(name)
    arm.animation_data.action = action
    n_fr = clip_frames(dur)
    for tf, cfgs in ANIM_KEYS[name][1]:
        key_bones(action, tf * (n_fr - 1), cfgs)
    # NLA track per anim -> one exported GLB animation per clip
    tr = arm.animation_data.nla_tracks.new()
    tr.name = name
    tr.strips.new(name, 0, action)
    arm.animation_data.action = None

bpy.ops.object.select_all(action='SELECT')
bpy.ops.export_scene.gltf(filepath=OUT, export_yup=True,
                          export_apply=False, export_animations=True,
                          export_animation_mode='NLA_TRACKS')
print("EXPORTED", OUT, "anims:", [t.name for t in arm.animation_data.nla_tracks])
