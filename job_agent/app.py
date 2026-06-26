"""Flask dashboard. http://localhost:5000"""
from __future__ import annotations

import logging
import threading
from datetime import datetime

from flask import Flask, jsonify, render_template, request

from config import FLASK_HOST, FLASK_PORT, MIN_FIT_SCORE
from db import get_jobs, init_db, stats, update_status

log = logging.getLogger(__name__)
app = Flask(__name__)

# Single thread guard so we don't fire two batch applies in parallel.
_apply_lock = threading.Lock()
_apply_state = {"running": False, "done": 0, "total": 0, "current": None}


def _apply_worker(job_ids: list[int]) -> None:
    from applicator import run_apply_many

    _apply_state.update(running=True, done=0, total=len(job_ids), current=None)
    try:
        run_apply_many(job_ids)
    finally:
        _apply_state.update(running=False, current=None)


def _search_worker() -> None:
    from agent import run_pipeline_once

    try:
        run_pipeline_once()
    except Exception:  # noqa: BLE001
        log.exception("manual run failed")


@app.route("/")
def index():
    jobs = get_jobs(min_score=MIN_FIT_SCORE)
    s = stats()
    return render_template(
        "dashboard.html",
        jobs=jobs,
        stats=s,
        threshold=MIN_FIT_SCORE,
        last_updated=datetime.now().strftime("%b %d %Y %I:%M %p"),
    )


@app.route("/api/jobs")
def api_jobs():
    jobs = get_jobs(min_score=MIN_FIT_SCORE)
    return jsonify({"jobs": jobs, "stats": stats(), "apply_state": _apply_state})


@app.route("/api/apply", methods=["POST"])
def api_apply():
    if _apply_state["running"]:
        return jsonify({"error": "already running"}), 409
    data = request.get_json(silent=True) or {}
    job_ids = [int(x) for x in data.get("job_ids", [])]
    if not job_ids:
        return jsonify({"error": "no job_ids"}), 400
    for jid in job_ids:
        update_status(jid, "approved")
    if not _apply_lock.acquire(blocking=False):
        return jsonify({"error": "lock held"}), 409
    try:
        threading.Thread(target=_apply_worker, args=(job_ids,), daemon=True).start()
    finally:
        _apply_lock.release()
    return jsonify({"ok": True, "queued": len(job_ids)})


@app.route("/api/skip", methods=["POST"])
def api_skip():
    data = request.get_json(silent=True) or {}
    job_id = int(data.get("job_id", 0))
    if not job_id:
        return jsonify({"error": "no job_id"}), 400
    update_status(job_id, "skipped")
    return jsonify({"ok": True})


@app.route("/api/run-now", methods=["POST"])
def api_run_now():
    threading.Thread(target=_search_worker, daemon=True).start()
    return jsonify({"ok": True})


@app.route("/status")
def status():
    return jsonify({"apply_state": _apply_state, "stats": stats()})


def serve() -> None:
    init_db()
    app.run(host=FLASK_HOST, port=FLASK_PORT, debug=False, use_reloader=False)


if __name__ == "__main__":
    serve()
