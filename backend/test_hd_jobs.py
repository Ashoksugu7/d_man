"""HD async pipeline smoke test (eager mode — no Redis/worker needed).

Exercises the Celery task end-to-end: synthetic photo -> pose -> stub engine
-> result file, and checks the success payload shape the API/UI rely on.
"""
import os
os.environ["CELERY_TASK_ALWAYS_EAGER"] = "1"
os.environ.setdefault("HD_ENGINE", "stub")

import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import numpy as np  # noqa: E402
from PIL import Image, ImageDraw  # noqa: E402


def _make_person(path):
    w, h = 480, 640
    img = Image.new("RGB", (w, h), (225, 225, 225))
    d = ImageDraw.Draw(img)
    d.ellipse([w/2-40, 60, w/2+40, 140], fill=(200, 170, 150))
    d.polygon([(w*0.30, 200), (w*0.70, 200), (w*0.66, 470), (w*0.34, 470)],
              fill=(120, 120, 130))
    img.save(path)


def main():
    from app import jobs
    from app.jobs import run_hd_tryon

    os.makedirs(jobs.RESULTS_DIR, exist_ok=True)
    up = os.path.join(jobs.BASE_DIR, "storage", "uploads")
    os.makedirs(up, exist_ok=True)
    photo = os.path.join(up, "_hd_test.png")
    _make_person(photo)

    r = run_hd_tryon.apply(args=("shirt_red", photo, "png"))
    assert r.state == "SUCCESS", f"expected SUCCESS, got {r.state}: {r.result}"
    res = r.result
    for k in ("result_id", "result_url", "garment_id", "engine"):
        assert k in res, f"missing {k} in result payload"
    out = os.path.join(str(jobs.RESULTS_DIR), f"hd_{res['result_id']}.png")
    assert os.path.exists(out), f"result image not written: {out}"
    print("PASS - HD job SUCCESS, engine:", res["engine"], "->", res["result_url"])

    # Unknown garment should fail clearly. In eager mode the exception
    # propagates; in worker mode it becomes the task's FAILURE state (which the
    # GET endpoint surfaces as {"status":"failure","error":...}).
    try:
        run_hd_tryon.apply(args=("does_not_exist", photo, "png"))
        raise AssertionError("expected failure for unknown garment")
    except ValueError as e:
        assert "Unknown garment_id" in str(e)
    print("PASS - unknown garment -> error surfaced")

    print("ALL PASS")


if __name__ == "__main__":
    main()
