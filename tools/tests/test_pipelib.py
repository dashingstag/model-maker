"""pipelib tests: locks, stale recovery, race-safe break, atomic JSON.

  python -m unittest discover -s tools/tests -v
"""
import json, os, subprocess, sys, tempfile, threading, time, unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import pipelib
from pipelib import FileLock, LockHeld, atomic_json, name_of, resolve_ref


class AtomicJsonTest(unittest.TestCase):
    def test_roundtrip_and_no_tmp_left(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "m.json")
            atomic_json(p, {"a": 1})
            atomic_json(p, {"a": 2})
            self.assertEqual(json.load(open(p)), {"a": 2})
            self.assertEqual(os.listdir(d), ["m.json"])

    def test_concurrent_writers_never_tear(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "m.json")
            atomic_json(p, {"n": -1})
            errors = []

            def writer(n):
                for i in range(30):
                    atomic_json(p, {"n": n, "pad": "x" * 2000})

            def reader():
                for _ in range(200):
                    try:
                        json.load(open(p))
                    except json.JSONDecodeError as e:
                        errors.append(e)
                    except PermissionError:
                        pass  # Windows: replace in progress — not a torn read
            ts = [threading.Thread(target=writer, args=(n,)) for n in range(3)]
            ts.append(threading.Thread(target=reader))
            [t.start() for t in ts]
            [t.join() for t in ts]
            self.assertEqual(errors, [])
            self.assertFalse([f for f in os.listdir(d) if f.endswith(".tmp")])


class FileLockTest(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.d.name, "c.lock")

    def tearDown(self):
        self.d.cleanup()

    def test_exclusive_and_owner_reported(self):
        a = FileLock(self.path, owner="goalA:gen").acquire()
        with self.assertRaises(LockHeld) as cm:
            FileLock(self.path, owner="goalB:gen", timeout=0).acquire()
        self.assertEqual(cm.exception.owner, "goalA:gen")
        a.release()
        self.assertFalse(os.path.exists(self.path))

    def test_wait_then_acquire(self):
        a = FileLock(self.path, owner="A").acquire()
        threading.Timer(1.2, a.release).start()
        t0 = time.time()
        b = FileLock(self.path, owner="B", timeout=10).acquire()
        self.assertGreater(time.time() - t0, 1.0)
        b.release()

    def test_dead_pid_is_swept(self):
        p = subprocess.Popen([sys.executable, "-c", "pass"]); p.wait()
        os.mkdir(self.path)
        atomic_json(os.path.join(self.path, "owner.json"),
                    {"owner": "dead", "pid": p.pid, "ts": time.time(), "token": "x"})
        b = FileLock(self.path, owner="B", timeout=0).acquire()
        self.assertTrue(b.acquired)
        b.release()

    def test_live_pid_with_fresh_heartbeat_not_stale(self):
        a = FileLock(self.path, owner="A").acquire()
        info = json.load(open(os.path.join(self.path, "owner.json")))
        self.assertFalse(FileLock(self.path, owner="B")._is_stale(info))
        a.release()

    def test_heartbeat_refreshes_ts(self):
        old = pipelib.HEARTBEAT
        pipelib.HEARTBEAT = 0.2
        try:
            a = FileLock(self.path, owner="A").acquire()
            t1 = json.load(open(os.path.join(self.path, "owner.json")))["ts"]
            time.sleep(0.7)
            t2 = json.load(open(os.path.join(self.path, "owner.json")))["ts"]
            self.assertGreater(t2, t1)
            a.release()
        finally:
            pipelib.HEARTBEAT = old

    def test_break_does_not_steal_fresh_lock(self):
        """B3: a delayed breaker judged an OLD owner stale; a fresh owner
        has since taken the lock — the break must restore it."""
        judged = {"owner": "old", "pid": 999999, "ts": 0, "token": "old-token"}
        fresh = FileLock(self.path, owner="fresh").acquire()
        FileLock(self.path, owner="breaker")._break_if_still(judged)
        self.assertEqual(json.load(open(os.path.join(self.path, "owner.json")))["owner"],
                         "fresh")
        fresh.release()

    def test_release_only_deletes_own_lock(self):
        a = FileLock(self.path, owner="A").acquire()
        a._stop.set()
        # simulate A's lock broken and re-taken by B
        import shutil; shutil.rmtree(self.path)
        b = FileLock(self.path, owner="B").acquire()
        a.release()
        self.assertTrue(os.path.exists(self.path))
        b.release()

    def test_sorted_multi_acquire_no_deadlock(self):
        paths = [os.path.join(self.d.name, f"{c}.lock") for c in ("a", "b", "c")]
        done = []

        def worker(order):
            ls = [FileLock(p, owner=str(order), timeout=20).acquire()
                  for p in sorted(order)]
            time.sleep(0.2)
            for l in reversed(ls):
                l.release()
            done.append(order)
        ts = [threading.Thread(target=worker, args=(o,))
              for o in (paths, list(reversed(paths)), paths[1:] + paths[:1])]
        [t.start() for t in ts]
        [t.join(30) for t in ts]
        self.assertEqual(len(done), 3)


class HelpersTest(unittest.TestCase):
    def test_name_of(self):
        self.assertEqual(name_of("idle"), "idle")
        self.assertEqual(name_of({"name": "walk_a", "prompt_extra": "x"}), "walk_a")
        self.assertEqual(name_of({"id": "crew_01"}), "crew_01")

    def test_resolve_ref_keypath(self):
        root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        self.assertTrue(resolve_ref(root, "@palettes/dusk.colors.sea").startswith("#"))


if __name__ == "__main__":
    unittest.main()
