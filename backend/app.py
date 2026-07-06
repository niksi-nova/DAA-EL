# =============================================================================
# app.py — Flask REST API
# =============================================================================
# OVERALL DESIGN:
#   This file is the HTTP layer of the project.  It handles:
#     - Receiving uploaded log files from a client (browser / Postman / React)
#     - Delegating all analysis work to the analyzer package (engine layer)
#     - Returning structured JSON results
#     - Caching results in memory for later retrieval
#
#   Architectural separation:
#     app.py          → HTTP concerns only (routing, request parsing, responses)
#     analyzer/       → Algorithm concerns only (no Flask, no HTTP)
#
#   This separation matters: the analyzer package can be tested independently
#   of Flask (see test_engine.py), and the Flask layer can be swapped for
#   another framework without touching the algorithm code.
#
# ENDPOINTS:
#   POST /analyze              → Upload a file, run sequential + parallel, return results
#   POST /benchmark            → Upload a file, sweep thread counts 1–16, return comparison
#   GET  /results/<job_id>     → Retrieve a previously stored result by job ID
#   GET  /health               → Liveness probe
#
# RESULTS PERSISTENCE:
#   Results are stored in a local SQLite file (backend/results.db) keyed by
#   job_id — see db.py. This survives server restarts, unlike the in-memory
#   dict this project started with. Still single-file and zero-setup, which
#   is the right tradeoff for a university project; a production deployment
#   serving multiple machines would use Redis or PostgreSQL instead.
#
# FILE LIFECYCLE:
#   1. Client uploads file via multipart/form-data.
#   2. Flask saves it to uploads/<job_id>_<safe_filename>.
#   3. The analyzer engine reads it directly from disk.
#   4. After analysis, we DELETE the file.
#   Reason: we only need the RESULT (counts + metrics), not the raw file.
#   Keeping uploaded files wastes disk space and creates privacy/security risk.
#   Deleting immediately is the correct default for a stateless analysis service.
# =============================================================================

import atexit
import os
import uuid
from concurrent.futures import ProcessPoolExecutor

from flask import Flask, request, jsonify, Response
from flask_cors import CORS
from werkzeug.utils import secure_filename

import db
from analyzer import chunker, sequential, parallel, metrics
from analyzer.parallel import analyze_parallel_mmap  # mmap-backed parallel variant


def _load_dotenv(path: str) -> None:
    """
    Minimal .env loader: reads KEY=VALUE lines into os.environ, skipping
    blank lines and '#' comments. Existing environment variables are NOT
    overwritten, so `PORT=5002 python app.py` can still override the file.

    We hand-roll this instead of depending on python-dotenv so the backend
    has no extra install step / dependency just to read one number.
    """
    if not os.path.exists(path):
        return
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip())


# ---------------------------------------------------------------------------
# Load PORT from the project-root .env file (one level above backend/), so
# the port number lives in exactly one place and the frontend (vite.config.js
# / api.js) can read the same file instead of each side hardcoding its own
# copy of the number.
# ---------------------------------------------------------------------------
_load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".env"))
PORT = int(os.environ.get("PORT", 5000))

# ---------------------------------------------------------------------------
# Flask application setup
# ---------------------------------------------------------------------------
app = Flask(__name__)

# CORS: allow all origins.  In a production app you would restrict this to
# your frontend domain.  For local development and a university project,
# allowing all origins is fine and avoids confusing CORS errors.
CORS(app)

# Directory where uploaded files are temporarily saved during analysis.
UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "uploads")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# ---------------------------------------------------------------------------
# Persistent worker pool
# ---------------------------------------------------------------------------
# Spawning a ProcessPoolExecutor is not free: each worker is a brand-new OS
# process, which on Windows in particular involves a comparatively expensive
# CreateProcess call plus Python re-importing every module in the worker.
# Creating and tearing down a pool on EVERY /analyze or /benchmark request
# pays that cost repeatedly for no benefit, since the same pool can safely
# service many requests one after another.
#
# We create ONE pool when the Flask process starts and reuse it for the
# lifetime of the server. max_workers is set high enough (32) to cover the
# largest thread count we ever request (clamped to 32 in /analyze, and the
# THREAD_COUNTS sweep in /benchmark tops out at 16) — submitting fewer tasks
# than max_workers simply leaves the extra worker processes idle.
#
# WHY THIS IS GUARDED BY if __name__ == "__main__" (at the bottom of this
# file) RATHER THAN CREATED HERE AT IMPORT TIME:
# ProcessPoolExecutor uses the 'spawn' start method on macOS/Windows, which
# launches each worker as a fresh Python interpreter that RE-IMPORTS this
# module (as '__mp_main__', not '__main__'). If pool creation happened at
# plain module level, every worker process would execute this line again on
# import and spawn its OWN 32-process pool, which would each spawn 32 more,
# recursively — a fork bomb. Creating it only inside the `if __name__ ==
# "__main__":` guard ensures only the original parent process builds the pool.
WORKER_POOL: "ProcessPoolExecutor | None" = None

# ---------------------------------------------------------------------------
# Results persistence (SQLite)
# ---------------------------------------------------------------------------
# Previously results were cached in a plain Python dict, which is wiped on
# every server restart. db.py stores each job's result as a row in a local
# SQLite file (results.db) so GET /results/<job_id> keeps working even after
# the Flask process has been stopped and started again.
db.init_db()

# ---------------------------------------------------------------------------
# Configuration: allowed file extensions (basic security guard).
# We only process text-based log files.
# ---------------------------------------------------------------------------
ALLOWED_EXTENSIONS = {"log", "txt"}


def _allowed_file(filename: str) -> bool:
    """Return True if the filename has an allowed extension."""
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def _warm_page_cache(filepath: str) -> None:
    """
    Read the file once and throw the result away, before any timer starts.

    Without this, the sequential run (which always goes first) pays the cold
    disk-read cost while every parallel/mmap run that follows benefits from
    an OS page cache that the sequential run just warmed up for them. That
    asymmetry inflates the measured speedup. Warming the cache up front
    before ANY timed run starts puts all three methods on equal footing.
    """
    with open(filepath, "rb") as f:
        while f.read(1024 * 1024):
            pass


def _save_upload(file_storage, job_id: str) -> str:
    """
    Securely save an uploaded FileStorage object to disk.

    secure_filename() (from werkzeug) sanitises the filename to prevent
    directory traversal attacks (e.g., a filename like '../../etc/passwd'
    would be reduced to 'etc_passwd').  This is essential whenever you
    save user-supplied filenames to disk.

    We prefix the safe filename with the job_id to prevent name collisions
    if two users upload files with the same name simultaneously.

    Returns the absolute path to the saved file.
    """
    safe_name = secure_filename(file_storage.filename)
    save_path = os.path.join(UPLOAD_FOLDER, f"{job_id}_{safe_name}")
    file_storage.save(save_path)
    return save_path


# =============================================================================
# ROUTE: POST /analyze
# =============================================================================
@app.route("/analyze", methods=["POST"])
def analyze() -> Response:
    """
    Accept a log file and a thread count, run both sequential and parallel
    analysis, compute metrics, store the result, and return it as JSON.

    Request (multipart/form-data):
      file    : The log file to analyse.
      threads : (optional) Number of parallel threads.  Default: 4.
                Clamped to [1, 32] to prevent resource exhaustion.

    Response (200 OK):
      {
        "job_id":        "...",         // UUID for later retrieval
        "filename":      "...",         // original upload filename
        "file_size_kb":  ...,           // file size in KB
        "total_lines":   ...,           // sum of all level counts
        "counts":        { "INFO": ..., "WARNING": ..., ... },
        "metrics":       {
          "sequential_time_ms": ...,
          "parallel_time_ms":   ...,
          "speedup":            ...,
          "efficiency_pct":     ...,
          "num_threads":        ...
        }
      }

    Error responses:
      400 Bad Request  — missing file, no filename, disallowed extension
      500 Internal     — unexpected error during analysis
    """
    # ── Validate request ────────────────────────────────────────────────────
    if "file" not in request.files:
        return jsonify({"error": "No file part in request."}), 400

    file = request.files["file"]
    if file.filename == "":
        return jsonify({"error": "No file selected."}), 400

    if not _allowed_file(file.filename):
        return jsonify({
            "error": f"File type not allowed. Accepted: {ALLOWED_EXTENSIONS}"
        }), 400

    # ── Parse thread count ──────────────────────────────────────────────────
    try:
        num_threads = int(request.form.get("threads", 4))
    except ValueError:
        num_threads = 4
    # Clamp to a sane range: minimum 1, maximum 32.
    num_threads = max(1, min(32, num_threads))

    # ── Generate a job ID and save the file ─────────────────────────────────
    # uuid4() generates a random 128-bit identifier.  The probability of a
    # collision is astronomically small (2^-61 for 1 billion jobs).
    job_id = str(uuid.uuid4())
    filepath = _save_upload(file, job_id)
    original_filename = secure_filename(file.filename)

    try:
        file_size_kb = round(os.path.getsize(filepath) / 1024, 2)

        # ── SPLIT ──────────────────────────────────────────────────────────
        # Divide the file into num_threads byte-range chunks aligned to newlines.
        # O(T) time, O(T) space — see chunker.py for full explanation.
        chunks = chunker.get_chunks(filepath, num_threads)

        # Warm the OS page cache BEFORE any timed run, so the sequential
        # baseline isn't unfairly penalised by a cold-disk read that the
        # later parallel/mmap runs wouldn't have to pay.
        _warm_page_cache(filepath)

        # ── Sequential baseline (control variable) ──────────────────────────
        # Run the single-threaded analysis FIRST so we have the ground truth
        # counts to verify against the parallel result (correctness before speed).
        seq_counts, seq_time = sequential.analyze_sequential(filepath)

        # ── Parallel analysis (experimental variable) ────────────────────────
        # Run the multi-threaded analysis.
        par_counts, par_time = parallel.analyze_parallel(filepath, chunks, executor=WORKER_POOL)

        # ── mmap-backed parallel analysis (third method) ─────────────────────
        # We run all three methods so the frontend can display a three-way
        # comparison: sequential vs. thread-parallel vs. mmap-parallel.
        # The mmap variant maps the entire file into virtual memory once and
        # lets all threads read their chunks directly from RAM (after the OS
        # page cache is warm from the sequential and parallel passes above).
        # This gives us the best-case read throughput for the given hardware.
        mmap_counts, mmap_time = analyze_parallel_mmap(filepath, chunks, executor=WORKER_POOL)

        # ── Compute performance metrics ──────────────────────────────────────
        perf_metrics = metrics.compute_metrics(seq_time, par_time, num_threads)

        # We use the PARALLEL counts as the returned result — it covers the full
        # file via the chunk mechanism.  (Both should be identical; the test
        # script verifies this assertion explicitly.)
        total_lines = sum(par_counts.values())

        result = {
            "job_id":        job_id,
            "filename":      original_filename,
            "file_size_kb":  file_size_kb,
            "total_lines":   total_lines,
            "counts":        par_counts,
            "metrics":       perf_metrics,
            # mmap wall-clock time exposed directly so the frontend can show
            # all three bars (sequential / parallel / mmap) in one response.
            "mmap_time_ms":  round(mmap_time * 1000, 2),
        }

        # Persist the result for later retrieval via GET /results/<job_id>,
        # surviving a server restart (see db.py for why SQLite over a dict).
        db.save_result(job_id, original_filename, result)

        return jsonify(result), 200

    except Exception as exc:
        # Surface the error message for debugging.  In production you would
        # log this server-side and return a generic error to the client.
        return jsonify({"error": str(exc)}), 500

    finally:
        # Always delete the uploaded file — even if analysis raised an exception.
        # We only needed it for the duration of the analysis; keeping it
        # wastes disk space and is a privacy/security concern.
        if os.path.exists(filepath):
            os.remove(filepath)


# =============================================================================
# ROUTE: POST /benchmark
# =============================================================================
@app.route("/benchmark", methods=["POST"])
def benchmark() -> Response:
    """
    Run a full thread-count sweep for one uploaded file.

    For each thread count in [1, 2, 4, 8, 16]:
      - Run analyze_parallel with that thread count.
      - Record actual speedup vs. sequential baseline.
      - Compute theoretical speedup from Amdahl's Law (S=0.05).

    This endpoint produces the data needed to plot the speedup-vs-threads
    chart — the most important visualisation in the project report.

    Request (multipart/form-data):
      file : The log file to benchmark.

    Response (200 OK):
      {
        "filename":       "...",
        "file_size_kb":   ...,
        "sequential_ms":  ...,    // baseline (single-threaded) time in ms
        "results": [
          {
            "threads":              1,
            "time_ms":              ...,
            "actual_speedup":       ...,   // measured
            "theoretical_speedup":  ...,   // Amdahl's Law (S=0.05)
            "efficiency_pct":       ...
          },
          ...  // one entry per thread count in THREAD_COUNTS
        ]
      }
    """
    if "file" not in request.files:
        return jsonify({"error": "No file part in request."}), 400

    file = request.files["file"]
    if file.filename == "":
        return jsonify({"error": "No file selected."}), 400

    if not _allowed_file(file.filename):
        return jsonify({
            "error": f"File type not allowed. Accepted: {ALLOWED_EXTENSIONS}"
        }), 400

    job_id = str(uuid.uuid4())
    filepath = _save_upload(file, job_id)
    original_filename = secure_filename(file.filename)

    try:
        file_size_kb = round(os.path.getsize(filepath) / 1024, 2)

        # Warm the OS page cache before the very first timed run (see
        # _warm_page_cache docstring) so the sequential baseline isn't
        # measuring cold-disk I/O while every later thread-count run benefits
        # from a cache that previous runs already warmed up.
        _warm_page_cache(filepath)

        # ── Sequential baseline — run ONCE ───────────────────────────────────
        # We run the sequential analysis exactly once.  All speedup ratios are
        # computed relative to this single measurement, which is the standard
        # methodology in parallel benchmarking to avoid noise from repeated runs.
        seq_counts, seq_time = sequential.analyze_sequential(filepath)
        seq_ms = round(seq_time * 1000, 2)

        # Thread counts to benchmark.  Powers of 2 are the standard progression
        # in parallel computing because they directly illustrate Amdahl's
        # diminishing returns: each doubling shows a smaller incremental gain.
        THREAD_COUNTS = [1, 2, 4, 8, 16]

        results = []
        for t in THREAD_COUNTS:
            # Re-chunk the file for the current thread count.
            chunks = chunker.get_chunks(filepath, t)

            # Run parallel analysis and record time.
            _par_counts, par_time = parallel.analyze_parallel(filepath, chunks, executor=WORKER_POOL)

            # Compute metrics for this thread count.
            m = metrics.compute_metrics(seq_time, par_time, t)

            # Theoretical speedup from Amdahl's Law using S=0.05.
            # In our I/O-bound workload, ~5% is serial:
            #   - File stat call (get_chunks)
            #   - Thread pool creation
            #   - Result merge
            theoretical = metrics.amdahl_speedup(t, serial_fraction=0.05)

            results.append({
                "threads":             t,
                "time_ms":             m["parallel_time_ms"],
                "actual_speedup":      m["speedup"],
                "theoretical_speedup": theoretical,
                "efficiency_pct":      m["efficiency_pct"],
            })

        response = {
            "filename":      original_filename,
            "file_size_kb":  file_size_kb,
            "sequential_ms": seq_ms,
            "results":       results,
        }

        return jsonify(response), 200

    except Exception as exc:
        return jsonify({"error": str(exc)}), 500

    finally:
        # Clean up the uploaded file regardless of success or failure.
        if os.path.exists(filepath):
            os.remove(filepath)


# =============================================================================
# ROUTE: GET /results/<job_id>
# =============================================================================
@app.route("/results/<job_id>", methods=["GET"])
def get_result(job_id: str) -> Response:
    """
    Retrieve a previously computed and cached analysis result by job ID.

    This allows a client to:
      1. POST /analyze → receive job_id immediately
      2. GET /results/<job_id> → fetch the result at any later time, even
         across a server restart, since results are persisted in SQLite.

    SQLite primary-key lookup is O(log n) via its B-tree index — negligible
    for the scale of this project.
    """
    result = db.get_result(job_id)
    if result is None:
        return jsonify({
            "error": f"No result found for job_id '{job_id}'."
        }), 404

    return jsonify(result), 200


# =============================================================================
# ROUTE: GET /health
# =============================================================================
@app.route("/health", methods=["GET"])
def health() -> Response:
    """
    Liveness probe — returns 200 OK so the client (or load balancer) can
    verify the server is running and responsive.

    No logic here: if this endpoint responds, the Flask app is alive.
    """
    return jsonify({"status": "ok"}), 200


# =============================================================================
# Entry point
# =============================================================================
if __name__ == "__main__":
    # Build the persistent worker pool now — see the WORKER_POOL comment
    # above for why this must stay inside this guard.
    WORKER_POOL = ProcessPoolExecutor(max_workers=32)
    atexit.register(WORKER_POOL.shutdown)

    # debug=True enables:
    #   - Auto-reload when source files change (no need to restart manually)
    #   - Detailed error pages with stack traces in the browser
    # NEVER use debug=True in production — it exposes an interactive debugger.
    # use_reloader=False because the reloader forks a second process that
    # would otherwise duplicate the worker pool; we already get fast restarts
    # are not critical for this project's local dev workflow.
    #
    # PORT is read from the project-root .env file — change it there, not here.
    app.run(debug=True, port=PORT, use_reloader=False)
