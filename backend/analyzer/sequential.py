# =============================================================================
# analyzer/sequential.py
# =============================================================================
# PURPOSE:
#   Provide the sequential (single-threaded) baseline analysis of a log file.
#
# ROLE IN THE EXPERIMENT:
#   In any performance experiment, you need a CONTROL — a measurement taken
#   without the intervention (parallelism) so you can isolate the effect.
#   This module is that control.  Every speedup and efficiency number in
#   analyzer/metrics.py is computed relative to the time measured here.
#
#   Without a correct sequential baseline:
#     - Speedup = parallel_time / ??? → meaningless
#     - We cannot verify that parallel counts == sequential counts
#       (correctness check before performance claim)
#
# ALGORITHM ANALYSIS:
#   Time complexity:  O(N) — we scan every line exactly once.
#   Space complexity: O(1) — we store only 5 integers (one per log level)
#                            regardless of how large the file is.  We never
#                            load the entire file into memory.
#   Core utilization: 1 core.  The GIL is held throughout; no parallelism.
# =============================================================================

import re
import time
from typing import Dict, Tuple

# =============================================================================
# WHY re.compile() AT MODULE LEVEL?
# ─────────────────────────────────
# A regular expression must be compiled from its string form into an internal
# finite automaton (NFA/DFA) representation before it can be used for matching.
#
# If we wrote:    re.search(r"\[(INFO|WARNING|...)\]", line)   inside the loop,
# Python would RE-COMPILE the pattern on EVERY iteration — O(N) compilations,
# each taking roughly the same time as the match itself.  This effectively
# doubles the per-line cost for no benefit.
#
# By compiling once at module load time (import), the pattern is compiled
# exactly ONCE and reused for all N lines.  Python's re module caches compiled
# patterns, but relying on that cache is implicit; compiling explicitly is the
# idiomatic, readable, and guaranteed way to avoid repeated compilation.
#
# The pattern explained:
#   \[           → literal opening bracket (must escape — '[' has special meaning)
#   (INFO|       → capture group: match one of the five log levels
#    WARNING|
#    ERROR|
#    DEBUG|
#    CRITICAL)
#   [^\]]*       → zero or more chars that are NOT ']' (handles padding spaces)
#   \]           → literal closing bracket
#
# We use a non-capturing group implicitly by checking match.group(1) — only
# the level name is captured, not the brackets or padding.
# =============================================================================
LOG_LEVEL_PATTERN = re.compile(r"\[(INFO|WARNING|ERROR|DEBUG|CRITICAL)[^\]]*\]")

# The five levels we count.  Using a tuple (not a set) preserves insertion
# order so the output dict always has a consistent key order.
LOG_LEVELS = ("INFO", "WARNING", "ERROR", "DEBUG", "CRITICAL")


def analyze_sequential(filepath: str) -> Tuple[Dict[str, int], float]:
    """
    Read `filepath` line by line and count occurrences of each log level.

    This is a single-pass O(N) scan with O(1) auxiliary space.

    Parameters
    ──────────
    filepath : Path to the log file.

    Returns
    ───────
    (counts, elapsed_seconds)
      counts          : dict mapping each log level to its line count.
      elapsed_seconds : wall-clock time in seconds for the entire scan,
                        measured with time.perf_counter() (see below).

    Why time.perf_counter() instead of time.time()?
    ─────────────────────────────────────────────────
    time.time() returns the system clock in seconds since the Unix epoch.
    On most platforms its resolution is ~1 ms — barely adequate for measuring
    operations that take tens of milliseconds.  Worse, the system clock can
    jump forward or backward due to NTP synchronisation, making consecutive
    calls non-monotonic.

    time.perf_counter() is a high-resolution MONOTONIC timer with nanosecond
    resolution on modern hardware.  It is guaranteed never to go backwards.
    For short-duration benchmarks (< 60 seconds), it is the correct choice.
    It is intentionally NOT suitable for wall-clock timestamps (it has no
    defined epoch), but we only use it for elapsed-time differences, so that
    is fine.

    Implementation detail — reading line by line vs. read() + split():
    ──────────────────────────────────────────────────────────────────
    We iterate over the file object directly (for line in f:).  Python's file
    iterator uses an internal C-level read buffer and yields one decoded line
    at a time.  This is:
      - O(1) space per iteration (one line in memory at a time)
      - Faster than f.readlines() which allocates a list of ALL lines — O(N)
      - Faster than f.read().split('\n') which builds one giant string — O(N)

    The O(1) space guarantee holds even for the 500,000-line large.log file.
    """
    # Initialise counters.  A dict with integer values is ideal here:
    # lookup and update are both O(1) average (hash table).
    counts: Dict[str, int] = {level: 0 for level in LOG_LEVELS}

    # ── Start the high-resolution timer ─────────────────────────────────────
    # We start AFTER initialising counts so we time only the I/O and regex
    # work, not Python dict construction overhead.
    start_time = time.perf_counter()

    with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            # LOG_LEVEL_PATTERN.search() scans the line for the first match.
            # Because every well-formed log line has exactly one level tag,
            # search() is sufficient and slightly faster than fullmatch().
            match = LOG_LEVEL_PATTERN.search(line)
            if match:
                # group(1) returns the captured level name (e.g., "ERROR").
                level = match.group(1)
                counts[level] += 1
                # Lines that don't match (e.g., malformed) are silently skipped.
                # This is intentional: a robust log analyzer must not crash on
                # unexpected input — it should simply ignore lines it cannot parse.

    # ── Stop the timer ───────────────────────────────────────────────────────
    elapsed = time.perf_counter() - start_time

    return counts, elapsed
