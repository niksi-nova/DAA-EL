# =============================================================================
# test_engine.py
# =============================================================================
# PURPOSE:
#   A standalone correctness and performance verification script.
#   Run this BEFORE starting the Flask server to confirm the core engine works.
#
# WHY VERIFY CORRECTNESS BEFORE MEASURING PERFORMANCE?
# ──────────────────────────────────────────────────────
# The most dangerous mistake in parallel programming is to assume that
# "it gave an answer, so it must be right."  Parallel bugs — race conditions,
# off-by-one errors in chunk boundaries, lines split between threads — often
# produce subtly WRONG results rather than crashes.
#
# A parallel analyzer that counts 99,850 lines instead of 100,000 is broken,
# even if it reports a 3.5× speedup.  A fast wrong answer is WORSE than a
# slow correct one: it erodes trust in the entire system.
#
# Therefore, our testing protocol is:
#   Step 1 — Assert sequential == parallel (correctness gate)
#   Step 2 — Report performance metrics (only meaningful if Step 1 passes)
#
# This mirrors the standard scientific method: validate your instrument before
# reporting measurements.
#
# USAGE:
#   cd backend/
#   python test_engine.py
#
# PRECONDITION:
#   uploads/medium.log must exist.  Run log_generator.py first if it doesn't.
# =============================================================================

import os
import sys

# ---------------------------------------------------------------------------
# Path setup — ensure the backend/ directory is on the Python module path so
# `from analyzer import ...` works when the script is run from any directory.
# ---------------------------------------------------------------------------
BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from analyzer import chunker, sequential, parallel, metrics
from analyzer.parallel import analyze_parallel_mmap

# ---------------------------------------------------------------------------
# Test configuration
# ---------------------------------------------------------------------------
TEST_FILE     = os.path.join(BACKEND_DIR, "uploads", "medium.log")
NUM_THREADS   = 4   # Enough to demonstrate parallelism; fast on any machine.
LOG_LEVELS    = ("INFO", "WARNING", "ERROR", "DEBUG", "CRITICAL")

# ANSI colour codes for pass/fail output.
GREEN  = "\033[92m"
RED    = "\033[91m"
YELLOW = "\033[93m"
BOLD   = "\033[1m"
RESET  = "\033[0m"


def print_header(title: str) -> None:
    width = 60
    print("\n" + "=" * width)
    print(f"  {title}")
    print("=" * width)


def main() -> None:
    # ── Precondition check ───────────────────────────────────────────────────
    print_header("DAA Project - Engine Correctness & Performance Test")

    if not os.path.exists(TEST_FILE):
        print(f"{RED}ERROR: Test file not found:{RESET}")
        print(f"  {TEST_FILE}")
        print(f"\nRun this first:  python log_generator.py")
        sys.exit(1)

    file_size_mb = os.path.getsize(TEST_FILE) / (1024 * 1024)
    print(f"\nTest file : {os.path.basename(TEST_FILE)}")
    print(f"File size : {file_size_mb:.2f} MB")
    print(f"Threads   : {NUM_THREADS}")

    # ── Warm the OS page cache BEFORE any timed run ─────────────────────────
    # The sequential run always goes first. Without a warm-up read, it would
    # pay the cold-disk-read cost while parallel/mmap runs that follow benefit
    # from a cache the sequential run just warmed up for them — skewing the
    # speedup numbers. A throwaway read here puts all three methods on equal
    # footing.
    with open(TEST_FILE, "rb") as _f:
        while _f.read(1024 * 1024):
            pass

    # ── STEP 1: Run Sequential Analysis ─────────────────────────────────────
    print_header("Step 1 - Sequential Analysis (Baseline)")
    print("Running single-threaded scan...")

    seq_counts, seq_time = sequential.analyze_sequential(TEST_FILE)
    seq_total = sum(seq_counts.values())

    print(f"\n  Results:")
    for level in LOG_LEVELS:
        print(f"    {level:<10}: {seq_counts[level]:>8,}")
    print(f"  {'TOTAL':<10}: {seq_total:>8,}")
    print(f"\n  Time: {seq_time * 1000:.2f} ms")

    # ── STEP 2: Run Parallel Analysis ────────────────────────────────────────
    print_header(f"Step 2 - Parallel Analysis ({NUM_THREADS} threads)")
    print("Computing byte-range chunks...")

    chunks = chunker.get_chunks(TEST_FILE, NUM_THREADS)
    print(f"  Chunk boundaries (byte ranges):")
    for i, (start, end) in enumerate(chunks):
        print(f"    Thread {i}: bytes [{start:>10,} -> {end:>10,}]  "
              f"({(end - start) / 1024:.1f} KB)")

    print("\nRunning parallel analysis...")
    par_counts, par_time = parallel.analyze_parallel(TEST_FILE, chunks)
    par_total = sum(par_counts.values())

    print(f"\n  Results:")
    for level in LOG_LEVELS:
        print(f"    {level:<10}: {par_counts[level]:>8,}")
    print(f"  {'TOTAL':<10}: {par_total:>8,}")
    print(f"\n  Time: {par_time * 1000:.2f} ms")

    # ── STEP 3: Correctness Assertion ────────────────────────────────────────
    print_header("Step 3 - Correctness Verification")
    print("Asserting: sequential counts == parallel counts for every level...\n")

    all_passed = True
    for level in LOG_LEVELS:
        seq_val = seq_counts[level]
        par_val = par_counts[level]
        match = seq_val == par_val
        status = f"{GREEN}PASS{RESET}" if match else f"{RED}FAIL{RESET}"
        diff_str = "" if match else f"  <- DIFFERENCE: {abs(seq_val - par_val):,}"
        print(f"  [{status}] {level:<10}  seq={seq_val:>8,}  par={par_val:>8,}{diff_str}")
        if not match:
            all_passed = False

    # Total line count assertion.
    total_match = seq_total == par_total
    status = f"{GREEN}PASS{RESET}" if total_match else f"{RED}FAIL{RESET}"
    diff_str = "" if total_match else f"  <- DIFFERENCE: {abs(seq_total - par_total):,}"
    print(f"\n  [{status}] {'TOTAL':<10}  seq={seq_total:>8,}  par={par_total:>8,}{diff_str}")
    if not total_match:
        all_passed = False

    # ── STEP 4: Performance Metrics ──────────────────────────────────────────
    print_header("Step 4 - Performance Metrics")

    perf = metrics.compute_metrics(seq_time, par_time, NUM_THREADS)
    theoretical = metrics.amdahl_speedup(NUM_THREADS, serial_fraction=0.05)

    print(f"  Sequential time   : {perf['sequential_time_ms']:>8.2f} ms")
    print(f"  Parallel time     : {perf['parallel_time_ms']:>8.2f} ms")
    print(f"  " + "-" * 36)
    print(f"  Actual speedup    : {perf['speedup']:>8.3f}x")
    print(f"  Theoretical (S=5%): {theoretical:>8.3f}x  (Amdahl's Law)")
    print(f"  Efficiency        : {perf['efficiency_pct']:>7.1f}%  "
          f"(ideal = 100%)")
    print(f"  Threads used      : {perf['num_threads']}")

    # ── STEP 5: mmap Parallel Analysis ──────────────────────────────────────
    # WHY TEST CORRECTNESS BEFORE COMPARING PERFORMANCE (reprise for mmap):
    # ───────────────────────────────────────────────────────────────────────
    # We restate this principle here because mmap introduces a new read path
    # (virtual memory slicing instead of explicit read() calls).  A subtle bug
    # in the slice boundaries, the decode step, or the regex could produce
    # counts that look plausible but differ by a few lines from the ground
    # truth.  A fast wrong answer is WORSE than a slow correct one: it would
    # make mmap appear more accurate than it is, skewing the comparison.
    # Always gate performance claims behind a correctness assertion.
    print_header("Step 5 - mmap Parallel Analysis (third method)")
    print("Running memory-mapped parallel analysis (same chunks, shared mmap)...")

    mmap_counts, mmap_time = analyze_parallel_mmap(TEST_FILE, chunks)
    mmap_total = sum(mmap_counts.values())

    print(f"\n  Results:")
    for level in LOG_LEVELS:
        print(f"    {level:<10}: {mmap_counts[level]:>8,}")
    print(f"  {'TOTAL':<10}: {mmap_total:>8,}")
    print(f"\n  Time: {mmap_time * 1000:.2f} ms")

    # ── mmap correctness assertion ───────────────────────────────────────────
    print(f"\n  Asserting: mmap counts == sequential counts for every level...\n")

    mmap_all_passed = True
    for level in LOG_LEVELS:
        seq_val  = seq_counts[level]
        mmap_val = mmap_counts[level]
        match    = seq_val == mmap_val
        status   = f"{GREEN}PASS{RESET}" if match else f"{RED}FAIL{RESET}"
        diff_str = "" if match else f"  <- DIFFERENCE: {abs(seq_val - mmap_val):,}"
        print(f"  [{status}] {level:<10}  seq={seq_val:>8,}  mmap={mmap_val:>8,}{diff_str}")
        if not match:
            mmap_all_passed = False

    mmap_total_match = (seq_total == mmap_total)
    status   = f"{GREEN}PASS{RESET}" if mmap_total_match else f"{RED}FAIL{RESET}"
    diff_str = "" if mmap_total_match else f"  <- DIFFERENCE: {abs(seq_total - mmap_total):,}"
    print(f"\n  [{status}] {'TOTAL':<10}  seq={seq_total:>8,}  mmap={mmap_total:>8,}{diff_str}")
    if not mmap_total_match:
        mmap_all_passed = False

    # Propagate mmap failures into the global pass/fail flag so the Final
    # Result section reflects all three methods together.
    if not mmap_all_passed:
        all_passed = False

    # ── mmap performance comparison ──────────────────────────────────────────
    print_header("Step 5b - mmap Performance Comparison")

    mmap_ms            = round(mmap_time  * 1000, 3)
    speedup_vs_seq     = round(seq_time   / mmap_time, 3)
    speedup_vs_par     = round(par_time   / mmap_time, 3)

    print(f"  mmap parallel time      : {mmap_ms:>8.2f} ms")
    print(f"  " + "-" * 42)
    print(f"  Speedup over sequential : {speedup_vs_seq:>8.3f}x")
    print(f"  Speedup over parallel   : {speedup_vs_par:>8.3f}x")
    print()

    # INTERPRETING THE mmap vs. PARALLEL SPEEDUP NUMBER:
    # ────────────────────────────────────────────────────
    # speedup_vs_par = par_time / mmap_time
    #
    #   > 1.0× → mmap is faster than regular parallel.
    #             The bottleneck has shifted from disk I/O (where parallel
    #             threads waiting on the OS scheduler gains time) to RAM
    #             throughput.  mmap wins because it skips the kernel-to-user
    #             copy overhead and serves data straight from the page cache.
    #
    #   ≈ 1.0× → Both methods are already bottlenecked at the same resource.
    #             On an M5 Pro with a 7 GB/s NVMe SSD, even "regular" reads
    #             are served mostly from the OS page cache (warm from the
    #             sequential pass), so the read path is already RAM-speed.
    #             The remaining difference is thread overhead and regex time,
    #             which is the same for both.  Expected range on M5 Pro for
    #             a ~8 MB file: 0.9× – 2.0×.
    #
    #   < 1.0× → mmap is SLOWER (rare, but possible on the first cold run
    #             if mmap setup + page-fault overhead exceeds the disk I/O
    #             savings, or if the file is very small so overhead dominates).
    if speedup_vs_par > 1.05:
        verdict = f"{GREEN}mmap is faster than regular parallel{RESET}"
    elif speedup_vs_par >= 0.95:
        verdict = f"{YELLOW}mmap and parallel are approximately equal{RESET}"
    else:
        verdict = f"{YELLOW}mmap is slightly slower (overhead-dominated at this file size){RESET}"

    print(f"  Interpretation: {verdict}")
    print(f"\n  (On Apple M5 Pro: expect {YELLOW}0.9x - 2.5x{RESET} due to warm SSD page cache)")

    # ── Final verdict ────────────────────────────────────────────────────────
    print_header("Final Result")
    if all_passed:
        print(f"  {GREEN}{BOLD}ALL CORRECTNESS CHECKS PASSED{RESET}")
        print(f"\n  The parallel engine produces identical counts to the")
        print(f"  sequential baseline.  The implementation is correct.")
        print(f"\n  You can now start the Flask API:  python app.py")
    else:
        print(f"  {RED}{BOLD}CORRECTNESS CHECKS FAILED{RESET}")
        print(f"\n  The parallel counts differ from the sequential baseline.")
        print(f"  This indicates a bug in the chunker or parallel analyzer.")
        print(f"  DO NOT report performance numbers until correctness is fixed.")
        sys.exit(1)

    print()


if __name__ == "__main__":
    main()
