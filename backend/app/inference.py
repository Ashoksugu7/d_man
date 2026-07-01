"""HD try-on inference engines.

Phase 3 introduces a *pluggable* inference layer so the async job pipeline can
run today (CPU stub) and be upgraded to a real diffusion model (IDM-VTON /
CatVTON) on a GPU box without touching the queue, endpoints, or UI.

Select the engine with the HD_ENGINE env var:
    HD_ENGINE=catvton   -> CatVTONEngine  (default; local real VTON)
    HD_ENGINE=stub      -> StubEngine     (CPU; reuses the affine warp)
    HD_ENGINE=replicate -> ReplicateEngine(hosted IDM-VTON; no local GPU needed;
                                           requires REPLICATE_API_TOKEN)
    HD_ENGINE=idm_vton  -> IDMVTONEngine  (local; requires NVIDIA/MPS + weights)
"""
from __future__ import annotations

import io
import os
import tempfile
import time
from typing import Callable, Dict, Tuple

import numpy as np
import cv2

from .warp import warp_and_composite, TOP_CATEGORIES

Progress = Callable[[int, str], None]  # (percent, message) -> None


def _vton_category(category: str) -> str:
    """Map our garment categories to IDM-VTON's expected values."""
    c = (category or "").lower()
    if c == "pant":
        return "lower_body"
    if c in ("dress", "saree", "lehenga", "gown"):
        return "dresses"
    return "upper_body"  # shirts/tees/kurtas/etc


class InferenceEngine:
    """Interface every HD engine implements."""

    name = "base"

    def generate(
        self,
        user_bgr: np.ndarray,
        garment_rgba: np.ndarray,
        garment_kp: Dict[str, Tuple[float, float]],
        body_kp: Dict[str, Tuple[float, float]],
        category: str,
        progress: Progress | None = None,
    ) -> np.ndarray:
        raise NotImplementedError


def _report(progress: Progress | None, pct: int, msg: str) -> None:
    if progress:
        progress(pct, msg)


class StubEngine(InferenceEngine):
    """CPU placeholder that produces a plausible HD-looking result *now*.

    It reuses the affine warp/composite from Phase 1 and adds light finishing
    (edge feather + subtle smoothing) so the async pipeline is fully testable
    end-to-end without a GPU. Swap for IDMVTONEngine for photorealistic output.
    """

    name = "stub"

    def generate(self, user_bgr, garment_rgba, garment_kp, body_kp, category,
                 progress=None):
        _report(progress, 10, "Preparing inputs")
        result = warp_and_composite(user_bgr, garment_rgba, garment_kp,
                                    body_kp, category)
        _report(progress, 60, "Compositing garment")

        # Light "finishing" pass so the stub is visually distinct from the
        # instant affine endpoint: gentle bilateral smoothing on the garment.
        finished = cv2.bilateralFilter(result, d=5, sigmaColor=40, sigmaSpace=5)
        _report(progress, 95, "Finishing")
        return finished


class IDMVTONEngine(InferenceEngine):
    """Real diffusion try-on. Requires an NVIDIA GPU (>=8GB VRAM) and weights.

    INTEGRATION GUIDE (do on a GPU machine):
      1. pip install the model deps (torch+cuda, diffusers, etc.) and clone the
         IDM-VTON repo; download checkpoints.
      2. In __init__, load the pipeline once (cache as a module global so the
         Celery worker reuses it across tasks):
            from idm_vton import IDMVTONPipeline
            self.pipe = IDMVTONPipeline.from_pretrained(..).to("cuda")
      3. The model needs more than our keypoints — typically:
            - DensePose UV map of the person  (see DensePose)
            - human parsing mask (SCHP / Graphonomy) to isolate the torso/legs
            - the garment image + its mask
         Compute these here (or in a preprocessing step) from user_bgr.
      4. Run inference and return a BGR uint8 image the same size as user_bgr.
      5. Target <15s/image; export to ONNX / use TensorRT for speed.

    Until implemented, this raises so misconfiguration is obvious rather than
    silently degrading.
    """

    name = "idm_vton"

    def __init__(self) -> None:
        # Lazy: don't import torch unless this engine is actually selected.
        self._pipe = None

    def _ensure_loaded(self):
        if self._pipe is None:
            raise NotImplementedError(
                "IDMVTONEngine is a GPU integration stub. Implement model "
                "loading + inference (see the integration guide in "
                "inference.py) on a CUDA machine, then set HD_ENGINE=idm_vton."
            )

    def generate(self, user_bgr, garment_rgba, garment_kp, body_kp, category,
                 progress=None):
        _report(progress, 5, "Loading diffusion model")
        self._ensure_loaded()
        # ... real preprocessing + pipeline call goes here ...


class ReplicateEngine(InferenceEngine):
    """Photorealistic try-on via hosted IDM-VTON on Replicate.

    The heavy model runs in the cloud, so this works on ANY machine (incl. a
    Mac with no GPU). Requires:
        pip install replicate
        export REPLICATE_API_TOKEN=...        # https://replicate.com/account
        export HD_ENGINE=replicate
    Optional:
        REPLICATE_IDM_VTON_VERSION  (pin a specific model version hash)

    Model: cuuupid/idm-vton. Inputs: human_img, garm_img, garment_des,
    category (upper_body|lower_body|dresses), plus seed/steps. Returns one image.
    Note: Replicate is a paid hosted service and each call has latency/cost.
    """

    name = "replicate"
    # Default pinned version (override via REPLICATE_IDM_VTON_VERSION).
    DEFAULT_REF = (
        "cuuupid/idm-vton:"
        "0513734a452173b8173e907e3a59d19a36266e55b48528559432bd21c7d7e985"
    )

    def __init__(self) -> None:
        if not os.getenv("REPLICATE_API_TOKEN"):
            # Surface misconfig early & clearly rather than at first request.
            raise RuntimeError(
                "ReplicateEngine needs REPLICATE_API_TOKEN set. Get one at "
                "https://replicate.com/account and `export REPLICATE_API_TOKEN=...`"
            )
        self._ref = os.getenv("REPLICATE_IDM_VTON_VERSION") or self.DEFAULT_REF

    def generate(self, user_bgr, garment_rgba, garment_kp, body_kp, category,
                 progress=None):
        import replicate  # lazy: only needed for this engine
        import requests

        _report(progress, 5, "Uploading images")
        # Encode person (BGR) and garment (BGR+alpha -> RGB on white) to PNG.
        human_png = _encode_png(user_bgr)
        garm_rgb = _flatten_rgba(garment_rgba)
        garm_png = _encode_png(garm_rgb)

        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as hf, \
             tempfile.NamedTemporaryFile(suffix=".png", delete=False) as gf:
            hf.write(human_png); hf.flush()
            gf.write(garm_png); gf.flush()
            human_path, garm_path = hf.name, gf.name

        _report(progress, 20, "Running diffusion model (hosted)")
        try:
            with open(human_path, "rb") as h, open(garm_path, "rb") as g:
                output = replicate.run(self._ref, input={
                    "human_img": h,
                    "garm_img": g,
                    "garment_des": f"a {category}",
                    "category": _vton_category(category),
                    "crop": False,
                    "steps": int(os.getenv("HD_STEPS", "30")),
                    "seed": int(os.getenv("HD_SEED", "42")),
                })
        finally:
            for p in (human_path, garm_path):
                try:
                    os.unlink(p)
                except OSError:
                    pass

        _report(progress, 85, "Downloading result")
        url = _first_url(output)
        if not url:
            raise RuntimeError(f"Unexpected Replicate output: {output!r}")
        data = requests.get(url, timeout=120).content
        arr = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
        if arr is None:
            raise RuntimeError("Could not decode result image from Replicate")
        _report(progress, 98, "Finalizing")
        return arr


# --- small encode/decode helpers -------------------------------------------
def _encode_png(bgr: np.ndarray) -> bytes:
    ok, buf = cv2.imencode(".png", bgr)
    if not ok:
        raise RuntimeError("PNG encode failed")
    return buf.tobytes()


def _flatten_rgba(rgba: np.ndarray) -> np.ndarray:
    """Composite a BGRA garment over white -> BGR (Replicate wants a normal img)."""
    if rgba.shape[2] == 3:
        return rgba
    alpha = rgba[:, :, 3:4].astype(np.float32) / 255.0
    bgr = rgba[:, :, :3].astype(np.float32)
    white = np.full_like(bgr, 255.0)
    out = bgr * alpha + white * (1.0 - alpha)
    return out.astype(np.uint8)


def _first_url(output) -> str | None:
    """Replicate output can be a str, a list, or a FileOutput-like object."""
    if output is None:
        return None
    if isinstance(output, str):
        return output
    if isinstance(output, (list, tuple)):
        return _first_url(output[0]) if output else None
    for attr in ("url",):
        if hasattr(output, attr):
            return getattr(output, attr)
    return str(output)


class LocalDiffusionEngine(InferenceEngine):
    """Local diffusion try-on that runs on Apple Silicon (MPS), CUDA, or CPU.

    Avoids DensePose/SCHP (the Mac pain point): it builds the garment-agnostic
    mask from MediaPipe (see preprocess.py) and uses a Stable-Diffusion-1.5
    *inpainting* pipeline + **IP-Adapter** conditioned on the garment image to
    paint the garment into the masked clothing region.

    Setup (Apple Silicon):
        pip install -r backend/requirements-hd.txt   # torch, diffusers, ...
        export HD_ENGINE=local
    First run downloads ~2-3GB of weights (SD1.5 inpainting + IP-Adapter).
    Tunables: HD_STEPS, HD_GUIDANCE, HD_IPADAPTER_SCALE, HD_BASE_MODEL.

    Notes: this is a pragmatic, moderate-quality local path — not full IDM-VTON
    fidelity. MPS is slower than CUDA; expect tens of seconds per image.
    """

    name = "local"
    SIZE = 512  # SD1.5 inpainting works best around 512px

    def __init__(self) -> None:
        self._pipe = None
        self._device = None
        self._dtype = None

    def _load(self, progress: Progress | None):
        if self._pipe is not None:
            return
        import torch
        from diffusers import AutoPipelineForInpainting

        if torch.cuda.is_available():
            self._device, self._dtype = "cuda", torch.float16
        elif getattr(torch.backends, "mps", None) and torch.backends.mps.is_available():
            # float16 on MPS is flaky for SD; float32 is safer.
            self._device, self._dtype = "mps", torch.float32
        else:
            self._device, self._dtype = "cpu", torch.float32

        _report(progress, 8, f"Loading model on {self._device}")
        base = os.getenv("HD_BASE_MODEL", "runwayml/stable-diffusion-inpainting")
        pipe = AutoPipelineForInpainting.from_pretrained(base, torch_dtype=self._dtype)
        # IP-Adapter (SD1.5) lets us condition on the garment IMAGE, not just text.
        pipe.load_ip_adapter("h94/IP-Adapter", subfolder="models",
                             weight_name="ip-adapter_sd15.bin")
        pipe.set_ip_adapter_scale(float(os.getenv("HD_IPADAPTER_SCALE", "0.7")))
        pipe.safety_checker = None
        pipe.to(self._device)
        self._pipe = pipe

    def generate(self, user_bgr, garment_rgba, garment_kp, body_kp, category,
                 progress=None):
        import torch
        from PIL import Image
        from .preprocess import build_inpaint_mask

        self._load(progress)

        h0, w0 = user_bgr.shape[:2]
        user_rgb = cv2.cvtColor(user_bgr, cv2.COLOR_BGR2RGB)

        _report(progress, 18, "Building clothing mask")
        mask = build_inpaint_mask(user_rgb, body_kp, category)

        S = self.SIZE
        person_pil = Image.fromarray(user_rgb).resize((S, S))
        mask_pil = Image.fromarray(mask).resize((S, S))
        garm_rgb = cv2.cvtColor(_flatten_rgba(garment_rgba), cv2.COLOR_BGR2RGB)
        garm_pil = Image.fromarray(garm_rgb).resize((S, S))

        steps = int(os.getenv("HD_STEPS", "30"))
        guidance = float(os.getenv("HD_GUIDANCE", "7.0"))
        prompt = (f"a person wearing a {category}, photorealistic, natural "
                  f"folds, well-fitted, studio photo")
        negative = "lowres, blurry, deformed, extra limbs, distorted, artifacts"

        # diffusers >=0.27 step callback signature: (pipe, step, t, kwargs)->kwargs
        def cb(_pipe, step, _t, kwargs):
            pct = 25 + int(70 * (step + 1) / max(steps, 1))
            _report(progress, min(pct, 96), f"Diffusing ({step + 1}/{steps})")
            return kwargs

        _report(progress, 25, "Diffusing")
        gen = torch.Generator(device="cpu").manual_seed(int(os.getenv("HD_SEED", "42")))
        out = self._pipe(
            prompt=prompt,
            negative_prompt=negative,
            image=person_pil,
            mask_image=mask_pil,
            ip_adapter_image=garm_pil,
            num_inference_steps=steps,
            guidance_scale=guidance,
            strength=0.99,
            generator=gen,
            callback_on_step_end=cb,
        ).images[0]

        result_rgb = np.array(out.resize((w0, h0)))
        return cv2.cvtColor(result_rgb, cv2.COLOR_RGB2BGR)


class CatVTONEngine(InferenceEngine):
    """Real virtual try-on with CatVTON, runnable locally on Apple Silicon.

    Unlike the IP-Adapter `local` engine (which only *style-conditions*), CatVTON
    is a true VTON diffusion model: it concatenates the person and garment and
    actually transfers the garment. We feed it OUR MediaPipe mask, so we skip
    CatVTON's DensePose+SCHP `AutoMasker` — that's what keeps it Mac-installable
    (`CatVTONPipeline` itself only needs diffusers, no detectron2).

    SETUP (once):
        # 1. clone the repo somewhere and point CATVTON_REPO at it
        git clone https://github.com/Zheng-Chong/CatVTON
        export CATVTON_REPO=/abs/path/to/CatVTON
        # 2. install its deps (skip detectron2/densepose — we don't use them)
        pip install -r backend/requirements-hd.txt
        # 3. select the engine
        export HD_ENGINE=catvton
    Weights (zhengchong/CatVTON + SD-1.5 inpaint base) auto-download on first run.

    Tunables: CATVTON_REPO (required), CATVTON_BASE, CATVTON_ATTN,
    CATVTON_VERSION (vitonhd|dresscode|mix), HD_STEPS, HD_GUIDANCE (CFG ~2.5),
    HD_HEIGHT (512), HD_WIDTH (384), HD_SEED.
    """

    name = "catvton"

    def __init__(self) -> None:
        repo = os.getenv("CATVTON_REPO")
        if not repo or not os.path.isdir(repo):
            raise RuntimeError(
                "CatVTONEngine needs CATVTON_REPO pointing at a clone of "
                "https://github.com/Zheng-Chong/CatVTON. See backend/scripts/"
                "setup_catvton.sh or PHASE3_NOTES.md."
            )
        self._repo = repo
        self._pipe = None
        self._device = None
        self._H = int(os.getenv("HD_HEIGHT", "512"))
        self._W = int(os.getenv("HD_WIDTH", "384"))

    def _load(self, progress):
        if self._pipe is not None:
            return
        import sys
        import torch
        if self._repo not in sys.path:
            sys.path.insert(0, self._repo)
        # Imports the diffusers-only pipeline (NOT model.cloth_masker, which would
        # pull in detectron2/densepose).
        from model.pipeline import CatVTONPipeline  # type: ignore

        if torch.cuda.is_available():
            self._device, dtype = "cuda", torch.float16
        elif getattr(torch.backends, "mps", None) and torch.backends.mps.is_available():
            self._device, dtype = "mps", torch.float32
        else:
            self._device, dtype = "cpu", torch.float32

        _report(progress, 8, f"Loading CatVTON on {self._device}")
        self._pipe = CatVTONPipeline(
            base_ckpt=os.getenv("CATVTON_BASE", "runwayml/stable-diffusion-inpainting"),
            attn_ckpt=os.getenv("CATVTON_ATTN", "zhengchong/CatVTON"),
            attn_ckpt_version=os.getenv("CATVTON_VERSION", "mix"),
            weight_dtype=dtype,
            device=self._device,
            skip_safety_check=True,
        )

    def generate(self, user_bgr, garment_rgba, garment_kp, body_kp, category,
                 progress=None):
        import torch
        from PIL import Image
        from diffusers.image_processor import VaeImageProcessor
        from .preprocess import build_inpaint_mask

        self._load(progress)
        H, W = self._H, self._W
        h0, w0 = user_bgr.shape[:2]

        user_rgb = cv2.cvtColor(user_bgr, cv2.COLOR_BGR2RGB)
        _report(progress, 18, "Building clothing mask")
        mask = build_inpaint_mask(user_rgb, body_kp, category)

        person_pil = Image.fromarray(user_rgb)
        garm_pil = Image.fromarray(cv2.cvtColor(_flatten_rgba(garment_rgba), cv2.COLOR_BGR2RGB))
        mask_pil = Image.fromarray(mask)

        # Match CatVTON's reference preprocessing exactly.
        vae_proc = VaeImageProcessor(vae_scale_factor=8)
        mask_proc = VaeImageProcessor(vae_scale_factor=8, do_normalize=False,
                                      do_binarize=True, do_convert_grayscale=True)
        person_t = vae_proc.preprocess(person_pil, H, W)   # (1,C,H,W) in [-1,1]
        cloth_t = vae_proc.preprocess(garm_pil, H, W)
        mask_t = mask_proc.preprocess(mask_pil, H, W)

        steps = int(os.getenv("HD_STEPS", "50"))
        guidance = float(os.getenv("HD_GUIDANCE", "2.5"))
        _report(progress, 25, "Running CatVTON")
        gen = torch.Generator(device="cpu").manual_seed(int(os.getenv("HD_SEED", "42")))
        results = self._pipe(
            person_t, cloth_t, mask_t,
            num_inference_steps=steps,
            guidance_scale=guidance,
            height=H, width=W,
            generator=gen,
        )
        result_pil = results[0].resize((w0, h0))
        _report(progress, 96, "Finalizing")
        return cv2.cvtColor(np.array(result_pil), cv2.COLOR_RGB2BGR)


_ENGINES = {
    "stub": StubEngine,
    "replicate": ReplicateEngine,
    "local": LocalDiffusionEngine,
    "catvton": CatVTONEngine,
    "idm_vton": IDMVTONEngine,
}
_engine_singleton: InferenceEngine | None = None


def get_engine() -> InferenceEngine:
    """Return the configured engine (cached). Defaults HD renders to CatVTON."""
    global _engine_singleton
    if _engine_singleton is None:
        key = os.getenv("HD_ENGINE", "catvton").lower()
        cls = _ENGINES.get(key, StubEngine)
        _engine_singleton = cls()
    return _engine_singleton
