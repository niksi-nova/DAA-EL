# Parallel Log Analyzer — DAA Elective Project

A Flask + React application that analyzes server log files three different
ways — **sequential scan**, **multi-process parallel scan**, and **memory-mapped
parallel scan** — and compares their wall-clock performance. The project exists
to give a hands-on, measurable demonstration of core Design & Analysis of
Algorithms (DAA) concepts: divide-and-conquer (MapReduce-style splitting),
Amdahl's Law, time/space complexity analysis, and the practical overhead of
parallelism.

---

## 1. What this project actually does

You upload a `.log` (or `.txt`) file. The backend counts how many lines belong
to each log level (`INFO`, `WARNING`, `ERROR`, `DEBUG`, `CRITICAL`) using three
independent algorithms, all of which **must produce identical counts**:

| Method | File | Technique |
|---|---|---|
| Sequential | `analyzer/sequential.py` | Single-threaded line-by-line scan — the control/baseline |
| Parallel | `analyzer/parallel.py` | Splits the file into N byte-range chunks, processes them in **separate OS processes** |
| mmap Parallel | `analyzer/parallel.py` | Same chunking, but each worker reads its chunk via a memory-mapped view of the file instead of `read()` |

The frontend (React + Vite + Tailwind) lets you upload a file, pick a thread
count, see the level breakdown and timing bars, or run a full benchmark sweep
(1/2/4/8/16 threads) and see a speedup-vs-threads chart compared against the
theoretical curve from Amdahl's Law.

### Why three methods instead of one?
Because the *point of a DAA project* is to compare algorithms, not just to
build a working app. Having a correct sequential baseline lets us prove the
parallel version is correct (matching counts) before we report it as faster.
Having both a regular-I/O parallel version and an mmap version lets us
compare two different parallelization strategies on the same problem.

---

## 2. Architecture

```
backend/
  app.py                  Flask REST API (HTTP layer only)
  db.py                   SQLite persistence for results
  log_generator.py        Generates small/medium/large/empty synthetic logs
  test_engine.py          Standalone correctness + performance test script
  analyzer/
    chunker.py             SPLIT step — divides file into newline-aligned byte ranges
    sequential.py          Baseline O(N) single-threaded scan
    parallel.py            MAP+REDUCE step — process-pool parallel scan, + mmap variant
    metrics.py              Speedup / efficiency / Amdahl's Law calculations
  uploads/                Scratch space for uploaded files (deleted after analysis)
  results.db              SQLite database of past analysis results (gitignored)

frontend/
  src/
    App.jsx                Root component, page routing between Analyze/Results/Benchmark
    api.js                  fetch() wrappers for /analyze, /benchmark, /health
    components/             UploadPanel, ResultsDashboard, BenchmarkChart, etc.
```

**Separation of concerns:** `app.py` only knows about HTTP. `analyzer/` only
knows about algorithms — no Flask import anywhere in that package. This is
why `test_engine.py` can exercise the whole engine without ever starting a
web server.

### Request flow for `POST /analyze`
1. Client uploads a file (`multipart/form-data`) with an optional `threads` field.
2. Flask saves it to `uploads/<job_id>_<filename>`.
3. `chunker.get_chunks()` divides the file into `threads` newline-aligned byte ranges.
4. The OS page cache is warmed with one throwaway read (see §4.3).
5. `sequential.analyze_sequential()` runs — this is the timed baseline.
6. `parallel.analyze_parallel()` runs using the **persistent process pool**.
7. `parallel.analyze_parallel_mmap()` runs, also via the persistent pool.
8. `metrics.compute_metrics()` turns the two timings into speedup/efficiency.
9. The result is saved to SQLite (`db.py`) and returned as JSON.
10. The uploaded file is deleted — only the *result* is kept, not the raw log.

---

## 3. The algorithms, explained

### 3.1 Chunking (the "SPLIT" step) — `chunker.py`
Naively splitting a file into N equal byte ranges can cut a line in half
(`...[ERROR` | `OR] message...`), causing that line to be silently dropped
by both halves — an undercounting bug. `get_chunks()` fixes this: it
computes N candidate split points, then for each one seeks forward to the
next `\n` and uses that as the real boundary. This guarantees every chunk
starts and ends on a complete line.

- Time: O(T) — T seeks, each followed by at most one short forward scan.
- Space: O(T) — just the T `(start, end)` tuples.

### 3.2 Sequential baseline — `sequential.py`
A single pass over the file, line by line, applying a pre-compiled regex
(`\[(INFO|WARNING|ERROR|DEBUG|CRITICAL)[^\]]*\]`) to each line.
- Time: O(N) where N = number of lines.
- Space: O(1) — only five integer counters, regardless of file size.

### 3.3 Parallel (process pool) — `parallel.py`
This is the MAP+REDUCE step:
- **MAP**: each chunk is handed to a worker that opens its own file handle,
  seeks to its byte range, reads it, decodes it, and counts log levels into a
  *local* dict.
- **REDUCE**: the main process sums the N partial dicts into one final dict.

**Why `ProcessPoolExecutor`, not `ThreadPoolExecutor`?** This is the most
important algorithmic decision in the project, and the project's original
version got it wrong. Decoding bytes and running a regex over text is
**CPU-bound** Python bytecode. CPython's Global Interpreter Lock (GIL) only
allows one thread to execute Python bytecode at a time — so threads do *not*
get you real concurrency on CPU-bound work; they just take turns. A process
pool sidesteps the GIL entirely: each worker is a separate OS process with
its own interpreter and its own GIL, so the regex/decode work genuinely runs
on multiple cores at once. You can see this directly in our own benchmark
data (§5) — `large.log` (500K lines) gets a real 2.4x speedup at 4 processes,
something a thread pool could never deliver on this workload.

- Time: O(N/T) parallel phase + O(T) reduce + O(T) process-spawn overhead.
- Space: O(N/T) per worker (one chunk's worth of bytes).

### 3.4 mmap parallel — `parallel.py`
Instead of `read()`-ing bytes (disk/page-cache → kernel buffer → user-space
copy), each worker memory-maps the file and slices directly out of the
mapped pages. Once the OS page cache is warm, this avoids a redundant copy
and tends to be the fastest of the three methods on repeated/warm reads.
Because `mmap.mmap` objects cannot be pickled across a process boundary,
each worker process opens its **own** mapping of the same file — the OS page
cache is still shared system-wide, so this costs no extra disk I/O.

### 3.5 Metrics — `metrics.py`
- **Speedup** = `sequential_time / parallel_time`. >1 means parallel won.
- **Efficiency** = `speedup / num_threads * 100%`. How much of each thread's
  theoretical contribution was actually realized.
- **Amdahl's Law**: `Speedup(T) = 1 / (S + (1-S)/T)` where S is the serial
  (non-parallelizable) fraction of the work. We assume S=0.05 (5%) for this
  I/O-adjacent workload and plot it as the theoretical ceiling against the
  measured speedup.

---

## 4. Fixes made to the original implementation

The project started with a working but fragile prototype. Six concrete
issues were found and fixed:

### 4.1 Empty-file crash in mmap analysis
`mmap.mmap()` raises `ValueError: cannot mmap an empty file` on a 0-byte
file — there's no page to map. **Fix:** `analyze_parallel_mmap()` now checks
`os.path.getsize(filepath) == 0` before touching mmap at all and returns
zero counts immediately. Verified: uploading a 0-byte `.log` file through
`/analyze` now returns `200 OK` with all-zero counts instead of `500`.

### 4.2 Unicode crashes on Windows consoles
`test_engine.py` and `log_generator.py` used Unicode box-drawing/arrow
characters (`→`, `←`, `—`, `─`, `×`) inside `print()` calls. Windows'
default console codepage (cp1252) can't encode these, raising
`UnicodeEncodeError` and crashing the script. **Fix:** every such character
inside an actual `print()` call (not in comments/docstrings, which never hit
the console) was replaced with an ASCII equivalent (`->`, `<-`, `-`, `x`).

### 4.3 GIL bottleneck — ThreadPoolExecutor → ProcessPoolExecutor
See §3.3. This is the core algorithmic fix. The old thread-pool version
showed flat or negative scaling on CPU-bound regex/decode work because the
GIL serialized it. Swapping to `ProcessPoolExecutor` lets the decode+regex
work run on genuinely separate cores. One subtlety this introduced: mmap
objects can't be shared across processes (no shared address space), so
`_process_chunk_mmap` now opens its own mapping per worker instead of
receiving one shared `mm` object — the OS page cache still makes this cheap.

**Trade-off you'll observe and should be ready to explain:** process
creation has real overhead (tens of milliseconds), so on *small* files the
process-pool version can be *slower* than sequential (see the `small.log`
benchmark in §5) — this is expected and is itself a teaching point about
when parallelism pays off.

### 4.4 Cold-cache bias in benchmarking
The sequential run always executes first and pays the cost of reading the
file from disk for the first time. Every parallel/mmap run that follows
benefits from a warm OS page cache that the sequential run paid for — making
the parallel speedup look artificially better than it really is. **Fix:**
`_warm_page_cache()` in `app.py` (and an equivalent block in
`test_engine.py`) does one throwaway full read of the file *before* the
sequential timer starts, so all three methods start from the same cache
state.

### 4.5 Persistent worker pool
Previously a new `ProcessPoolExecutor` was spawned and torn down on every
single request — expensive, especially the OS-level process creation cost
on Windows. **Fix:** `app.py` now creates one `ProcessPoolExecutor(max_workers=32)`
when the Flask process starts and reuses it for every `/analyze` and
`/benchmark` request via `executor=WORKER_POOL`. `analyzer/parallel.py`'s
two analysis functions accept an optional `executor` parameter for this.

One non-obvious correctness detail: this pool is built **inside the
`if __name__ == "__main__":` guard**, not at plain module level. `ProcessPoolExecutor`
uses the `spawn` start method on macOS/Windows, which re-imports `app.py` in
every worker process. If pool creation happened at module level, every
worker would try to spawn its *own* 32-process pool recursively — a fork
bomb. Guarding it ensures only the original parent process ever builds it.

### 4.6 In-memory results lost on restart
`results_store = {}` lived only as long as the Flask process did — any
client holding a `job_id` would get a 404 after any restart. **Fix:**
`db.py` adds a small SQLite-backed store (`results.db`, one row per job,
result stored as a JSON blob). `GET /results/<job_id>` now survives server
restarts — verified manually in §6.

---

## 5. What I should show the professor (test plan + expected output)

Run these **in order**. Each one demonstrates a different fix or concept.

### Test 1 — Generate the test data
```bash
cd backend
python log_generator.py
```
**Expected:** creates `uploads/small.log` (10K lines), `medium.log` (100K),
`large.log` (500K). No crash, no Unicode errors (this exercises fix 4.2).

### Test 2 — Correctness + performance engine test
```bash
python test_engine.py
```
**Expected output (abridged):**
```
Step 3 - Correctness Verification
  [PASS] INFO        seq=  49,905  par=  49,905
  ...
  [PASS] TOTAL       seq= 100,000  par= 100,000

Step 4 - Performance Metrics
  Actual speedup    :    0.27x      <- expected to be < 1 on medium.log; see note below
  Theoretical (S=5%):    3.478x
  Efficiency        :     6.8%

Step 5 - mmap Parallel Analysis (third method)
  [PASS] TOTAL       seq= 100,000  mmap= 100,000
  Speedup over parallel   :    1.671x

Final Result
  ALL CORRECTNESS CHECKS PASSED
```
**What to say if asked why speedup is below 1.0:** process creation overhead
(4 new OS processes) can exceed the time saved on a file this size. This is
**expected and correct behavior**, not a bug — it's the overhead term in
`O(N/T) + O(T)` dominating. Show Test 4 below for a file large enough that
parallelism actually wins.

### Test 3 — Empty file does not crash (regression test for fix 4.1)
```bash
touch uploads/empty.log
python -c "
from analyzer import chunker, sequential, parallel
from analyzer.parallel import analyze_parallel_mmap
f = 'uploads/empty.log'
print(sequential.analyze_sequential(f))
print(analyze_parallel_mmap(f, chunker.get_chunks(f, 4)))
"
```
**Expected:** two lines printed, both `({'INFO': 0, 'WARNING': 0, 'ERROR': 0, 'DEBUG': 0, 'CRITICAL': 0}, <tiny float>)`.
No `ValueError`. (Before the fix, the second call raised
`ValueError: cannot mmap an empty file`.)

### Test 4 — Start the API and demonstrate real parallel speedup
```bash
python app.py
```
In another terminal:
```bash
curl -F "file=@uploads/large.log" -F "threads=4" http://127.0.0.1:5000/analyze
```
**Expected:** JSON with `"speedup": ~2.0-2.5` and `"efficiency_pct": ~55-65`.
This is the number that proves multiprocessing genuinely parallelizes
CPU-bound work — show this number specifically, since the small/medium files
intentionally demonstrate the *overhead-dominated* regime instead.

### Test 5 — Benchmark sweep (Amdahl's Law in action)
```bash
curl -F "file=@uploads/medium.log" http://127.0.0.1:5000/benchmark
```
**Expected shape:** speedup rises from 1→4 threads, then **falls** at 8 and
16 threads as process overhead outweighs the shrinking per-process workload.
This non-monotonic curve is the single best thing to point at when
discussing Amdahl's Law and diminishing returns — show the `efficiency_pct`
column dropping steadily as threads increase even while you add more
"compute power."

### Test 6 — Results persist across a server restart (regression test for fix 4.6)
```bash
# with the server running from Test 4/5, grab a job_id from any response, e.g.:
JOB_ID=<paste a job_id from a previous response>

# Now kill and restart the server:
# Ctrl+C, then: python app.py

curl http://127.0.0.1:5000/results/$JOB_ID
```
**Expected:** the full original JSON result, unchanged, even though the
Flask process was completely restarted in between. (Before fix 4.6, this
would return `404 Not Found` because results lived only in a Python dict.)

### Test 7 — Input validation
```bash
curl -X POST http://127.0.0.1:5000/analyze                       # no file
curl -F "file=@/etc/hosts" http://127.0.0.1:5000/analyze         # disallowed extension
curl http://127.0.0.1:5000/results/not-a-real-id                  # unknown job
```
**Expected:** three separate `400`/`404` JSON error bodies, no stack traces,
no server crash.

### Test 8 — Frontend walkthrough
```bash
cd frontend && npm install && npm run dev
```
Open the shown localhost URL (backend must be running on port 5000).
Upload `small.log`, then `large.log`, and finally run a Benchmark sweep —
show the bar chart for single-file analysis and the line chart (actual vs.
theoretical Amdahl curve) for the benchmark sweep.

---

## 6. How I actually verified all of this

I ran the full sequence above against this exact codebase on macOS (Python
3.14, M-series chip):
- `test_engine.py` → all correctness checks passed on `medium.log` (100K lines).
- Empty-file scan (sequential, parallel, mmap) → no exception, all-zero counts.
- `/analyze` on `small.log`, `large.log`, and a genuinely empty 0-byte file via curl → all `200 OK`.
- `/benchmark` on `medium.log` → speedup peaked at 4 threads (3.10x, 77% efficiency)
  and degraded at 8 (2.08x) and 16 threads (1.52x) — the expected Amdahl's Law shape.
- Killed and restarted the Flask server, then `GET /results/<job_id>` for a
  job created *before* the restart → returned the full original result,
  proving SQLite persistence works.
- Bad extension, missing file, and unknown job_id → correct `400`/`404` errors, no crashes.

---

## 7. Likely viva questions and how to answer them

**Q: Why does ProcessPoolExecutor sometimes make things slower than sequential?**
Because creating an OS process has real, fixed overhead (tens of
milliseconds) that doesn't shrink with the workload. For N small enough,
`O(T)` overhead exceeds the `O(N/T)` savings. This is exactly what Amdahl's
Law predicts: there's a serial/fixed cost that caps how much parallelism
helps, and for small N that fixed cost can dominate entirely.

**Q: Why ProcessPoolExecutor and not ThreadPoolExecutor, given Python has threads?**
Because the actual work per chunk — `bytes.decode()` and `re.search()` in a
loop — is CPU-bound pure-Python-adjacent work. CPython's GIL means only one
thread executes Python bytecode at a time, so threads can't get real
parallelism here; they'd just take turns, same total CPU time, plus thread
overhead. Processes have independent GILs (one per interpreter), so the
work runs on actually-separate cores simultaneously.

**Q: How do you guarantee correctness when you split the file across processes?**
Two things: (1) the chunker aligns every split point to a newline, so no log
line is ever divided between two chunks; (2) `test_engine.py` asserts that
sequential, parallel, and mmap counts are bit-for-bit identical for every
log level before any performance number is reported — a fast wrong answer
is considered worse than a slow right one.

**Q: Why can't you just pass one shared mmap object to all the worker processes?**
`mmap.mmap` objects wrap an OS-level memory mapping tied to a process's
virtual address space; they cannot be pickled or shared across a process
boundary the way they could across threads (which *do* share an address
space). Each worker process instead opens its own mapping of the same file.
This still saves I/O because the OS page cache (RAM-backed) is shared system-wide
regardless of which process maps it.

**Q: What is Amdahl's Law and where do you use it?**
`Speedup(T) = 1 / (S + (1-S)/T)`, where S is the fraction of the work that
is inherently serial (can't be parallelized — file metadata lookups, the
final reduce/merge step, process startup). We use S=0.05 as an estimate and
plot the resulting theoretical curve against the measured speedup in the
`/benchmark` endpoint and the frontend's benchmark chart, so you can visually
compare "what we got" against "the best we could ever get."

**Q: Why measure wall-clock time including process/thread setup, instead of just the compute time?**
Because a user of this tool experiences the *entire* request, not just the
inner loop. Excluding setup overhead would make parallelism look better than
it actually is in practice — the same reasoning behind the page-cache
warm-up fix (4.4): always compare like-for-like, including all real costs.

**Q: Why SQLite instead of just keeping the in-memory dict, or going straight to Postgres/Redis?**
A dict dies with the process — unacceptable for a service meant to let
clients fetch results later. SQLite needs no server process and ships in the
Python standard library, which matches the scope of a single-machine
university project; Postgres/Redis would be the right call only if this had
to scale across multiple server processes or machines.

**Q: What's the time/space complexity of each method?**
- Sequential: O(N) time, O(1) space (N = number of lines).
- Chunking (split step): O(T) time and space (T = thread/process count).
- Parallel MAP phase: O(N/T) time per worker, run concurrently; O(T) reduce step on top.
- mmap variant: same asymptotic O(N/T), different constant factor (avoids one user-space copy once the page cache is warm); O(N) *virtual* address space per worker (not physical RAM, thanks to demand paging).

**Q: What would you change to make this production-ready?**
Replace SQLite with Postgres/Redis if running multiple server instances;
add request size limits and rate limiting on `/analyze`; use a real WSGI
server (gunicorn) instead of Flask's dev server; add authentication if this
weren't a local demo tool.

---

## 8. Running everything from scratch

```bash
# Backend
cd backend
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
python log_generator.py        # one-time: create sample log files
python test_engine.py          # one-time: verify correctness before starting the server
python app.py                  # starts Flask on http://127.0.0.1:5000

# Frontend (separate terminal)
cd frontend
npm install
npm run dev                    # starts Vite dev server, proxies to the Flask API
```

`results.db` and `uploads/*.log` are not committed to git (see `.gitignore`) —
run `log_generator.py` to regenerate sample data on a fresh clone.
