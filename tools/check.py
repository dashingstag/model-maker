"""check_id runner — the ledger contract's executable half.

  python tools/check.py                 # list registered checks
  python tools/check.py <id> [arg]      # run one; exit 0/1
  python tools/check.py all             # run every parameterized=none

checks.json maps id -> {cmd, desc, arg?}. Commands run from repo root.
Use in BUG_LEDGER rows as `check_id: <id>` so triage notes stay runnable.
"""
import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REG = os.path.join(ROOT, "tools", "checks.json")


def load():
    return json.load(open(REG))


def run_check(cid, arg):
    reg = load()
    c = reg.get(cid)
    if not c and ":" in cid:
        base, _, a2 = cid.rpartition(":")
        c = reg.get(base + ":{arg}")
        if c and arg is None:
            arg = a2
            cid = base + ":{arg}"
    if not c:
        sys.exit(f"unknown check_id '{cid}' — see `python tools/check.py`")
    cmd = c["cmd"]
    if "{arg}" in cmd:
        if not arg:
            sys.exit(f"{cid} takes an argument: {c.get('arg_hint', '<value>')}")
        cmd = cmd.replace("{arg}", arg)
    elif arg:
        sys.exit(f"{cid} takes no argument")
    r = subprocess.run(cmd, shell=True, cwd=ROOT,
                       capture_output=True, text=True)
    out = (r.stdout + r.stderr).strip()
    print(out[-800:] if out else "(no output)")
    print(f"{cid}: {'PASS' if r.returncode == 0 else 'FAIL'}")
    return r.returncode


def main():
    if len(sys.argv) < 2:
        for cid, c in load().items():
            print(f"  {cid:<28} {c['desc']}"
                  + (f"  [arg: {c['arg_hint']}]" if "{arg}" in c["cmd"] else ""))
        return
    if sys.argv[1] == "all":
        fails = [cid for cid, c in load().items()
                 if "{arg}" not in c["cmd"] and run_check(cid, None)]
        sys.exit(1 if fails else 0)
    sys.exit(run_check(sys.argv[1],
                       sys.argv[2] if len(sys.argv) > 2 else None))


if __name__ == "__main__":
    main()
