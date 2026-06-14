# =============================================================================
# analyzer/metrics.py
# =============================================================================
# PURPOSE:
#   Pure calculation module — no file I/O, no threading, no Flask.
#   Takes two timing measurements and a thread count, and returns all
#   performance metrics relevant to the parallel algorithms analysis.
#
# WHY ISOLATE THIS?
#   Keeping calculations in a separate module with no side effects makes them:
#     1. Unit-testable without touching the filesystem or starting threads.
#     2. Easy to modify (change rounding, add new metrics) without touching
#        any other part of the system.
#     3. Clearly separated from I/O concerns (Single Responsibility Principle).
#
# =============================================================================
#
# AMDAHL'S LAW — THE THEORETICAL FRAMEWORK:
# ──────────────────────────────────────────
# Amdahl's Law (1967) predicts the maximum speedup of a program when only
# part of it can be parallelised:
#
#     Speedup(T) = 1 / (S + (1 - S) / T)
#
# where:
#   S = the SERIAL FRACTION of the program (0 ≤ S ≤ 1)
#       The part that cannot be parallelised: startup, file open, result merge.
#   T = number of threads (processors)
#   (1 - S) = the PARALLEL FRACTION
#
# Key insights from Amdahl's Law:
#
#   1. As T → ∞, Speedup → 1/S.
#      Even with infinite threads, the serial fraction S is the hard ceiling.
#      Example: if S = 0.05 (5% serial), max speedup = 1/0.05 = 20×.
#
#   2. DIMINISHING RETURNS: each doubling of T yields less additional speedup.
#      Going from T=1 to T=2 gives the biggest jump.
#      Going from T=8 to T=16 gives a much smaller jump.
#
#   3. For large T, the overhead of creating threads and merging results
#      can EXCEED the parallel savings — this is why we sometimes see
#      efficiency_pct < 100% even for modest thread counts.
#
# In our /benchmark endpoint, we use S = 0.05 as a reasonable estimate
# for a primarily I/O-bound workload.  The actual measured speedup lets
# students compare empirical vs. theoretical and discuss discrepancies.
#
# EFFICIENCY — WHAT "GOOD" PARALLELISM LOOKS LIKE:
# ──────────────────────────────────────────────────
# Efficiency measures how well we are utilising each thread:
#
#     Efficiency = Speedup / T  (expressed as %)
#
# Interpretation:
#   100%  → PERFECT linear scaling — every thread contributes fully.
#             Almost never achieved in the real world.
#   50%   → We got T× threads but only 0.5T× speedup — half the capacity
#             is wasted on overhead (thread creation, GIL contention, I/O
#             queue saturation, cache thrashing, etc.).
#   < 50% → Parallel overhead is significant; worth questioning if more
#             threads are worthwhile.
#
# Efficiency ALWAYS decreases as T increases (for fixed N), which is why
# there is an optimal T beyond which adding threads hurts or offers no benefit.
# =============================================================================

from typing import Dict


def compute_metrics(
    seq_time: float,
    par_time: float,
    num_threads: int,
) -> Dict[str, float]:
    """
    Compute performance comparison metrics between sequential and parallel runs.

    Parameters
    ──────────
    seq_time    : Sequential elapsed time in SECONDS (from time.perf_counter()).
    par_time    : Parallel elapsed time in SECONDS (from time.perf_counter()).
    num_threads : Number of threads used in the parallel run.

    Returns
    ───────
    A dict with the following keys:

      sequential_time_ms  : seq_time converted to milliseconds, 2 d.p.
      parallel_time_ms    : par_time converted to milliseconds, 2 d.p.
      speedup             : Ratio seq_time / par_time, 3 d.p.
                            > 1.0 → parallel is faster
                            = 1.0 → same speed
                            < 1.0 → parallel is SLOWER (overhead dominated)
      efficiency_pct      : speedup / num_threads * 100, 1 d.p.
                            100% = perfect; real world is always below 100%.
      num_threads         : Passed through unchanged (convenient for JSON).

    No file I/O.  No side effects.  Purely deterministic arithmetic.
    Time complexity: O(1).  Space complexity: O(1).
    """
    # Convert seconds → milliseconds for a friendlier human-readable number.
    # Multiplying by 1000 is exact (no floating-point representation issue
    # beyond what was already present in the perf_counter reading).
    seq_ms = round(seq_time * 1000, 2)
    par_ms = round(par_time * 1000, 2)

    # ── Speedup ──────────────────────────────────────────────────────────────
    # Speedup = (time with 1 thread) / (time with T threads)
    # A value > 1 means the parallel version is faster.
    # We guard against division-by-zero: if par_time is somehow 0 (extremely
    # fast machine or tiny file), cap speedup at num_threads (perfect scaling).
    if par_time > 0:
        speedup = round(seq_time / par_time, 3)
    else:
        speedup = float(num_threads)

    # ── Efficiency ───────────────────────────────────────────────────────────
    # Efficiency tells us what fraction of each thread's capacity is being used.
    # If speedup = T, efficiency = 100% (ideal but unrealistic).
    # If speedup = T/2, efficiency = 50% (half the threads are "wasted").
    efficiency_pct = round((speedup / num_threads) * 100, 1)

    return {
        "sequential_time_ms": seq_ms,
        "parallel_time_ms":   par_ms,
        "speedup":            speedup,
        "efficiency_pct":     efficiency_pct,
        "num_threads":        num_threads,
    }


def amdahl_speedup(num_threads: int, serial_fraction: float = 0.05) -> float:
    """
    Compute the THEORETICAL speedup predicted by Amdahl's Law for a given
    number of threads and serial fraction.

    Formula:
        Speedup(T) = 1 / (S + (1 - S) / T)

    Parameters
    ──────────
    num_threads     : T in the formula.
    serial_fraction : S in the formula.  Defaults to 0.05 (5% serial work),
                      a reasonable estimate for our I/O-bound log analyzer.

    Returns
    ───────
    Theoretical speedup, rounded to 3 decimal places.

    This function is used by the /benchmark endpoint to compute a theoretical
    curve for comparison against the empirically measured speedup.  Plotting
    both on the same graph is one of the strongest visualisations in the report.
    """
    s = serial_fraction
    t = num_threads
    theoretical = 1.0 / (s + (1.0 - s) / t)
    return round(theoretical, 3)
