"""Goal driver — one command runs the mechanical stages end-to-end.

  python tools/run_goal.py briefs/<goal>.brief.json [--wait S] [--no-harness]

Sequence: scaffold -> component C-track (mechanical stages only) ->
publish -> supervised harness run -> export_scene -> golden_check ->
dist manifest. Judgment gates (curation picks, vision verdicts) stop the
run honestly: it reports what needs a human/agent decision rather than
certifying blind.

Harness supervision (borrowed from mixar's sandbox_supervisor): the
Godot runner is spawned in its own process group, writes heartbeat
records to .run/harness-<pid>.json as it advances stages, and is reaped
on completion or killed when its heartbeat stalls. Stale records from
dead pids are swept on entry — no more 7MB zombies holding the lock.
"""
import json
import os
import subprocess
import sys
import time
from pipelib import (FileLock, LockHeld, atomic_json, instances,
                     register_instance, heartbeat_instance, _pid_alive)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENV = json.load(open(os.path.join(ROOT, "tools", "env.json")))
GODOT = ENV["godot"]
PY = sys.executable
STALL_S = 180.0          # heartbeat older than this while alive = wedged
POLL_S = 2.0

def tool(name):
    return os.path.join(ROOT, "tools", name)


def run(cmd, **kw):
    r = subprocess.run(cmd, capture_output=True, text=True, **kw)
    return r


def sweep_stale():
    """Kill live stale harness records before starting (left-over locks)."""
    for rec in instances(ROOT, "harness"):
        if rec.get("alive") and _pid_alive(rec.get("pid", -1)):
            hb = time.time() - rec.get("heartbeat", 0)
            if hb > STALL_S:
                print(f"run_goal: reaping stalled harness pid {rec['pid']} "
                      f"(stage={rec.get('stage')}, stale {hb:.0f}s)")
                kill_pid(rec["pid"])


def kill_pid(pid):
    if os.name == "nt":
        subprocess.run(["taskkill", "//PID", str(pid), "//F", "//T"],
                       capture_output=True)
    else:
        try:
            os.killpg(pid, 15)
        except OSError:
            pass


def spawn_harness(job_path, log_path):
    """Spawn the Godot runner detached in its own group; return Popen."""
    kw = {"stdout": open(log_path, "w"), "stderr": subprocess.STDOUT}
    if os.name == "nt":
        kw["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        kw["start_new_session"] = True
    return subprocess.Popen([GODOT, "--path",
                             os.path.join(ROOT, "godot"), "--", job_path], **kw)


def supervise(proc, job_path, stall_s=STALL_S):
    """Poll the child's heartbeat record; kill on stall or parent death."""
    rec_path = None
    last_hb = time.time()
    stage = "spawn"
    while proc.poll() is None:
        time.sleep(POLL_S)
        run_dir = os.path.join(ROOT, ".run")
        pid = proc.pid
        cand = os.path.join(run_dir, f"harness-{pid}.json")
        if os.path.exists(cand):
            try:
                rec = json.load(open(cand))
            except (OSError, ValueError):
                rec = {}
            if rec.get("heartbeat", 0) > last_hb - POLL_S or rec_path is None:
                last_hb = max(last_hb, rec.get("heartbeat", last_hb))
                stage = rec.get("stage", stage)
                rec_path = cand
        if time.time() - last_hb > stall_s:
            print(f"run_goal: harness stalled at '{stage}' — killing {pid}")
            kill_pid(pid)
            return {"ok": False, "reason": f"stalled at {stage}"}
    rc = proc.wait()
    return {"ok": rc == 0, "rc": rc}


def component_track(cid, wait):
    """Run the mechanical C-stages; return 'certified'|'blocked:<gate>'."""
    d = os.path.join(ROOT, "pipeline", "components", cid)
    man_p = os.path.join(d, "manifest.json")
    man = json.load(open(man_p)) if os.path.exists(man_p) else {}
    st = man.get("status")
    if st == "certified":
        return "certified"
    brief = json.load(open(os.path.join(d, "brief.json")))
    if st in (None, "new", "needs_human"):
        if st == "needs_human":
            return "blocked:needs_human"
        r = run([PY, tool("gen_component.py"), cid] +
                (["--wait", str(wait)] if wait else []), cwd=ROOT)
        if r.returncode:
            return f"blocked:gen — {r.stderr.strip()[:120]}"
    # extract
    r = run([PY, tool("extract.py"), cid], cwd=ROOT)
    if r.returncode:
        return f"blocked:extract — {r.stderr.strip()[:120]}"
    # vision — mechanical for review:auto? verdict still required; report it
    vj = os.path.join(d, "unit_render", "vision.json")
    v = json.load(open(vj)) if os.path.exists(vj) else {}
    if v.get("verdict") == "pass":
        run([PY, tool("vision.py"), "certify", cid], cwd=ROOT)
        man = json.load(open(man_p))
        return "certified" if man.get("status") == "certified" else "blocked:certify"
    return "blocked:vision"


def main(brief_path, wait, no_harness):
    brief = json.load(open(brief_path))
    goal = brief["goal"]
    register_instance(ROOT, "run_goal", os.getpid(), {"goal": goal})
    sweep_stale()

    # 1. scaffold (validates + writes spec.json + creates component dirs)
    r = run([PY, tool("scaffold.py"), brief_path], cwd=ROOT)
    print(r.stdout.strip() or r.stderr.strip())
    if r.returncode:
        sys.exit(f"run_goal: scaffold failed for {goal}")

    # 2. component tracks — mechanical stages only
    comp_dir = os.path.join(ROOT, "pipeline", "composition", goal)
    spec = json.load(open(os.path.join(comp_dir, "spec.json")))
    states = {cid: component_track(cid, wait) for cid in spec["components"]}
    blocked = {c: s for c, s in states.items() if s != "certified"}
    for c, s in states.items():
        print(f"  {c}: {s}")
    if blocked:
        print(f"run_goal: {len(blocked)} component(s) await a gate "
              f"(curation/vision) — run the judgment steps, then rerun me")
        sys.exit(1)

    # 3. publish
    r = run([PY, tool("publish.py"), goal] + (["--wait", str(wait)] if wait else []),
            cwd=ROOT)
    print((r.stdout or r.stderr).strip().splitlines()[-1])
    if r.returncode:
        sys.exit("run_goal: publish blocked")

    run([PY, tool("layout_map.py"), goal], cwd=ROOT)

    # 4. supervised harness
    if not no_harness:
        job_p = os.path.join(comp_dir, "jobs.json")
        log_p = os.path.join(comp_dir, "harness.log")
        proc = spawn_harness(job_p, log_p)
        heartbeat_instance(ROOT, "run_goal", os.getpid(),
                           stage=f"harness pid {proc.pid}")
        res = supervise(proc, job_p)
        rep_p = os.path.join(comp_dir, "report.json")
        if not res["ok"] or not os.path.exists(rep_p):
            sys.exit(f"run_goal: harness failed — {res}; see {log_p}")
        rep = json.load(open(rep_p))
        bad = [s for s, v in rep.get("shot_expect", {}).items()
               if any(c.get("pass") is False for c in v.values())]
        if rep.get("composition", {}).get("missing_assets"):
            bad.append("missing_assets")
        if bad:
            print(f"run_goal: harness flags {bad} — triage before packaging")
            sys.exit(1)

    # 5. package: scene export + golden check + dist manifest
    r = run([PY, tool("export_scene.py"), goal], cwd=ROOT)
    print(r.stdout.strip())
    if not no_harness:
        gc = run([PY, tool("golden_check.py"), goal], cwd=ROOT)
        print("golden:", "PASS" if gc.returncode == 0 else "DRIFT — inspect")
    print(f"run_goal: {goal} complete")


if __name__ == "__main__":
    w = (int(sys.argv[sys.argv.index("--wait") + 1])
         if "--wait" in sys.argv else 0)
    main(sys.argv[1], w, "--no-harness" in sys.argv)
