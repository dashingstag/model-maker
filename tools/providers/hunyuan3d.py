"""hunyuan3d provider — image->3D via Tencent Hunyuan3D-2 (mymeshy adapter
pattern). Real backend for the mannequin->production path.

Status: SKELETON — declares the contract, fails with install steps until
weights + deps land. Options: model (mini|full), resolution, texture
(bool), vram_budget_gb. When implemented, generate() must:
  1. load the accepted/ concept image for <cid> (candidates/accepted pick)
  2. run hy3dgen shape (+ paint if VRAM allows; else project the
     reference image for albedo — mymeshy's degrade path)
  3. cleanup/decimate/xatlas-UV via the meshproc chain
  4. write export/<cid>.glb

Install sketch (from mymeshy): clone Tencent-Hunyuan/Hunyuan3D-2,
pip install hy3dgen deps (ninja, pybind11, opencv-python, pymeshlab,
pygltflib); paint needs custom_rasterizer CUDA ext ~10-12GB VRAM.
"""

def _check_env(opts):
    try:
        import hy3dgen  # noqa: F401
        return True
    except ImportError:
        return False


def generate(cid, cdir, brief, opts, env, out):
    if not _check_env(opts):
        raise RuntimeError(
            f"hunyuan3d provider not installed for {cid} — install "
            "Tencent-Hunyuan/Hunyuan3D-2 + hy3dgen deps (see module "
            "docstring / reports/REPO_RESEARCH.md); use provider:'mock' "
            "to keep the pipeline runnable meanwhile")
    # TODO(real): hy3dgen shape -> paint/degrade -> meshproc -> write `out`
    raise NotImplementedError("hunyuan3d.generate body pending weights")
