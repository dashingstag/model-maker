"""Regenerate site/index.html — a self-contained viewer of every
component and composition, rebuilt from on-disk evidence.

  python tools/site_gen.py [--serve]

Runs automatically at the end of extract.py and publish.py, so the page
always reflects the latest rev/shots. Image and GLB paths are relative
to the repo root, so the page works opened directly from disk — 3D
previews fetch the GLB over HTTP when served, and fall back to
base64 sidecars in site/glb/ when opened via file://.
"""
import base64
import html
import json
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SITE = os.path.join(ROOT, "site")
GLB_JS = os.path.join(SITE, "glb")

STATUS_COLOR = {
    "certified": "#3fb950", "processed": "#58a6ff",
    "generated": "#d29922", "needs_human": "#f85149",
    "accepted": "#8b949e",
}


def rel(p):
    return os.path.relpath(p, SITE).replace("\\", "/")


def img_card(path, label=""):
    return (f'<a href="{rel(path)}" target="_blank" class="shot">'
            f'<img loading="lazy" src="{rel(path)}" alt="{label}">'
            f'<span>{html.escape(label or os.path.basename(path))}</span></a>')


def pngs(d, names=None):
    if not os.path.isdir(d):
        return []
    out = sorted(f for f in os.listdir(d) if f.endswith(".png"))
    if names:
        out = [f for f in out if f in names] or out
    return [os.path.join(d, f) for f in out]


def component_card(cdir):
    cid = os.path.basename(cdir)
    mpath = os.path.join(cdir, "manifest.json")
    man = json.load(open(mpath)) if os.path.exists(mpath) else {}
    bpath = os.path.join(cdir, "brief.json")
    brief = json.load(open(bpath)) if os.path.exists(bpath) else {}
    vpath = os.path.join(cdir, "unit_render", "vision.json")
    vision = json.load(open(vpath)) if os.path.exists(vpath) else {}
    cpath = os.path.join(cdir, "unit_render", "contract.json")
    contract = json.load(open(cpath)) if os.path.exists(cpath) else {}

    status = man.get("status", "unscaffolded")
    color = STATUS_COLOR.get(status, "#8b949e")
    rev = man.get("rev", "-")
    cons = man.get("constraints", {})
    ctype = man.get("type") or brief.get("type", "?")
    tris = man.get("tris")
    budget = man.get("tri_budget")
    tris_s = (f"{tris:,}/{budget:,}" if isinstance(tris, int)
              and isinstance(budget, int) else
              (f"{tris:,}" if isinstance(tris, int) else ""))
    anims = man.get("animations") or [
        a["name"] if isinstance(a, dict) else a
        for a in brief.get("anims", [])]

    glb = os.path.join(cdir, "processed", f"{cid}.glb")
    if not os.path.exists(glb):
        glb = ""
    ur = os.path.join(cdir, "unit_render")
    shots = pngs(ur)
    acc = pngs(os.path.join(cdir, "accepted"))

    verdict = vision.get("verdict")
    vcolor = {"pass": "#3fb950", "fail": "#f85149"}.get(verdict, "#8b949e")
    flags = vision.get("flags", [])
    cpass = contract.get("pass")
    hist_n = len([d for d in os.listdir(os.path.join(cdir, "history"))
                  if d.startswith("rev")]) \
        if os.path.isdir(os.path.join(cdir, "history")) else 0

    viewer = ""
    if glb:
        os.makedirs(GLB_JS, exist_ok=True)
        b64 = base64.b64encode(open(glb, "rb").read()).decode("ascii")
        js = os.path.join(GLB_JS, f"{cid}.js")
        with open(js, "w", encoding="ascii") as f:
            f.write(f'window.__GLB_B64=window.__GLB_B64||{{}};'
                    f'window.__GLB_B64["{cid}"]="{b64}";\n')
        viewer = (f'<button class="view3d" data-src="{rel(glb)}" '
                  f'data-glbjs="glb/{cid}.js" data-cid="{cid}">'
                  f'load 3D</button><div class="mv"></div>')

    prompt = html.escape(brief.get("prompt_core", ""))[:220]
    out = [f'<section class="card" id="{cid}">',
           f'<h2>{cid} <span class="badge" style="background:{color}">'
           f'{status}</span> <span class="rev">rev {rev}'
           + (f' · {hist_n} archived' if hist_n else '') + "</span></h2>",
           f'<div class="meta"><span class="type">{ctype}</span>']
    if tris_s:
        out.append(f"<span>tris {tris_s}</span>")
    if anims:
        out.append(f"<span>{len(anims)} anims: "
                   f"{html.escape(', '.join(anims[:12]))}"
                   f"{'…' if len(anims) > 12 else ''}</span>")
    if prompt:
        out.append(f'<div class="prompt">{prompt}</div>')
    out.append("</div>")
    if verdict or cpass is not None:
        out.append('<div class="gates">')
        if verdict:
            out.append(f'<span style="color:{vcolor}">vision: {verdict}'
                       f'</span>')
        if cpass is not None:
            out.append(f'<span style="color:'
                       f'{"#3fb950" if cpass else "#f85149"}">contract: '
                       f'{"pass" if cpass else "FAIL"}</span>')
        for f in flags[:6]:
            out.append(f'<span class="flag">⚑ {html.escape(str(f))}</span>')
        out.append("</div>")
    out.append(viewer)
    if acc:
        out.append('<div class="strip"><b>accepted</b>'
                   + "".join(img_card(p, "ref") for p in acc[:1]) + "</div>")
    if shots:
        out.append('<div class="strip"><b>unit_render</b>'
                   + "".join(img_card(p, os.path.splitext(
                       os.path.basename(p))[0]) for p in shots) + "</div>")
    out.append("</section>")
    return "\n".join(out)


def composition_card(gdir):
    gid = os.path.basename(gdir)
    rpath = os.path.join(gdir, "report.json")
    rep = json.load(open(rpath)) if os.path.exists(rpath) else {}
    errors = rep.get("errors") or []
    shots = pngs(os.path.join(gdir, "shots"))
    gshot = os.path.join(ROOT, "golden", gid)
    blessed = set(os.listdir(gshot)) if os.path.isdir(gshot) else set()
    fresh = {os.path.basename(s) for s in shots} & blessed
    out = [f'<section class="card wide" id="{gid}">',
           f'<h2>{gid} <span class="type">composition</span> '
           f'<span class="rev">{len(shots)} shots · '
           f'{len(fresh)}/{len(blessed)} golden-covered</span></h2>']
    out.append('<div class="gates">'
               + (f'<span style="color:#3fb950">0 errors</span>'
                  if not errors else
                  "".join(f'<span style="color:#f85149">'
                          f'{html.escape(str(e))}</span>' for e in errors))
               + "</div>")
    if shots:
        out.append('<div class="strip">'
                   + "".join(img_card(p, os.path.splitext(
                       os.path.basename(p))[0]) for p in shots) + "</div>")
    out.append("</section>")
    return "\n".join(out)


PAGE = """<!doctype html><meta charset="utf-8">
<title>model-maker — asset viewer</title>
<style>
  :root {{ color-scheme: dark }}
  body {{ background:#0d1117; color:#c9d1d9; font:14px/1.45 system-ui;
         margin:0; padding:24px }}
  h1 {{ font-size:20px }} h2 {{ font-size:16px; font-weight:600 }}
  .bar {{ color:#8b949e; margin-bottom:20px }}
  nav a {{ color:#58a6ff; margin-right:12px; text-decoration:none }}
  .card {{ background:#161b22; border:1px solid #30363d; border-radius:8px;
          padding:16px; margin:0 0 18px }}
  .badge {{ color:#0d1117; border-radius:10px; padding:1px 9px;
           font-size:12px; vertical-align:middle }}
  .rev,.type {{ color:#8b949e; font-size:12px; font-weight:400 }}
  .meta {{ display:flex; gap:14px; flex-wrap:wrap; color:#8b949e;
          margin:6px 0 }}
  .prompt {{ flex-basis:100%; color:#7d8590; font-style:italic }}
  .gates {{ display:flex; gap:14px; flex-wrap:wrap; margin:6px 0 }}
  .flag {{ color:#d29922; font-size:12px }}
  .strip {{ display:flex; gap:8px; overflow-x:auto; padding:10px 0 2px;
           align-items:flex-start }}
  .strip b {{ flex:0 0 auto; color:#8b949e; font-size:11px;
             text-transform:uppercase; padding-top:40px }}
  a.shot {{ flex:0 0 auto; width:150px; text-decoration:none }}
  a.shot img {{ width:150px; height:94px; object-fit:cover;
               border:1px solid #30363d; border-radius:6px }}
  a.shot span {{ display:block; color:#8b949e; font-size:10px;
                overflow:hidden; text-overflow:ellipsis; white-space:nowrap }}
  .view3d {{ background:#21262d; color:#c9d1d9; border:1px solid #30363d;
            border-radius:6px; padding:4px 12px; cursor:pointer; margin:8px 0 }}
  .mv {{ position:relative }}
  .mv canvas {{ width:100%; height:340px; border:1px solid #30363d;
               border-radius:6px; background:#0d1117; display:block }}
  .mv .ctl {{ display:flex; gap:10px; align-items:center; padding:6px 2px;
             font-size:12px; color:#8b949e }}
  .mv select {{ background:#21262d; color:#c9d1d9; border:1px solid #30363d;
               border-radius:6px; padding:3px 8px; font-size:12px }}
  .mv label {{ display:flex; gap:4px; align-items:center; cursor:pointer }}
  .mv .hint {{ margin-left:auto; font-style:italic }}
</style>
<h1>model-maker — asset viewer</h1>
<div class="bar">regenerated {ts} · {nc} components · {ng} compositions ·
 works from file:// or <code>python tools/site_gen.py --serve</code></div>
<nav>{nav}</nav>
{body}
<script src="vendor/three.min.js"></script>
<script src="vendor/GLTFLoader.js"></script>
<script src="vendor/OrbitControls.js"></script>
<script>
for (const b of document.querySelectorAll(".view3d")) {{
  b.onclick = () => {{
    if (b.disabled) return;
    b.disabled = true; b.textContent = "loading…";
    const host = b.parentElement.querySelector(".mv");
    try {{ loadGlb(host, b.dataset.src, b.dataset.glbjs, b.dataset.cid); }}
    catch (e) {{ b.textContent = "3D failed to load (see console)"; }}
  }};
}}
function loadGlb(host, src, glbjs, cid) {{
  const W = host.clientWidth || 900, H = 340;
  const scene = new THREE.Scene();
  scene.background = new THREE.Color(0x0d1117);
  const cam = new THREE.PerspectiveCamera(40, W / H, 0.01, 100);
  const ren = new THREE.WebGLRenderer({{ antialias: true }});
  ren.setSize(W, H); ren.outputEncoding = THREE.sRGBEncoding;
  const bar = document.createElement("div");
  bar.className = "ctl";
  host.appendChild(ren.domElement);
  host.appendChild(bar);
  scene.add(new THREE.HemisphereLight(0xffffff, 0x445566, 1.1));
  const dir = new THREE.DirectionalLight(0xffffff, 0.7);
  dir.position.set(2, 4, 3); scene.add(dir);
  const loader = new THREE.GLTFLoader();
  const fail = () => {{
    host.innerHTML = "<p style='color:#f85149'>GLB load failed — " +
      "run <code>python tools/site_gen.py --serve</code> or regenerate</p>";
  }};
  const fromBytes = (buf) => loader.parse(buf, "", onGlb, fail);
  const viaScript = () => {{
    const s = document.createElement("script");
    s.src = glbjs;
    s.onload = () => {{
      const b64 = window.__GLB_B64 && window.__GLB_B64[cid];
      if (!b64) return fail();
      const bin = atob(b64), bytes = new Uint8Array(bin.length);
      for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
      fromBytes(bytes.buffer);
    }};
    s.onerror = fail;
    document.head.appendChild(s);
  }};
  fetch(src).then(r => {{
    if (!r.ok) throw new Error(r.status);
    return r.arrayBuffer();
  }}).then(fromBytes).catch(viaScript);
  function onGlb(g) {{
    scene.add(g.scene);
    const box = new THREE.Box3().setFromObject(g.scene);
    const c = box.getCenter(new THREE.Vector3());
    const s = box.getSize(new THREE.Vector3()).length();
    cam.position.set(c.x + s * 0.55, c.y + s * 0.2, c.z + s * 0.75);
    const ctl = new THREE.OrbitControls(cam, ren.domElement);
    ctl.target.copy(c);
    ctl.enableDamping = true;

    const mix = new THREE.AnimationMixer(g.scene);
    const actions = {{}};
    for (const clip of g.animations)
      actions[clip.name] = mix.clipAction(clip);

    let cur = null;
    const sel = document.createElement("select");
    const names = ["paused (hold frame)"].concat(g.animations.map(a => a.name));
    for (const n of names) {{
      const o = document.createElement("option");
      o.value = n; o.textContent = n; sel.appendChild(o);
    }}
    function play(name) {{
      if (cur) cur.stop();
      if (name !== "paused (hold frame)") {{
        mix.stopAllAction();
        cur = actions[name];
        if (cur) {{
          cur.reset();
          cur.setLoop(THREE.LoopRepeat, Infinity).play();
        }}
      }} else {{ mix.stopAllAction(); cur = null; }}
    }}
    sel.onchange = () => play(sel.value);
    const prefer = g.animations.some(a => a.name === "idle")
      ? "idle" : names[names.length - 1];
    sel.value = prefer;
    bar.appendChild(document.createTextNode("pose"));
    bar.appendChild(sel);

    const spin = document.createElement("label");
    const box2 = document.createElement("input");
    box2.type = "checkbox";
    box2.onchange = () => {{ ctl.autoRotate = box2.checked;
                            ctl.autoRotateSpeed = 2.0; }};
    spin.appendChild(box2);
    spin.appendChild(document.createTextNode("auto-rotate"));
    bar.appendChild(spin);
    const hint = document.createElement("span");
    hint.className = "hint";
    hint.textContent = "drag = orbit · wheel = zoom · right-drag = pan";
    bar.appendChild(hint);
    play(prefer);

    const clk = new THREE.Clock();
    (function tick() {{
      requestAnimationFrame(tick);
      mix.update(clk.getDelta());
      ctl.update(); ren.render(scene, cam);
    }})();
  }}
}}
</script>
<script>
// live reload — /__ver is served only by `site_gen.py --serve`; on
// file:// or any fetch error this quietly does nothing
let __ver = null;
setInterval(() => {{
  fetch("/__ver", {{cache: "no-store"}}).then(r => r.json()).then(j => {{
    if (__ver === null) {{ __ver = j.v; }}
    else if (j.v !== __ver) {{ location.reload(); }}
  }}).catch(() => {{}});
}}, 3000);
</script>
"""


def build():
    os.makedirs(SITE, exist_ok=True)
    if os.path.isdir(GLB_JS):           # stale sidecars for removed comps
        for f in os.listdir(GLB_JS):
            os.remove(os.path.join(GLB_JS, f))
    comp_root = os.path.join(ROOT, "pipeline", "components")
    goal_root = os.path.join(ROOT, "pipeline", "composition")
    comps = sorted(os.path.join(comp_root, d)
                   for d in os.listdir(comp_root)
                   if os.path.isdir(os.path.join(comp_root, d)))
    goals = sorted(os.path.join(goal_root, d)
                   for d in os.listdir(goal_root)
                   if os.path.isdir(os.path.join(goal_root, d)))
    body = [composition_card(g) for g in goals]
    body += [component_card(c) for c in comps]
    ids = [os.path.basename(g) for g in goals] + \
          [os.path.basename(c) for c in comps]
    nav = "".join(f'<a href="#{i}">{i}</a>' for i in ids)
    page = PAGE.format(ts=time.strftime("%Y-%m-%d %H:%M:%S"),
                       nc=len(comps), ng=len(goals),
                       nav=nav, body="\n".join(body))
    # atomic write — a reader must never see a half-written page
    tmp = os.path.join(SITE, "index.html.tmp")
    open(tmp, "w", encoding="utf-8").write(page)
    os.replace(tmp, os.path.join(SITE, "index.html"))
    print(f"site -> {os.path.join(SITE, 'index.html')} "
          f"({len(comps)} components, {len(goals)} compositions)")


WATCH_EXT = (".json", ".glb", ".png", ".jpg", ".jpeg", ".md")


def signature():
    """(max mtime_ns, file count) over the asset tree — any add,
    modify or delete under pipeline/ changes it."""
    latest, count = 0, 0
    for base, _, files in os.walk(os.path.join(ROOT, "pipeline")):
        for f in files:
            if not f.endswith(WATCH_EXT):
                continue
            count += 1
            try:
                latest = max(latest, os.stat(
                    os.path.join(base, f)).st_mtime_ns)
            except OSError:
                pass
    return latest, count


def main():
    build()
    if "--serve" in sys.argv:
        import functools
        import http.server
        import json as _json
        import socketserver
        import threading
        import webbrowser

        state = {"v": 0, "sig": signature()}
        lock = threading.Lock()

        def watch():
            while True:
                time.sleep(3)
                try:
                    sig = signature()
                    if sig != state["sig"]:
                        with lock:
                            state["sig"] = sig
                            build()
                            state["v"] += 1
                except Exception as e:     # a bad tree state must never
                    print("site watch:", e)  # kill the server

        threading.Thread(target=watch, daemon=True).start()

        class Handler(http.server.SimpleHTTPRequestHandler):
            def translate_path(self, path):
                # /site/index.html/… -> /site/index.html (browsers that
                # append a slash, incl. favicon fetches)
                if "/index.html/" in path:
                    path = path.split("/index.html/", 1)[0] + "/index.html"
                return super().translate_path(path)

            def do_GET(self):
                if self.path.split("?", 1)[0] == "/__ver":
                    body = _json.dumps({"v": state["v"]}).encode()
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(body)))
                    self.send_header("Cache-Control", "no-store")
                    self.end_headers()
                    self.wfile.write(body)
                    return
                super().do_GET()

        port = 8471
        handler = functools.partial(Handler, directory=ROOT)
        print(f"serving {ROOT} at http://127.0.0.1:{port}/site/ "
              f"(watching pipeline/ for changes)")
        webbrowser.open(f"http://127.0.0.1:{port}/site/")
        socketserver.ThreadingTCPServer(
            ("127.0.0.1", port), handler).serve_forever()


main()
