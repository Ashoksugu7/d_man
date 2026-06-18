#!/usr/bin/env bash
# Set up CatVTON for the local `catvton` HD engine (Apple Silicon friendly).
# We use our own MediaPipe mask, so we DO NOT install detectron2 / densepose.
#
# Usage:
#   bash backend/scripts/setup_catvton.sh [target_dir]
#   export CATVTON_REPO=<printed path>
#   export HD_ENGINE=catvton
set -euo pipefail

TARGET="${1:-$HOME/CatVTON}"

if [ ! -d "$TARGET/.git" ]; then
  echo "Cloning CatVTON into $TARGET ..."
  git clone --depth 1 https://github.com/Zheng-Chong/CatVTON "$TARGET"
else
  echo "CatVTON already present at $TARGET"
fi

# CatVTONPipeline only needs diffusers/torch/transformers/accelerate — already
# in backend/requirements-hd.txt. We intentionally skip the repo's
# detectron2/densepose/SCHP requirements (used only by their AutoMasker).
echo
echo "Done. Now run:"
echo "  pip install -r backend/requirements-hd.txt"
echo "  export CATVTON_REPO=\"$TARGET\""
echo "  export HD_ENGINE=catvton"
echo
echo "Then start the worker (macOS fork-safe) + API and click 'HD render'."
echo "First run downloads the CatVTON + SD-1.5-inpaint weights (~few GB)."
