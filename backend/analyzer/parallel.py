# =============================================================================
# analyzer/parallel.py
# =============================================================================
# PURPOSE:
#   Provide the parallel (multi-threaded) analysis of a log file using a
#   thread pool.  This is the core algorithmic contribution of the project.
#
# THE MAP-REDUCE ANALOGY (ENTIRE PIPELINE):
# ──────────────────────────────────────────
#   Step 1 — SPLIT  : chunker.get_chunks()     → divide file into T byte ranges
#   Step 2 — MAP    : _process_chunk()          → each thread counts its slice
#   Step 3 — REDUCE : merge loop in analyze_parallel() → sum partial counts
#
#   This mirrors Google's original MapReduce paper (Dean & Ghemawat, 2004)
#   and Apache Hadoop's TextInputFormat + Mapper + Reducer pipeline,
#   implemented here at the single-machine, single-file scale.
#
# WHY NO RACE CONDITIONS IN THIS DESIGN?
# ──────────────────────────────────────
#   A race condition occurs when two threads read AND write a SHARED variable
#   concurrently without synchronisation.  This design eliminates shared
#   mutable state during the parallel phase entirely:
#
#     - Each thread opens its OWN file handle (not shared).
#     - Each thread writes only to its OWN local `counts` dict (not shared).
#     - No global variables are mutated during the parallel phase.
#     - The ONLY shared state is the ThreadPoolExecutor's internal job queue,
#       which is thread-safe by design (it uses its own lock internally).
#
#   After all threads finish, the MAIN thread (single-threaded) performs the
#   merge — at that point no other thread is running, so again no races.
#
# WHY PYTHON'S GIL DOES NOT BLOCK US HERE:
# ──────────────────────────────────────────
#   Python has a Global Interpreter Lock (GIL) that prevents two threads from
#   executing Python bytecode simultaneously.  This means CPU-bound work (e.g.,
#   pure Python number crunching) does NOT benefit from threading in CPython.
#
#   However, this task is I/O-BOUND: each thread spends most of its time
#   WAITING for the OS to read disk blocks into memory.  During an I/O wait,
#   the GIL is RELEASED, allowing other threads to run.  So multiple threads
#   CAN overlap their disk reads in time even under the GIL.
#
#   Result: meaningful real-world speedup despite the GIL, because the
#   bottleneck is disk I/O, not Python interpreter throughput.
#
# THREADPOOLEXECUTOR vs. MANUALLY CREATING threading.Thread OBJECTS:
# ────────────────────────────────────────────────────────────────────
#   Manual approach (DO NOT DO):
#       threads = [threading.Thread(target=...) for _ in range(T)]
#       for t in threads: t.start()
#       for t in threads: t.join()
#       # results must be collected via a shared list (needs a lock or careful
#       # indexing), and errors in threads are silently swallowed unless you
#       # add explicit exception handling.
#
#   ThreadPoolExecutor approach (THIS FILE):
#       with ThreadPoolExecutor(max_workers=T) as pool:
#           futures = [pool.submit(fn, *args) for ...]
#           results = [f.result() for f in futures]
#       # f.result() re-raises any exception that occurred inside the thread,
#       # so errors are surfaced automatically.  No manual join() needed.
#       # The context manager guarantees all threads finish before exit.
#
#   The pool is also REUSABLE for multiple submissions, though here we create
#   a fresh pool per call to keep the API simple.
#
# TIME COMPLEXITY ANALYSIS:
# ──────────────────────────
#   Let N = number of lines in the file, T = number of threads.
#
#   Parallel phase: each thread processes N/T lines → O(N/T) per thread.
#                   T threads run concurrently   → O(N/T) wall-clock time.
#
#   Merge phase:    sum T partial dicts, each with 5 keys → O(T * 5) = O(T).
#
#   Thread overhead: creating and destroying T threads → O(T).
#
#   Total wall-clock: O(N/T) + O(T)
#
#   For large N and small T (the common case), O(N/T) dominates and the
#   total is effectively O(N/T) — a T-fold improvement over sequential O(N).
#   For very small N, the O(T) overhead can exceed the O(N/T) savings,
#   which is why small.log may show speedup < 1 — this is the expected result
#   and is an important teaching moment about parallel algorithm overhead.
# =============================================================================

import os
import re
import time
from concurrent.futures import ProcessPoolExecutor, Future
from typing import Dict, List, Tuple

# Compile the regex pattern ONCE at module load (same reasoning as in
# sequential.py — avoid O(N * T) recompilations across all threads).
# Each thread calls .search() on its own lines; the compiled pattern object
# is read-only and therefore thread-safe (Python's re module guarantees this).
LOG_LEVEL_PATTERN = re.compile(r"\[(INFO|WARNING|ERROR|DEBUG|CRITICAL)[^\]]*\]")

LOG_LEVELS = ("INFO", "WARNING", "ERROR", "DEBUG", "CRITICAL")


def _process_chunk(filepath: str, start_byte: int, end_byte: int) -> Dict[str, int]:
    """
    MAP step: read and analyse one byte-range chunk of `filepath`.

    This function is designed to be called concurrently by multiple threads
    without any synchronisation primitives (locks, semaphores).  It achieves
    this by having NO shared mutable state:

      - Opens its own file handle → each thread gets a separate OS file
        descriptor.  File descriptors are per-process resources, and the OS
        allows multiple descriptors pointing to the same file.  Seeking one
        descriptor does NOT affect the position of another.  This is what
        makes independent random access to the same file safe in parallel.

      - Creates its own local `counts` dict → no other thread can see this
        variable; it lives entirely on this thread's call stack.  When the
        function returns, the dict is handed back to the executor's result
        queue — a thread-safe operation handled by ThreadPoolExecutor.

    Parameters
    ──────────
    filepath   : Path to the log file.
    start_byte : Byte offset where this thread's slice begins (inclusive).
    end_byte   : Byte offset where this thread's slice ends (exclusive).

    Returns
    ───────
    A dict {level: count} for lines within [start_byte, end_byte).

    Time complexity:  O(N/T) where N/T = number of lines in this chunk.
    Space complexity: O(1) — only the 5-entry counts dict is stored.
    """
    # Local counts dict — entirely private to this thread invocation.
    counts: Dict[str, int] = {level: 0 for level in LOG_LEVELS}

    # Open in binary mode ('rb') for the same reason as the chunker:
    # we need byte-accurate seeking.  We decode to text manually below.
    with open(filepath, "rb") as f:
        # Seek directly to this chunk's start byte.
        # f.seek() is O(1) — a single lseek() system call.
        # This is the payoff for the chunker's O(T) work: each thread can
        # jump straight to its data without reading past other chunks.
        f.seek(start_byte)

        # Read exactly (end_byte - start_byte) bytes — no more, no less.
        # This is the chunk's raw content.
        chunk_bytes = f.read(end_byte - start_byte)

    # Decode bytes to a Python str.
    # errors='ignore' drops any bytes that are not valid UTF-8.  This is
    # the correct choice for log analysis: we prefer to silently skip a
    # malformed byte rather than raise an exception and lose the entire chunk.
    chunk_text = chunk_bytes.decode("utf-8", errors="ignore")

    # Split the decoded text into individual lines.
    # splitlines() handles '\n', '\r\n', and '\r' — more robust than
    # split('\n') which would leave a trailing '\r' on Windows-style files.
    for line in chunk_text.splitlines():
        match = LOG_LEVEL_PATTERN.search(line)
        if match:
            level = match.group(1)
            counts[level] += 1

    return counts


def analyze_parallel(
    filepath: str,
    chunks: List[Tuple[int, int]],
    executor: "ProcessPoolExecutor | None" = None,
) -> Tuple[Dict[str, int], float]:
    """
    Orchestrate the parallel analysis: submit MAP tasks, collect results,
    then REDUCE (merge) the partial counts into a single final dict.

    Parameters
    ──────────
    filepath : Path to the log file.
    chunks   : List of (start_byte, end_byte) tuples from chunker.get_chunks().
               len(chunks) determines the number of worker threads used.

    Returns
    ───────
    (counts, elapsed_seconds)
      counts          : Merged dict {level: total_count} for the whole file.
      elapsed_seconds : Wall-clock time for the ENTIRE parallel operation,
                        including thread creation, all MAP work, and the REDUCE
                        merge.  This is what we compare to sequential time.

    Why we time the ENTIRE operation (including thread overhead):
    ─────────────────────────────────────────────────────────────
    If we only timed the pure compute part (inside the threads), we would
    be measuring best-case performance that ignores real costs:
      - Thread creation and warm-up time
      - Result collection from futures
      - Merge (reduce) time
    All of these are part of the actual wall-clock experience.  A fair
    comparison with sequential must include ALL costs on both sides.
    """
    num_threads = len(chunks)

    # ── Start the high-resolution monotonic timer ────────────────────────────
    start_time = time.perf_counter()

    # ── MAP PHASE ────────────────────────────────────────────────────────────
    # Submit one _process_chunk task per chunk.  submit() is non-blocking —
    # it enqueues the work and immediately returns a Future object.
    #
    # We collect all futures in a list so we can wait for ALL of them before
    # starting the reduce phase (no partial merges — this keeps the design simple
    # and avoids the complexity of streaming reduction).
    #
    # If the caller passed a pre-built `executor` (e.g. app.py's persistent,
    # process-wide pool), reuse it instead of spawning/tearing down a fresh
    # ProcessPoolExecutor on every call — process creation has real OS
    # overhead, so a persistent pool avoids paying it on every request.
    futures: List[Future] = []
    if executor is not None:
        for start_byte, end_byte in chunks:
            futures.append(executor.submit(_process_chunk, filepath, start_byte, end_byte))
        for future in futures:
            future.result()  # propagate any worker exception now
    else:
        with ProcessPoolExecutor(max_workers=num_threads) as local_executor:
            for start_byte, end_byte in chunks:
                future = local_executor.submit(_process_chunk, filepath, start_byte, end_byte)
                futures.append(future)
            # The 'with' block blocks here until ALL submitted tasks are complete.
            # ProcessPoolExecutor spawns real OS processes, each with its own GIL,
            # so the CPU-bound decode/regex work actually runs concurrently across
            # cores instead of being serialised by a single shared GIL.

    # ── REDUCE PHASE ─────────────────────────────────────────────────────────
    # All threads have finished.  We are now single-threaded again (the main
    # thread).  Merge the T partial count dicts into one final dict.
    #
    # Algorithmic note: this is the REDUCE step of Map-Reduce.
    # Each partial dict has exactly 5 keys (the log levels).  Summing T dicts
    # of constant size is O(T * 5) = O(T) — negligible compared to O(N/T) MAP.
    #
    # We use f.result() to retrieve the return value of _process_chunk().
    # Crucially, if the thread raised an exception, f.result() re-raises it
    # here in the main thread, so errors are never silently swallowed.
    merged: Dict[str, int] = {level: 0 for level in LOG_LEVELS}
    for future in futures:
        partial_counts = future.result()  # Blocks until this future is done.
        for level in LOG_LEVELS:
            merged[level] += partial_counts[level]

    # ── Stop the timer ───────────────────────────────────────────────────────
    elapsed = time.perf_counter() - start_time

    return merged, elapsed


# =============================================================================
# MEMORY-MAPPED VARIANTS
# =============================================================================
#
# WHAT IS mmap?
# ─────────────
# mmap (memory-mapped file I/O) is a mechanism provided by the OS kernel that
# maps a file directly into the process's virtual address space.  Instead of
# issuing explicit read() system calls that copy data from kernel buffers into
# user-space buffers, the process accesses file content via ordinary memory
# load instructions.  The OS page-fault handler brings in the required 4 KB
# pages on demand — and once brought in, the data lives in the page cache
# (RAM) for as long as the OS decides it is useful.
#
# WHY IS mmap FASTER THAN REGULAR READ() FOR REPEATED ACCESS?
# ────────────────────────────────────────────────────────────
# Regular read() path:
#   disk → kernel page cache → copy into user-space buffer → your code
#
# mmap path (first access):
#   disk → kernel page cache → page is mapped; no extra copy → your code
#
# mmap path (subsequent access / OS still has page in cache):
#   kernel page cache → your code   (disk is NOT touched at all)
#
# Because all three analysis methods (sequential, parallel, mmap) run on the
# same file in the same process during a single benchmark, the OS page cache
# is likely still warm from the sequential run.  With mmap, subsequent reads
# come straight from RAM — no system call, no kernel-to-user copy overhead.
# This is the ~100× faster claim: RAM latency (~100 ns) vs. SSD latency
# (~100 µs) is indeed ~1000× on a cold cache, and RAM vs. memcpy overhead
# is ~10–100× on a warm cache.
#
# NOTE ON THE M5 PRO SSD:
# The Apple M5 Pro has an NVMe SSD with sequential read speeds exceeding
# 7 GB/s.  This is far faster than the ~500 MB/s typical of SATA SSDs, and
# it narrows the gap between "disk read" and "mmap from page cache".  For
# small files (< 40 MB like our logs) that fit entirely in RAM, the OS page
# cache will likely hold the entire file after the first sequential pass,
# making subsequent mmap reads purely RAM-speed.  This is why the mmap
# speedup over regular parallel on M5 Pro may be close to 1.0×: both are
# already reading from the page cache, so the access mechanism difference
# is nearly invisible.
#
# THE GIL AND mmap:
# ──────────────────
# Even though mmap data lives in RAM (not disk), accessing it still involves
# memory load operations that the OS can service without holding the Python
# GIL.  Specifically:
#   - mm[start:end] (slice notation) calls mmap's C-level __getitem__,
#     which copies bytes under the C API — the GIL is released during
#     the copy, allowing other threads to proceed concurrently.
#   - The subsequent .decode() and regex match also release the GIL
#     during C-extension work.
# Therefore, multiple threads CAN overlap their mmap reads in real time,
# even in CPython.
#
# MAP-REDUCE ANALOGY FOR THE mmap PIPELINE:
# ──────────────────────────────────────────
#   SPLIT   : chunker.get_chunks()         → same byte-range chunks as before
#   LOAD    : mmap.mmap(f.fileno(), ...)   → map entire file into shared RAM
#             Think of this as "loading the dataset into a shared workspace"
#             that all MAP workers can read simultaneously — like a shared
#             hash table in a distributed system's in-memory store.
#   MAP     : _process_chunk_mmap(mm, ...) → each thread counts its slice
#             directly from RAM, zero extra copies of the raw bytes needed
#             at the OS level (one copy still happens for decode, see below)
#   REDUCE  : merge loop in analyze_parallel_mmap() → same O(T) summation
# =============================================================================


def _process_chunk_mmap(
    filepath: str,
    start_byte: int,
    end_byte: int,
) -> Dict[str, int]:
    """
    MAP step (mmap variant): count log levels in one byte-range chunk by
    reading directly from a pre-mapped memory region.

    THREAD SAFETY — WHY THIS IS SAFE WITH A SHARED mmap OBJECT:
    ─────────────────────────────────────────────────────────────
    The mmap object `mm` is shared across all threads.  A naive approach
    would be to call mm.seek(start_byte) then mm.readline() in a loop.
    BUT seek() mutates the shared cursor position — if Thread A calls
    seek(0) and Thread B calls seek(500000) before either reads, BOTH
    threads will read from position 500000.  That is a classic race condition.

    The correct thread-safe approach is SLICE NOTATION:

        chunk_bytes = mm[start_byte:end_byte]

    Slice indexing on an mmap object does NOT touch the shared cursor.
    It goes directly to the underlying virtual memory pages and copies the
    requested byte range into a new bytes object on the calling thread's
    heap.  This operation is:
      1. Thread-safe  — no shared mutable state is read or written
      2. Atomic from the thread's perspective — the OS handles the page
         faults and byte copy inside a C-level call before returning
      3. Fast  — backed by RAM once the page cache is warm

    LOCAL dict = NO RACE CONDITION on the count variables:
    ───────────────────────────────────────────────────────
    Each thread creates its OWN `counts` dict on its own call stack.
    No other thread has a reference to it.  Writing counts[level] += 1
    is safe without any lock because it is 100% private to this thread.
    Only after the function RETURNS does the ThreadPoolExecutor place the
    result into its internal (thread-safe) result queue.

    Parameters
    ──────────
    mm         : Shared mmap.mmap object opened with ACCESS_READ.
    start_byte : First byte of this thread's chunk (inclusive).
    end_byte   : One past the last byte of this thread's chunk (exclusive).

    Returns
    ───────
    Dict {level: count} — the partial log level counts for this chunk.

    Time complexity:  O(N/T) — processes N/T bytes/lines in this chunk.
    Space complexity: O(1) per thread — the 5-entry counts dict, plus one
                      temporary bytes object of size N/T for the decoded
                      chunk.  That bytes object is immediately eligible for
                      garbage collection once the loop ends, so peak
                      additional memory per thread is O(N/T) — acceptable
                      because it is only a fraction of the file, not a copy
                      of the whole file.  (Compare to analyze_parallel where
                      each thread also holds N/T bytes in memory; the total
                      footprint is similar.)
    """
    # Process-private count accumulator.  No lock needed — fully local.
    counts: Dict[str, int] = {level: 0 for level in LOG_LEVELS}

    # mmap.mmap objects cannot be pickled across a process boundary (each
    # process has its own virtual address space), so each worker process
    # opens its OWN mapping of the same file.  The underlying OS page cache
    # is still shared across processes — once one worker has paged in a
    # region, the others read it straight from RAM, not disk.
    import mmap
    with open(filepath, "rb") as f, mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ) as mm:
        chunk_bytes: bytes = mm[start_byte:end_byte]

    # Decode bytes to str.  errors='ignore' silently skips non-UTF-8 bytes —
    # same policy as _process_chunk() for consistency.
    chunk_text: str = chunk_bytes.decode("utf-8", errors="ignore")

    # Scan line by line.  splitlines() handles all common line endings.
    for line in chunk_text.splitlines():
        match = LOG_LEVEL_PATTERN.search(line)
        if match:
            level = match.group(1)
            counts[level] += 1

    return counts


def analyze_parallel_mmap(
    filepath: str,
    chunks: List[Tuple[int, int]],
    executor: "ProcessPoolExecutor | None" = None,
) -> Tuple[Dict[str, int], float]:
    """
    Orchestrate the mmap-backed parallel analysis.

    KEY DESIGN DECISION — MAP ONCE, SHARE ACROSS ALL THREADS:
    ──────────────────────────────────────────────────────────
    Creating an mmap mapping is not free.  It requires:
      1. An mmap() system call that registers the virtual address range.
      2. The OS sets up page-table entries for the entire file.
      3. Initial page faults as threads access each 4 KB page for the first
         time (these are handled by the kernel, not Python).

    If we created one mmap per thread (T mappings), we would pay this setup
    cost T times and consume T × (file size) of virtual address space, even
    though virtual memory is cheap, the setup syscalls are not free.

    By mapping ONCE in the main thread and passing the same mm object to all
    T worker threads, we pay the setup cost exactly once.  All threads then
    read from the same shared virtual address range — sharing is free because
    mmap is backed by the OS page cache, which is already shared across all
    processes and threads reading the same file.

    SPACE COMPLEXITY — THE KEY TRADEOFF vs. REGULAR PARALLEL:
    ──────────────────────────────────────────────────────────
    Regular analyze_parallel():   O(1) virtual memory overhead
      Each thread opens its own fd and reads N/T bytes at a time.
      Only N/T bytes are in RAM per thread at peak (the read buffer).

    analyze_parallel_mmap():      O(N) virtual address space
      The ENTIRE file is mapped into virtual memory at once.
      Virtual memory ≠ physical RAM — the OS brings in only the pages
      actually accessed (demand paging), so physical RAM usage is still
      roughly N bytes total (same as the page cache would hold anyway).
      But the virtual address space commitment is O(N).

    WHEN IS THE mmap TRADEOFF WORTH IT?
      ✓ Worth it:  File fits in RAM (< physical memory).  Need maximum
                   read throughput.  File will be read more than once
                   (warm cache = pure RAM speed on subsequent passes).
      ✗ Not worth it: File is larger than available RAM — OS must page
                   out other data, causing thrashing.  Cold-cache first
                   read does not benefit because page faults still go
                   to disk.  In that case, regular parallel I/O with
                   explicit read() calls is actually safer and more
                   predictable.

    Parameters
    ──────────
    filepath : Path to the log file.
    chunks   : List of (start_byte, end_byte) tuples — identical format to
               what chunker.get_chunks() produces.  No changes to the
               chunker are needed; mmap and regular parallel use the same
               split strategy.

    Returns
    ───────
    (counts, elapsed_seconds) — identical signature to analyze_parallel().
    This makes the two functions drop-in replaceable in app.py and the
    test script.

    Time complexity:  O(N/T) for the parallel MAP phase (same as before).
                      O(T) for the REDUCE merge (same as before).
                      O(1) additional for mmap setup (one syscall).
                      Overall: O(N/T) — same asymptotic complexity as
                      analyze_parallel, but with a smaller constant factor
                      once the page cache is warm.

    Space complexity: O(N) virtual address space (mmap covers whole file).
                      O(1) physical RAM overhead per thread beyond the
                      page cache (which would hold the data anyway).
    """
    num_threads = len(chunks)

    # ── Start the timer ──────────────────────────────────────────────────────
    start_time = time.perf_counter()

    # EDGE CASE: mmap.mmap() raises "ValueError: cannot mmap an empty file"
    # on a 0-byte file — there is no page to map.  chunker.get_chunks() already
    # returns [(0, 0)] * num_threads for empty files, so we can short-circuit
    # here instead of touching mmap at all.
    if os.path.getsize(filepath) == 0:
        elapsed = time.perf_counter() - start_time
        return {level: 0 for level in LOG_LEVELS}, elapsed

    # ── MAP PHASE ────────────────────────────────────────────────────────────
    # Submit one _process_chunk_mmap task per chunk.  Each worker process opens
    # its own mmap of `filepath` (mmap objects cannot be pickled across a
    # process boundary), then reads its byte range from it.
    # No locks are needed because:
    #   1. All workers only READ their mapping (ACCESS_READ mode).
    #   2. They use slice notation (no shared cursor contention).
    #   3. They write only to their own LOCAL counts dicts.
    # If the caller passed a pre-built `executor` (app.py's persistent pool),
    # reuse it instead of spawning a fresh ProcessPoolExecutor per call.
    futures: List[Future] = []
    if executor is not None:
        for start_byte, end_byte in chunks:
            futures.append(executor.submit(_process_chunk_mmap, filepath, start_byte, end_byte))
        for future in futures:
            future.result()  # propagate any worker exception now
    else:
        with ProcessPoolExecutor(max_workers=num_threads) as local_executor:
            for start_byte, end_byte in chunks:
                future = local_executor.submit(
                    _process_chunk_mmap, filepath, start_byte, end_byte
                )
                futures.append(future)
            # Context manager exit: blocks until ALL workers complete.

    # ── REDUCE PHASE ─────────────────────────────────────────────────────────
    # Identical merge pattern to analyze_parallel().
    # This is the REDUCE step of Map-Reduce: sum T partial dicts of size 5.
    # O(T * 5) = O(T) — negligible.
    merged: Dict[str, int] = {level: 0 for level in LOG_LEVELS}
    for future in futures:
        partial_counts = future.result()
        for level in LOG_LEVELS:
            merged[level] += partial_counts[level]

    # ── Stop the timer ───────────────────────────────────────────────────────
    elapsed = time.perf_counter() - start_time

    return merged, elapsed
