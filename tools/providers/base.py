"""Provider adapters for glb components (mymeshy base.py pattern).

A component brief declares `provider: "mock"` or
`provider: {"name": "mock", "options": {...}}`. The adapter's generate()
produces export/<cid>.glb; everything downstream (unit render, sockets,
certification, publish) is provider-agnostic. `mock` runs without GPU or
Blender — it exists so the provider contract is always testable.
"""
import importlib.util
import os

_PROVIDERS_DIR = os.path.dirname(os.path.abspath(__file__))
_REGISTRY = {}


def adapter(name):
    if name not in _REGISTRY:
        path = os.path.join(_PROVIDERS_DIR, f"{name}.py")
        if not os.path.exists(path):
            raise KeyError(f"unknown provider '{name}'")
        spec = importlib.util.spec_from_file_location(f"providers.{name}", path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        _REGISTRY[name] = mod
    return _REGISTRY[name]


def provider_of(brief):
    p = brief.get("provider")
    if isinstance(p, dict):
        return p.get("name", "mock"), p.get("options", {})
    return (p or "mock"), {}


def generate(cid, cdir, brief, env):
    name, opts = provider_of(brief)
    ad = adapter(name)
    out = os.path.join(cdir, "export", f"{cid}.glb")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    ad.generate(cid, cdir, brief, opts, env, out)
    if not os.path.exists(out):
        raise RuntimeError(f"provider '{name}' produced no glb for {cid}")
    return out, name
