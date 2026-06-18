"""HD try-on inference engines.

Phase 3 introduces a *pluggable* inference layer so the async job pipeline can
run today (CPU stub) and be upgraded to a real diffusion model (IDM-VTON /
CatVTON) on a GPU box without touching the queue, endpoints, or UI.

Select the engine with the HD_ENGINE env var:
    HD_ENGINE=stub      -> StubEngine   (default; CPU; reuses the affine warp)
    HD_ENGINE=idm_vton  -> IDMVTONEngine (requires GPU + model weights)
"""
from __future__ import annotations

import os
from typing import Callable, Dict, Tuple

import numpy as np
import cv2

from .warp import warp_and_composite

Progress = Callable[[int, str], None]  # (percent, message) -> None


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


_ENGINES = {"stub": StubEngine, "idm_vton": IDMVTONEngine}
_engine_singleton: InferenceEngine | None = None


def get_engine() -> InferenceEngine:
    """Return the configured engine (cached). Falls back to stub if unknown."""
    global _engine_singleton
    if _engine_singleton is None:
        key = os.getenv("HD_ENGINE", "stub").lower()
        cls = _ENGINES.get(key, StubEngine)
        _engine_singleton = cls()
    return _engine_singleton
