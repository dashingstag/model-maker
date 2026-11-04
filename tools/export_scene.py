"""Export the published composition as a Godot .tscn scene artifact.

  python tools/export_scene.py <goal>

Reads pipeline/composition/<goal>/jobs.json (the resolved composition
publish emitted) and writes dist/<goal>/scene.tscn — a static Node2D
composition: parallax layers, member sprites (feet pivots, normal maps),
ui images, glb members as SubViewport + instanced PackedScene composites,
attached prop sprites, and the rig's point light. Asset paths stay
`res://assets/components/<id>/...` — drop dist/<goal>/components/ into a
project's assets/ to use it. Runtime behaviors (patrol, action clocks,
shot cameras) live in the harness, not the exported scene.
"""
import json
import os
import sys
from pipelib import atomic_json

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def esc(s):
    return s.replace('"', '\\"')


def c2v(c):
    """'#rrggbb' -> Color(...)"""
    c = c.lstrip("#")
    r, g, b = (int(c[i:i + 2], 16) / 255 for i in (0, 2, 4))
    a = int(c[6:8], 16) / 255 if len(c) == 8 else 1.0
    return f"Color({r:.4g}, {g:.4g}, {b:.4g}, {a:.4g})"


def main(goal):
    job_p = os.path.join(ROOT, "pipeline", "composition", goal, "jobs.json")
    job = json.load(open(job_p))
    comp = job["composition"]
    rig = job.get("rig", {})
    ext, sub, nodes = [], [], []
    nid = [0]

    def eid():
        nid[0] += 1
        return nid[0]

    def ext_res(type_, path):
        i = f"e{eid()}"
        ext.append(f'[ext_resource type="{type_}" path="{path}" id="{i}"]')
        return f'ExtResource("{i}")'

    def sub_res(type_, props):
        i = f"s{eid()}"
        body = "\n".join(f"{k} = {v}" for k, v in props.items())
        sub.append(f'[sub_resource type="{type_}" id="{i}"]\n{body}')
        return f'SubResource("{i}")'

    def node(name, type_, parent, props, inst=None):
        line = f'[node name="{esc(name)}" type="{type_}"'
        if parent is not None:
            line += f' parent="{esc(parent)}"'
        if inst:
            line += f" instance={inst}"
        line += "]"
        body = "\n".join(f"{k} = {v}" for k, v in props.items())
        nodes.append(line + ("\n" + body if body else ""))

    comp_dir = comp["components_dir"]
    node(goal, "Node2D", None, {})

    cm = rig.get("canvas_modulate")
    if cm:
        node("CanvasModulate", "CanvasModulate", ".", {"color": c2v(cm)})

    # parallax layers — mirrored copies at +-2560 like the harness
    node("ParallaxBG", "Node2D", ".", {})
    for L in comp.get("layers", []):
        tex = ext_res("Texture2D", f'{comp_dir}/{L["id"]}/bg.png')
        lx = -300.0 * L["factor"]
        y = L.get("y_off", 0)
        for dx in (-2560.0, 0.0, 2560.0):
            name = L["id"] if dx == 0.0 else f'{L["id"]}_f{int(dx)}'
            node(name, "Sprite2D", "ParallaxBG", {
                "position": f"Vector2({dx + lx}, {y})",
                "scale": "Vector2(1, 1)",
                "centered": "false",
                "texture": tex})

    members = comp.get("members", [])
    pos = {}

    def glb_stage(m):
        """SubViewport + env/light/cam + instanced glb for a 3D member."""
        vname = m["id"] + "_vp"
        node(vname, "SubViewport", ".", {
            "size": "Vector2i(360, 560)",
            "transparent_bg": "true",
            "own_world_3d": "true",
            "render_target_update_mode": "4"})
        env = sub_res("Environment", {
            "background_mode": "1",
            "background_color": "Color(0, 0, 0, 0)",
            "ambient_light_source": "2",
            "ambient_light_color": "Color(0.6, 0.62, 0.7, 1)",
            "ambient_light_energy": "0.5"})
        node("WorldEnvironment", "WorldEnvironment", vname, {"environment": env})
        node("Sun", "DirectionalLight3D", vname, {
            "rotation": "Vector3(-0.785398, -0.436332, 0)"})
        node("Cam", "Camera3D", vname, {
            "transform": ("Transform3D(1, 0, 0, 0, 0.939373, -0.342898, "
                          "0, 0.342898, 0.939373, 0, 1.35, 3.4)"),
            "current": "true"})
        g = ext_res("PackedScene", f'{comp_dir}/{m["id"]}/{m["glb"]}')
        node("Model", "Node3D", vname, {}, inst=g)
        vt = sub_res("ViewportTexture", {"viewport_path": f'NodePath("{vname}")'})
        return vt

    for m in members:
        kind = m.get("kind")
        x, y = m["x"], m["y"]
        pos[m["id"]] = (x, y)
        if kind in ("sprite", "variant"):
            base = f'{comp_dir}/{m["id"]}'
            dif = ext_res("Texture2D", base + "/sprite_idle.png")
            np = base + "/sprite_idle_n.png"
            tex = dif
            if os.path.exists(os.path.join(
                    ROOT, "pipeline", "components", m["id"],
                    "processed", "sprite_idle_n.png")):
                nrm = ext_res("Texture2D", np)
                tex = sub_res("CanvasTexture", {
                    "diffuse_texture": dif, "normal_texture": nrm})
            h = m.get("h_px", 384)
            node(m["id"], "Sprite2D", ".", {
                "position": f"Vector2({x}, {y})",
                "offset": f"Vector2(0, -{h / 2})",
                "scale": "Vector2(1, 1)",
                "texture": tex})
        elif kind in ("ui", "ui_image"):
            img = "portrait.png" if kind == "ui" else "image.png"
            t = ext_res("Texture2D", f'{comp_dir}/{m["id"]}/{img}')
            w, h = m.get("w", 300), m.get("h", 500)
            node(m["id"], "TextureRect", ".", {
                "offset_left": str(x), "offset_top": str(y),
                "offset_right": str(x + w), "offset_bottom": str(y + h),
                "texture": t, "expand_mode": "1", "stretch_mode": "6"})
        elif kind == "glb":
            vt = glb_stage(m)
            node(m["id"], "Sprite2D", ".", {
                "position": f"Vector2({x}, {y})",
                "offset": "Vector2(0, -280)",
                "texture": vt})

    # attached 2D props — siblings placed at host pos + authored offset
    for at in comp.get("layout", {}).get("attach", []):
        tgt = at.get("to", "")
        if tgt not in pos:
            continue
        hx, hy = pos[tgt]
        off = at.get("offset", [0, 0])
        base = f'{comp_dir}/{at["prop"]}'
        t = ext_res("Texture2D", base + "/sprite_idle.png")
        node(f'{at["prop"]}_on_{tgt}', "Sprite2D", ".", {
            "position": f"Vector2({hx + off[0]}, {hy + off[1]})",
            "texture": t})

    # rig point light anchored over the first member, else canvas center
    l2 = rig.get("light_2d")
    if l2:
        anchor = comp.get("layout", {}).get("light_anchor", {}).get("offset", [40, -290])
        hx, hy = next(iter(pos.values()), (640, 480))
        grad = sub_res("Gradient", {
            "colors": "PackedColorArray(1, 1, 1, 1, 1, 1, 1, 0)"})
        gt = sub_res("GradientTexture2D", {
            "width": "512", "height": "512",
            "fill": "1", "fill_from": "Vector2(0.5, 0.5)",
            "fill_to": "Vector2(1, 0.5)", "gradient": grad})
        node("KeyLight", "PointLight2D", ".", {
            "position": f"Vector2({hx + anchor[0]}, {hy + anchor[1]})",
            "color": c2v(l2.get("color", "#ffd9a0")),
            "energy": str(l2.get("energy", 2.0)),
            "texture_scale": str(l2.get("texture_scale", 3.0)),
            "texture": gt})

    # default framing mirrors the harness's wide shot: whole 2x canvas
    node("PreviewCam", "Camera2D", ".", {
        "position": "Vector2(1280, 720)",
        "zoom": "Vector2(0.5, 0.5)",
        "enabled": "false"})

    tscn = (f'[gd_scene load_steps={len(ext) + len(sub) + 1} format=3]\n\n'
            + "\n\n".join(ext + sub + nodes) + "\n")
    dist = os.path.join(ROOT, "dist", goal)
    os.makedirs(dist, exist_ok=True)
    out = os.path.join(dist, "scene.tscn")
    with open(out, "w") as f:
        f.write(tscn)

    mp = os.path.join(dist, "manifest.json")
    man = json.load(open(mp)) if os.path.exists(mp) else {"goal": goal}
    man["scene_tscn"] = "scene.tscn"
    spec_p = os.path.join(ROOT, "pipeline", "composition", goal, "spec.json")
    spec = json.load(open(spec_p)) if os.path.exists(spec_p) else {}
    man["components"] = {cid: comp.get("glbs", {}).get(cid, "")
                         for cid in spec.get("components",
                                            [m["id"] for m in members])}
    atomic_json(mp, man)
    print(f"{goal}: scene.tscn -> {out} "
          f"({len(members)} members, {len(comp.get('layers', []))} layers)")


if __name__ == "__main__":
    main(sys.argv[1])
