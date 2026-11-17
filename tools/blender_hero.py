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

import mathutils

argv = sys.argv[sys.argv.index("--") + 1:]
OUT = argv[argv.index("--out") + 1] if "--out" in argv else "hero.glb"
BRIEF = argv[argv.index("--brief") + 1] if "--brief" in argv else None

bpy.ops.wm.read_factory_settings(use_empty=True)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
brief = json.load(open(BRIEF)) if BRIEF else {}

def mat(name, rgb, rough=0.8, emit=None, metal=0.0):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    bsdf = m.node_tree.nodes["Principled BSDF"]
    bsdf.inputs["Base Color"].default_value = (*rgb, 1.0)
    bsdf.inputs["Roughness"].default_value = rough
    bsdf.inputs["Metallic"].default_value = metal
    if emit:
        bsdf.inputs["Emission Color"].default_value = (*emit, 1.0)
        bsdf.inputs["Emission Strength"].default_value = 1.5
    return m

# Azure Sage styling — deep indigo owns the silhouette, silver is the
# accent layer, jade marks rank; base colors are linear so darks must be
# genuinely low or the render washes to pastel
MATS = {
    "cloth":   mat("robe_indigo",  (0.035, 0.045, 0.12)),
    "sleeve":  mat("sleeve_indigo",(0.08, 0.10, 0.22)),
    "trim":    mat("trim_silver",  (0.52, 0.56, 0.66)),
    "skin":    mat("skin",         (0.62, 0.48, 0.40)),
    "hair":    mat("hair_white",   (0.70, 0.74, 0.84)),
    "crown":   mat("crown_dark",   (0.02, 0.02, 0.04), rough=0.3, metal=0.7),
    "gem":     mat("gem_jade",     (0.14, 0.50, 0.34), rough=0.2,
                   emit=(0.06, 0.38, 0.24)),
    "steel":   mat("steel",        (0.30, 0.32, 0.38), rough=0.3, metal=0.9),
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

def torus(name, loc, major, minor, material, rot=None):
    bpy.ops.mesh.primitive_torus_add(major_radius=major, minor_radius=minor,
                                     major_segments=12, minor_segments=6,
                                     location=loc, rotation=rot or (0, 0, 0))
    o = bpy.context.object
    o.name = name
    o.data.materials.append(material)
    parts.append(o)
    return o

# ---------------- body (~1.75m, origin at feet, faces -Y) ----------------
sphere("pelvis", (0, 0, 0.98), (0.15, 0.11, 0.12), MATS["cloth"])
sphere("chest_m", (0, 0, 1.33), (0.17, 0.12, 0.16), MATS["cloth"])
sphere("head_m", (0, 0, 1.64), (0.11, 0.10, 0.145), MATS["skin"])
cube("jaw_m", (0, -0.045, 1.565), (0.055, 0.045, 0.035), MATS["skin"])
cyl("neck_m", (0, 0, 1.48), 0.05, 0.10, MATS["skin"])
# silver-white hair: elongated topknot + wide fall + face-framing locks
cone("topknot", (0, 0.01, 1.82), 0.05, 0.018, 0.13, MATS["hair"])
cone("hair_fall", (0, 0.10, 1.40), 0.055, 0.13, 0.75, MATS["hair"],
     rot=(0.35, 0, 0))
sphere("hair_cap", (0, 0.02, 1.69), (0.125, 0.115, 0.135), MATS["hair"])
cone("lock_l", (-0.085, -0.055, 1.55), 0.018, 0.008, 0.28, MATS["hair"],
     rot=(-0.12, 0, 0))
cone("lock_r", ( 0.085, -0.055, 1.55), 0.018, 0.008, 0.28, MATS["hair"],
     rot=(-0.12, 0, 0))
# tall guan crown: metal band + fin + hairpin through the knot
cyl("crown", (0, -0.01, 1.865), 0.045, 0.07, MATS["crown"])
cube("crown_fin", (0, -0.01, 1.93), (0.018, 0.05, 0.035), MATS["crown"])
cyl("hairpin", (0, 0.01, 1.845), 0.008, 0.20, MATS["steel"],
    rot=(0, 1.5708, 0))
sphere("brow_gem", (0, -0.105, 1.70), (0.028, 0.014, 0.028), MATS["gem"])
# arms have substance: thin upper-arm sleeve + forearm under the cuff
cyl("up_arm_l", (-0.27, 0, 1.35), 0.045, 0.24, MATS["cloth"], rot=(0, 0.6, 0))
cyl("up_arm_r", ( 0.27, 0, 1.35), 0.045, 0.24, MATS["cloth"], rot=(0, -0.6, 0))
cyl("forearm_l", (-0.48, 0, 1.19), 0.035, 0.22, MATS["skin"], rot=(0, 0.65, 0))
cyl("forearm_r", ( 0.48, 0, 1.19), 0.035, 0.22, MATS["skin"], rot=(0, -0.65, 0))
# stacked sleeves hugging the arm line + silver cuff ring at the rim
cone("sleeve_up_l", (-0.26, 0, 1.36), 0.085, 0.11, 0.28, MATS["sleeve"], rot=(0, 0.5, 0))
cone("sleeve_lo_l", (-0.49, 0, 1.19), 0.135, 0.065, 0.30, MATS["sleeve"], rot=(0, 0.62, 0))
torus("cuff_l", (-0.575, 0, 1.095), 0.075, 0.012, MATS["trim"], rot=(0, 0.62, 0))
cone("sleeve_up_r", ( 0.26, 0, 1.36), 0.085, 0.11, 0.28, MATS["sleeve"], rot=(0, -0.5, 0))
cone("sleeve_lo_r", ( 0.49, 0, 1.19), 0.135, 0.065, 0.30, MATS["sleeve"], rot=(0, -0.62, 0))
torus("cuff_r", ( 0.575, 0, 1.095), 0.075, 0.012, MATS["trim"], rot=(0, -0.62, 0))
sphere("hand_l", (-0.615, 0, 1.045), (0.05, 0.045, 0.05), MATS["skin"])
sphere("hand_r", ( 0.615, 0, 1.045), (0.05, 0.045, 0.05), MATS["skin"])
# collar lapels + shoulder mantle over the chest-neck seam
cube("lapel_l", (-0.045, -0.10, 1.40), (0.035, 0.02, 0.11), MATS["trim"],
     rot=(0, 0.35, 0))
cube("lapel_r", ( 0.045, -0.10, 1.40), (0.035, 0.02, 0.11), MATS["trim"],
     rot=(0, -0.35, 0))
cone("mantle", (0, 0.01, 1.42), 0.24, 0.14, 0.16, MATS["trim"])
# layered lower robes: fitted waist + thigh-driven skirt gores + apron
cone("hakama_l", (-0.11, 0, 0.50), 0.18, 0.14, 0.90, MATS["trim"])
cone("hakama_r", ( 0.11, 0, 0.50), 0.18, 0.14, 0.90, MATS["trim"])
cone("robe_up", (0, 0.01, 1.16), 0.16, 0.21, 0.28, MATS["cloth"])
cone("skirt_l", (-0.13, 0.01, 0.62), 0.24, 0.15, 0.80, MATS["cloth"])
cone("skirt_r", ( 0.13, 0.01, 0.62), 0.24, 0.15, 0.80, MATS["cloth"])
cube("apron_f", (0, -0.14, 0.72), (0.09, 0.025, 0.42), MATS["sleeve"])
# exposed jade sash: wide band + knot + hanging ribbon tails
cyl("sash", (0, 0, 1.05), 0.235, 0.07, MATS["gem"])
cube("sash_knot", (0, -0.225, 1.05), (0.05, 0.03, 0.045), MATS["gem"])
cone("sash_tail_l", (-0.05, -0.16, 0.78), 0.028, 0.05, 0.48, MATS["gem"])
cone("sash_tail_r", ( 0.05, -0.16, 0.78), 0.028, 0.05, 0.48, MATS["gem"])
cube("foot_l", (-0.11, -0.06, 0.04), (0.06, 0.16, 0.04), MATS["crown"])
cube("foot_r", ( 0.11, -0.06, 0.04), (0.06, 0.16, 0.04), MATS["crown"])

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

# humanoid_v2 extended chains — declared by the brief's skeleton ref;
# v1 keeps exactly the 19 required bones
SKEL_V2 = brief.get("skeleton", "").endswith("humanoid_v2")
FINGERS = ("thumb", "index", "middle", "ring", "pinky")
STUBS = []
if SKEL_V2:
    # fingers: 3-joint chains fanning off each hand; stubs (one per
    # finger, bound to .2) let mitten geometry articulate at knuckle
    # level — a blob hand gains crude but real finger motion
    for side, sx in (("l", -1.0), ("r", 1.0)):
        hand = hand_l if side == "l" else hand_r
        hdir = mathutils.Vector((sx * 0.8, 0, -0.6)).normalized()
        for fi, f in enumerate(FINGERS):
            yoff = [-0.028, -0.014, 0.0, 0.014, 0.028][fi]
            if f == "thumb":
                fdir = mathutils.Vector((sx * 0.55, -0.45, -0.6)).normalized()
                froot = hand.tail + mathutils.Vector((0, -0.01, 0.01))
                seg = 0.022
            else:
                fdir = hdir.copy()
                froot = hand.tail + hdir * 0.02 + mathutils.Vector((0, yoff, 0))
                seg = 0.028
            prev = hand
            tip_at = froot
            for j in (1, 2, 3):
                tip_at = tip_at + fdir * seg
                prev = bone("hand.%s.%s.%d" % (side, f, j), froot, tip_at, prev)
                froot = tip_at
            STUBS.append(("finger_%s_%s" % (side, f),
                          hand.tail + hdir * 0.02
                          + mathutils.Vector((0, yoff, 0))
                          + fdir * seg * 1.5, fdir,
                          "hand.%s.%s.2" % (side, f)))
    # robe panels + hair + face — present so conform/reskin can route
    # real costume geometry onto them (painted meshes have skirt/hair
    # shells; fingers/jaw are forward-compatible slots)
    bone("skirt.front", (0, -0.13, 0.95), (0, -0.16, 0.55), root_b)
    bone("skirt.back", (0, 0.13, 0.95), (0, 0.16, 0.55), root_b)
    bone("skirt.l", (-0.14, 0, 0.95), (-0.17, 0, 0.55), root_b)
    bone("skirt.r", (0.14, 0, 0.95), (0.17, 0, 0.55), root_b)
    bone("hair.1", (0, 0.02, 1.76), (0, 0.02, 1.88), head_b)
    bone("hair.2", (0, 0.10, 1.70), (0, 0.14, 1.35), head_b)
    bone("hair.3", (-0.08, -0.05, 1.62), (-0.09, -0.06, 1.42), head_b)
    bone("hair.4", (0.08, -0.05, 1.62), (0.09, -0.06, 1.42), head_b)
    bone("jaw", (0, -0.05, 1.58), (0, -0.09, 1.50), head_b)
    bone("eye.l", (-0.045, -0.09, 1.66), (-0.045, -0.12, 1.66), head_b)
    bone("eye.r", (0.045, -0.09, 1.66), (0.045, -0.12, 1.66), head_b)

bpy.ops.object.mode_set(mode='OBJECT')

for name, loc, fdir, bname in STUBS:
    stub = cyl(name, tuple(loc), 0.013, 0.062, MATS["skin"],
               rot=(0, math.atan2(fdir.x, fdir.z) + math.pi / 2, 0))
    stub["v2_bone"] = bname

BONE_OF = {
    "pelvis": "root", "chest_m": "chest", "head_m": "head", "jaw_m": "head",
    "neck_m": "neck",
    "topknot": "head", "hair_fall": "head", "hair_cap": "head",
    "lock_l": "head", "lock_r": "head",
    "crown": "head", "crown_fin": "head", "hairpin": "head",
    "brow_gem": "head",
    "up_arm_l": "upper_arm.l", "up_arm_r": "upper_arm.r",
    "forearm_l": "forearm.l", "forearm_r": "forearm.r",
    "sleeve_up_l": "upper_arm.l", "sleeve_lo_l": "forearm.l",
    "cuff_l": "forearm.l", "hand_l": "hand.l",
    "sleeve_up_r": "upper_arm.r", "sleeve_lo_r": "forearm.r",
    "cuff_r": "forearm.r", "hand_r": "hand.r",
    "lapel_l": "chest", "lapel_r": "chest", "mantle": "chest",
    "hakama_l": "thigh.l", "hakama_r": "thigh.r",
    "robe_up": "root", "skirt_l": "thigh.l", "skirt_r": "thigh.r",
    "apron_f": "root", "sash": "root", "sash_knot": "root",
    "sash_tail_l": "root", "sash_tail_r": "root",
    "foot_l": "foot.l", "foot_r": "foot.r",
}
# v2 remaps — costume shells onto their driver bones so conform/reskin
# routes painted-mesh verts to articulable chains (hair sway, skirt
# panels); finger stubs carry their v2_bone tag
if SKEL_V2:
    BONE_OF.update({
        "topknot": "hair.1", "hair_fall": "hair.2",
        "lock_l": "hair.3", "lock_r": "hair.4", "jaw_m": "jaw",
        "skirt_l": "skirt.l", "skirt_r": "skirt.r",
        "apron_f": "skirt.front",
        "sash_tail_l": "skirt.front", "sash_tail_r": "skirt.front",
    })
for o in parts:
    mw = o.matrix_world.copy()
    o.parent = arm
    o.parent_type = 'BONE'
    o.parent_bone = o.get("v2_bone") or BONE_OF[o.name]
    o.matrix_world = mw

# ---------------- animation clips (pose-keyframed from shared/poses) ----------------
POSES = {}
pdir = os.path.join(ROOT, "shared", "poses")
for pf in sorted(os.listdir(pdir)):
    if pf.endswith(".json"):
        POSES.update(json.load(open(os.path.join(pdir, pf))).get("poses", {}))

# finger gestures — shared/poses/<g>.json joint_deg tables become pose
# cfgs on hand.{side}.{finger}.{n}; mirrored variants share the same
# curl axis values (bone-local X). Harmless on v1 builds: key_bones
# iterates armature bones, so unborn bone names are never keyed
def _gesture_cfg(name, side=None):
    d = json.load(open(os.path.join(pdir, name + ".json")))
    hand = side or d["hand"]
    return {"bones": {"%s.%s" % (hand, j): [math.radians(v), 0, 0]
                      for j, v in d["joints_deg"].items()}}

GCFG = {}
for g in ("grip_sword", "open_palm", "staff_grip", "sword_fingers",
          "talisman_pinch"):
    try:
        GCFG[g] = _gesture_cfg(g)
        GCFG[g + ".l"] = _gesture_cfg(g, "hand.l")
    except (OSError, KeyError):
        pass

# per-clip gesture overlays — the weapon hand keeps its grip through
# every frame; the free hand takes the seal/palm shape
CLIP_GESTURES = {
    "idle": ["open_palm.l"],
    "walk": ["open_palm.l"],
    "breath": ["open_palm.l"],
    "head_scan": ["open_palm.l"],
    "weight_shift": ["open_palm.l"],
    "sleeve_sway": ["open_palm.l"],
    "gaze_contemplate": ["staff_grip", "open_palm.l"],
    "wrist_channel": ["staff_grip", "open_palm.l"],
    "channel_water": ["staff_grip", "open_palm.l"],
    "staff_salute": ["staff_grip", "open_palm.l"],
    "seated_meditate": ["open_palm", "open_palm.l"],
    "formal_bow": ["staff_grip", "open_palm.l"],
    "kneel_offer": ["staff_grip", "open_palm.l"],
    "levitate_channel": ["staff_grip", "open_palm.l"],
    "talisman_cast": ["staff_grip", "sword_fingers.l"],
    "sword_swing": ["grip_sword"],
    "sword_form": ["grip_sword"],
    "lunge_strike": ["grip_sword"],
    "spinning_parry": ["grip_sword"],
    "parry": ["grip_sword"],
    "recover": ["grip_sword"],
    "aerial_flourish": ["grip_sword"],
}

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
    # duel clips — the action timeline anchors attacker/defender to these
    "sword_swing": (1.0, [(0.0, []), (0.25, [P("sword_windup")]),
                          (0.45, [P("sword_hit")]), (0.7, [P("sword_hit", 0.4)]),
                          (1.0, [])]),
    "parry": (0.8, [(0.0, []), (0.35, [P("parry")]), (1.0, [P("parry")])]),
    "recover": (0.8, [(0.0, [P("sword_hit", 0.5)]), (1.0, [])]),
    # ---- minute movements: subtle ambient loops ----
    "breath": (4.0, [(0.0, [P("breath_out")]), (0.45, [P("breath_in")]),
                     (1.0, [P("breath_out")])]),
    "weight_shift": (4.0, [(0.0, []), (0.3, [P("weight_shift_l")]),
                           (0.7, [P("weight_shift_r")]), (1.0, [])]),
    "head_scan": (3.0, [(0.0, []), (0.25, [P("head_turn_l")]),
                        (0.5, []), (0.75, [P("head_turn_r")]), (1.0, [])]),
    "sleeve_sway": (3.0, [(0.0, []), (0.3, [P("sleeve_sway_l")]),
                          (0.7, [P("sleeve_sway_r")]), (1.0, [])]),
    "gaze_contemplate": (3.0, [(0.0, []), (0.3, [P("gaze_down")]),
                               (0.75, [P("gaze_down")]), (1.0, [])]),
    "wrist_channel": (2.0, [(0.0, [P("wrist_circle_a")]),
                            (0.5, [P("wrist_circle_b")]),
                            (1.0, [P("wrist_circle_a")])]),
    # ---- complex poses: multi-bone coordinated clips ----
    "formal_bow": (2.4, [(0.0, []), (0.35, [P("formal_bow")]),
                         (0.75, [P("formal_bow")]), (1.0, [])]),
    "lunge_strike": (1.2, [(0.0, []), (0.2, [P("sword_stance", 0.6)]),
                           (0.55, [P("lunge_strike")]),
                           (0.8, [P("lunge_strike", 0.5)]), (1.0, [])]),
    "spinning_parry": (0.9, [(0.0, []), (0.35, [P("spinning_parry")]),
                             (0.7, [P("spinning_parry", 0.6)]),
                             (1.0, [P("sword_stance", 0.5)])]),
    "aerial_flourish": (1.6, [(0.0, []), (0.15, [P("formal_bow", 0.3)]),
                              (0.45, [P("aerial_spin")]),
                              (0.7, [P("aerial_spin", 0.5)]),
                              (1.0, [])]),
    "levitate_channel": (5.0, [(0.0, []), (0.25, [P("levitate_channel")]),
                               (0.5, [P("levitate_channel"), P("wrist_circle_a")]),
                               (0.75, [P("levitate_channel"), P("wrist_circle_b")]),
                               (1.0, [P("levitate_channel")])]),
    "sword_form": (3.0, [(0.0, []), (0.2, [P("sword_form_high")]),
                         (0.45, [P("lunge_strike")]),
                         (0.7, [P("sword_form_low")]),
                         (0.9, [P("sword_stance")]), (1.0, [])]),
    "talisman_cast": (1.4, [(0.0, []), (0.3, [P("hand_seal")]),
                            (0.55, [P("hand_seal"), P("wrist_circle_a", 0.5)]),
                            (0.8, [P("sleeve_sway_r")]), (1.0, [])]),
    "kneel_offer": (3.0, [(0.0, []), (0.3, [P("kneel_offering")]),
                          (0.8, [P("kneel_offering")]), (1.0, [])]),
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
        cfgs = cfgs + [(GCFG[g], 1.0) for g in CLIP_GESTURES.get(name, [])
                       if g in GCFG]
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
