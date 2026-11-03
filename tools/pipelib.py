"""Shared pipeline utilities: atomic JSON writes + mkdir-based file locks.

Lock model
- A lock is a directory `<target>.lock` containing `owner.json`
  {owner, pid, ts, token}. `os.mkdir` is the atomic create-or-fail
  primitive on both Windows and POSIX.
- Holders heartbeat `ts` from a daemon thread every HEARTBEAT seconds, so
  long CPU ComfyUI batches never look stale while their process lives.
- Stale = owner pid dead, or heartbeat older than STALE_SECONDS. A lock dir
  without owner.json yet gets a 60s grace window (json write in flight).
- Breaking a stale lock is race-safe: the breaker atomically renames the
  dir to a unique tombstone, then verifies the captured owner token is the
  one it judged stale; if a fresh owner was captured instead, it is
  restored.
- release() only deletes the lock if the token is still ours.

Usage:
    from pipelib import FileLock, LockHeld, atomic_json
    with FileLock(cdir + ".lock", owner=f"{goal}:gen", timeout=60):
        ...
"""
import json, os, time, shutil, threading, uuid

STALE_SECONDS = 2 * 3600
HEARTBEAT = 60


def atomic_json(path, obj, indent=2, retries=20):
    """Write JSON atomically: unique tmp file + os.replace.
    Retries replace on Windows sharing violations (reader holds the file)."""
    tmp = f"{path}.{os.getpid()}.{uuid.uuid4().hex[:6]}.tmp"
    with open(tmp, "w") as f:
        json.dump(obj, f, indent=indent)
    for i in range(retries):
        try:
            os.replace(tmp, path)
            return
        except PermissionError:
            if i == retries - 1:
                os.remove(tmp)
                raise
            time.sleep(0.05 * (i + 1))


def _pid_alive(pid):
    if not pid or pid <= 0:
        return False
    if os.name == "nt":
        import ctypes
        k32 = ctypes.windll.kernel32
        h = k32.OpenProcess(0x1000, False, pid)  # QUERY_LIMITED_INFORMATION
        if not h:
            # 87 = ERROR_INVALID_PARAMETER: no such pid. Anything else
            # (e.g. 5 access denied for elevated procs) -> assume alive.
            return k32.GetLastError() != 87
        code = ctypes.c_ulong()
        ok = k32.GetExitCodeProcess(h, ctypes.byref(code))
        k32.CloseHandle(h)
        return not ok or code.value == 259  # STILL_ACTIVE
    try:
        os.kill(pid, 0)
        return True
    except PermissionError:
        return True
    except OSError:
        return False


class LockHeld(Exception):
    def __init__(self, path, owner):
        self.path, self.owner = path, owner
        super().__init__(f"lock held: {path} (owner: {owner})")


def _read_owner(d):
    try:
        with open(os.path.join(d, "owner.json")) as f:
            return json.load(f)
    except Exception:
        return {}


class FileLock:
    def __init__(self, path, owner, timeout=0, stale_after=STALE_SECONDS):
        self.path, self.owner = path, owner
        self.timeout, self.stale_after = timeout, stale_after
        self.acquired = False
        self.token = None
        self._stop = threading.Event()
        self._hb = None

    def _owner_info(self):
        return _read_owner(self.path)

    def _is_stale(self, info):
        if info:
            if info.get("pid") and not _pid_alive(info["pid"]):
                return True
            return time.time() - info.get("ts", 0) > self.stale_after
        try:  # owner.json not written yet — grace on dir mtime
            return time.time() - os.path.getmtime(self.path) > 60
        except OSError:
            return False  # vanished/unstatable: let the mkdir loop retry

    def _break_if_still(self, judged):
        """Race-safe break: capture via atomic rename, verify, else restore."""
        tomb = f"{self.path}.breaking-{os.getpid()}-{uuid.uuid4().hex[:6]}"
        try:
            os.rename(self.path, tomb)
        except OSError:
            return  # someone else broke/released it first
        if _read_owner(tomb).get("token") != judged.get("token"):
            try:
                os.rename(tomb, self.path)  # captured a fresh lock: restore
                return
            except OSError:
                pass  # a third party re-created it; tombstone is orphaned
        shutil.rmtree(tomb, ignore_errors=True)

    def _write_owner(self):
        atomic_json(os.path.join(self.path, "owner.json"),
                    {"owner": self.owner, "pid": os.getpid(),
                     "ts": time.time(), "token": self.token})

    def _heartbeat(self):
        while not self._stop.wait(HEARTBEAT):
            if _read_owner(self.path).get("token") != self.token:
                return  # lost the lock; stop touching it
            try:
                self._write_owner()
            except OSError:
                return

    def acquire(self):
        deadline = time.time() + self.timeout
        while True:
            try:
                os.mkdir(self.path)
            except FileExistsError:
                info = self._owner_info()
                if self._is_stale(info):
                    self._break_if_still(info)
                    continue
                if time.time() >= deadline:
                    raise LockHeld(self.path, info.get("owner", "?"))
                time.sleep(1)
                continue
            self.token = uuid.uuid4().hex
            self._write_owner()
            self.acquired = True
            self._stop.clear()
            self._hb = threading.Thread(target=self._heartbeat, daemon=True)
            self._hb.start()
            return self

    def release(self):
        if not self.acquired:
            return
        self._stop.set()
        if self._owner_info().get("token") == self.token:
            shutil.rmtree(self.path, ignore_errors=True)
        self.acquired = False

    def __enter__(self):
        return self.acquire()

    def __exit__(self, *exc):
        self.release()
        return False


def name_of(entry):
    """Pose/anim/variant entries may be strings or {name|id: ...} objects."""
    if isinstance(entry, dict):
        return entry.get("name") or entry.get("id")
    return entry


def resolve_ref(root, ref):
    """@kind/name[.key.path] -> value from shared/<kind>/<name>.json."""
    kind, rest = ref[1:].split("/", 1)
    fname, _, keypath = rest.partition(".")
    with open(os.path.join(root, "shared", kind, fname + ".json")) as f:
        data = json.load(f)
    for k in filter(None, keypath.split(".")):
        data = data[k]
    return data
