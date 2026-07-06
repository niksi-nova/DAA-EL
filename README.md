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

## 3. The algorithms, explained (with analogies)

To make it easy to explain to professors or peers, here is a detailed breakdown of each algorithm used in the pipeline.

### 3.1 Chunking (the "SPLIT" step) — `chunker.py`
**The Goal:** Divide a massive log file into $N$ roughly equal pieces so multiple workers can process them simultaneously.
**The Problem:** If we just slice the file by pure byte counts (e.g., exactly every 1MB), we might slice a line right in half. A line like `[ERROR] Connection timeout` might get cut into `[ER` and `ROR] Connection timeout`. Both workers would fail to match the regex, leading to an undercounting bug.
**The Algorithm:**
1. Calculate candidate byte boundaries: `file_size / N`.
2. For each boundary (except the start and end of the file), open the file and seek to that exact byte.
3. Read forward byte-by-byte until we hit the first newline character (`\n`).
4. Lock in that newline position as the *real* boundary. 
**Analogy:** Imagine tearing a book into equal chapters for friends to read. Instead of ripping pages exactly in half blindly, you find the closest end-of-paragraph to tear along, ensuring no one gets half a sentence.
- **Time Complexity:** $O(T)$ — $T$ fast forward-seeks.
- **Space Complexity:** $O(T)$ — Storing just the $T$ byte-range tuples.

### 3.2 Sequential baseline — `sequential.py`
**The Goal:** Count the log levels using a single thread. This serves as our "control" in the experiment to prove that our parallel counts are correct and to act as a baseline for speedup.
**The Algorithm:**
1. Open the file normally.
2. Read line by line from top to bottom.
3. Apply a pre-compiled Regular Expression (`\[(INFO|WARNING|ERROR|DEBUG|CRITICAL)[^\]]*\]`) to check if the line contains a log level.
4. Increment the corresponding integer counter.
**Analogy:** One person reading a massive stack of papers top-to-bottom, keeping a tally on a piece of paper.
- **Time Complexity:** $O(N)$ where $N$ is the total number of lines.
- **Space Complexity:** $O(1)$ — Only five integer counters are held in memory regardless of how huge the file is.

### 3.3 Parallel (process pool) — `parallel.py`
**The Goal:** Distribute the counting workload across multiple CPU cores to finish faster.
**The Algorithm (MAP + REDUCE):**
- **MAP:** The chunker gives each worker process a specific byte range (e.g., bytes 1000 to 4500). The worker opens the file, seeks to byte 1000, reads until 4500, and counts the log levels into its own *local* dictionary.
- **REDUCE:** Once all workers finish, the main process gathers all the local dictionaries and sums them together (`total_errors = worker1_errors + worker2_errors...`).

**Crucial Design Decision: Processes vs Threads.** 
In Python, the Global Interpreter Lock (GIL) prevents multiple *threads* from executing Python bytecode simultaneously. If we used a `ThreadPoolExecutor`, threads would just take turns on a single CPU core, giving zero speedup. By using a `ProcessPoolExecutor`, we spawn entirely separate OS processes. Each has its own GIL, meaning they genuinely run on separate CPU cores at the exact same time.
**Analogy:** Instead of one person reading 1000 pages, you hire 4 independent people. You give them 250 pages each. They read them in separate rooms simultaneously and hand you 4 sticky notes with their final tallies. You just add the 4 sticky notes together.
- **Time Complexity:** $O(N/T)$ parallel phase + $O(T)$ reduce step + Process creation overhead.
- **Space Complexity:** $O(N/T)$ per worker to hold its chunk of bytes.

### 3.4 mmap parallel — `parallel.py`
**The Goal:** Eliminate the overhead of copying data from the operating system's memory into Python's memory.
**The Algorithm:**
Normally, when you call `read()`, the OS reads from the disk into its own "Kernel buffer", and then copies that data *again* into your application's "User-space buffer" (Python variables). 
Memory-mapping (`mmap`) bypasses this double-copy. It maps the file directly into the application's virtual address space. The worker can slice bytes directly out of the OS page cache as if it were a giant byte array in RAM.
Because `mmap` objects cannot be easily shared across separate OS processes in Python, each worker opens its *own* mapping of the file.
**Analogy:** Instead of photocopying pages from a master library book to give to your workers (`read()`), you give them a magical glass that lets them look directly at the master book's pages sitting in the library (`mmap`).
- **Time/Space Complexity:** Asymptotically identical to standard parallel, but with a much smaller constant factor (faster execution) due to reduced I/O bottlenecks.

### 3.5 Metrics & Amdahl's Law — `metrics.py`
**The Goal:** Quantify exactly how much faster we got, and compare it against the theoretical limits of computer science.
- **Speedup:** `sequential_time / parallel_time`. If this is 2.0, the parallel version was twice as fast.
- **Efficiency:** `(speedup / num_threads) * 100`. If 4 threads give a 2.0x speedup, efficiency is 50%. You rarely get 100% due to overhead.
- **Amdahl's Law:** A formula `Speedup = 1 / (S + (1-S)/T)`. 
  - $S$ is the strictly serial part of the task (e.g., chunking the file, booting up the processes, reducing the final counts).
  - Even with infinite processors ($T \to \infty$), your speedup will never exceed `1 / S`. If 5% of the task is serial overhead, the absolute maximum speedup you can *ever* get is 20x, no matter how many cores you buy. This law is visually plotted in our frontend benchmark chart!

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

## 8. Future Improvements

While this project successfully demonstrates the core concepts of parallel processing and algorithm design, there are several avenues for future enhancement:

1.  **Distributed Processing (MapReduce Cluster):** Moving from a single-machine multi-process architecture to a multi-machine distributed architecture (using tools like Apache Hadoop, Apache Spark, or a custom distributed task queue like Celery with RabbitMQ). This would allow scaling beyond the core count of a single machine.
2.  **Streaming Data Support:** Currently, the system analyzes static, pre-existing log files. An improvement would be to support real-time log ingestion (e.g., tailing a live log file or receiving logs over a network socket) and maintaining running counts using sliding window algorithms.
3.  **Advanced Regex & Parsing:** Expanding the parsing capabilities beyond simple regex matching of log levels. This could include parsing timestamps to identify temporal anomalies (e.g., sudden spikes in error rates) or extracting specific IP addresses and request paths for deeper analytics.
4.  **Persistent Caching & Indexing:** Implementing an inverted index on the log files to allow for rapid free-text searching alongside the level aggregation, potentially using tools like Elasticsearch or creating a simplified custom indexer.
5.  **Dynamic Work Stealing:** The current chunking strategy divides the file evenly upfront. If some chunks have significantly longer lines or more complex data, worker imbalance can occur. Implementing a dynamic "work stealing" queue where faster workers can pick up remaining chunks would improve CPU utilization on uneven data.

---

## 9. Configuring the port (single `.env` file)

The backend port lives in **one place**: the `.env` file at the project root
(next to this README, one level above both `backend/` and `frontend/`):

```
PORT=5002
```

To change it, edit that one line — nothing else needs touching:
- `backend/app.py` reads it directly (a tiny built-in parser, no extra
  dependency) and binds Flask to it.
- `frontend/vite.config.js` points Vite's env loader (`envDir: '../'`) at the
  same root `.env` and whitelists the bare `PORT` key via `envPrefix`, so
  `frontend/src/api.js` can read `import.meta.env.PORT` and build the right
  `http://localhost:<PORT>` base URL automatically.

Both sides fall back to `5000` if `.env` is missing, so the app still runs
without it — but keeping the file in sync means you only ever edit one number.

---

## 10. Running everything from scratch

```bash
# Backend
cd backend
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
python log_generator.py        # one-time: create sample log files
python test_engine.py          # one-time: verify correctness before starting the server
python app.py                  # starts Flask on http://127.0.0.1:<PORT from .env>

# Frontend (separate terminal)
cd frontend
npm install
npm run dev                    # starts Vite dev server, reads the same PORT from ../.env
```

`results.db` and `uploads/*.log` are not committed to git (see `.gitignore`) —
run `log_generator.py` to regenerate sample data on a fresh clone.
