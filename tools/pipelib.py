"""Shared pipeline utilities: atomic JSON writes + mkdir-based file locks.

Lock model
- A lock is a directory `<target>.lock` containing `owner.json`
  {owner, pid, ts}. `os.mkdir` is the atomic create-or-fail primitive on
  both Windows and POSIX.
- Ownership is by (goal, tool) name + pid. Stage tools write their owner
  into owner.json so a second workflow can see who holds it.
- Stale sweep: a lock whose owner pid is dead, or older than
  STALE_SECONDS, is broken automatically. A lock dir without owner.json
  yet gets a 60s grace window (mkdir succeeded, json write in flight).

Usage:
    from pipelib import FileLock, LockHeld, atomic_json
    with FileLock(cdir + ".lock", owner=f"{goal}:gen", timeout=60):
        ...
"""
import json, os, time, shutil

STALE_SECONDS = 2 * 3600


def atomic_json(path, obj, indent=2):
    """Write JSON atomically: tmp file + os.replace (atomic on Win+POSIX)."""
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(obj, f, indent=indent)
    os.replace(tmp, path)


def _pid_alive(pid):
    if not pid or pid <= 0:
        return False
    if os.name == "nt":
        import ctypes
        h = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)  # QUERY_LIMITED
        if not h:
            return False
        ctypes.windll.kernel32.CloseHandle(h)
        return True
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


class LockHeld(Exception):
    def __init__(self, path, owner):
        self.path, self.owner = path, owner
        super().__init__(f"lock held: {path} (owner: {owner})")


class FileLock:
    def __init__(self, path, owner, timeout=0, stale_after=STALE_SECONDS):
        self.path, self.owner = path, owner
        self.timeout, self.stale_after = timeout, stale_after
        self.acquired = False

    def _owner_info(self):
        try:
            return json.load(open(os.path.join(self.path, "owner.json")))
        except Exception:
            return {}

    def _is_stale(self, info):
        if info:
            if info.get("pid") and not _pid_alive(info["pid"]):
                return True
            return time.time() - info.get("ts", 0) > self.stale_after
        try:  # owner.json not written yet — grace on dir mtime
            return time.time() - os.path.getmtime(self.path) > 60
        except OSError:
            return True

    def break_lock(self):
        shutil.rmtree(self.path, ignore_errors=True)

    def acquire(self):
        deadline = time.time() + self.timeout
        while True:
            try:
                os.mkdir(self.path)
            except FileExistsError:
                info = self._owner_info()
                if self._is_stale(info):
                    self.break_lock()
                    continue
                if time.time() >= deadline:
                    raise LockHeld(self.path, info.get("owner", "?"))
                time.sleep(1)
                continue
            atomic_json(os.path.join(self.path, "owner.json"),
                        {"owner": self.owner, "pid": os.getpid(), "ts": time.time()})
            self.acquired = True
            return self

    def release(self):
        if self.acquired:
            self.break_lock()
            self.acquired = False

    def __enter__(self):
        return self.acquire()

    def __exit__(self, *exc):
        self.release()
        return False
