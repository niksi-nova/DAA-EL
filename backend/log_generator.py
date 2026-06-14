# =============================================================================
# log_generator.py
# =============================================================================
# PURPOSE:
#   A standalone utility script — NOT part of the Flask app — that generates
#   synthetic log files for testing and benchmarking the analyzer engine.
#
# WHY DIFFERENT FILE SIZES?
#   A core goal of this project is to demonstrate how parallel speedup changes
#   with input size N.  Amdahl's Law tells us:
#
#       Speedup(T) = 1 / (S + (1 - S) / T)
#
#   where S is the serial fraction and T is the number of threads.
#   Parallelism comes with constant overhead (thread creation, result merging).
#   That overhead only "pays off" when the parallel workload is large enough to
#   amortize it.  Therefore:
#
#     small.log  (  10,000 lines) → overhead may dominate; speedup can be <1×
#     medium.log ( 100,000 lines) → transition zone; clear benefit at 4+ threads
#     large.log  ( 500,000 lines) → compute-dominated; near-linear scaling
#
#   Running our analyzer on all three sizes lets us empirically plot speedup
#   vs. N and observe the crossover point — the strongest empirical evidence
#   in the final report.
#
# USAGE (run once before the Flask app or test script):
#   python log_generator.py
# =============================================================================

import os
import random
from datetime import datetime, timedelta

# ---------------------------------------------------------------------------
# Output directory — same folder the Flask API uses for uploaded files.
# os.path.dirname(__file__) resolves correctly no matter where the script is
# invoked from (unlike a bare relative path like "uploads/").
# ---------------------------------------------------------------------------
OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "uploads")

# ---------------------------------------------------------------------------
# Log-level weighted distribution
# ---------------------------------------------------------------------------
# We build an explicit weighted list so the distribution is self-documenting
# (the weight of each level is visible as its count in the list).
#
# INFO      50 entries → 50% of lines  (heartbeat of a healthy system)
# WARNING   20 entries → 20%           (degraded but still functioning)
# ERROR     15 entries → 15%           (failures that need attention)
# DEBUG     10 entries → 10%           (verbose diagnostics, usually filtered)
# CRITICAL   5 entries →  5%           (rare; system is in serious trouble)
#
# random.choice() on this list is O(1) — it picks a uniform random index.
# The non-uniform probability comes from the repetition of each level string.
# ---------------------------------------------------------------------------
LEVEL_WEIGHTS = (
    ["INFO"]     * 50
    + ["WARNING"]  * 20
    + ["ERROR"]    * 15
    + ["DEBUG"]    * 10
    + ["CRITICAL"] *  5
)  # Total: 100 elements — easy to reason about percentages.

# ---------------------------------------------------------------------------
# Realistic message templates per level.
# At least 5 per level prevents repeating patterns that could skew analysis.
# The {} placeholders are filled with random integers at generation time so
# every line looks unique.
# ---------------------------------------------------------------------------
MESSAGES: dict[str, list[str]] = {
    "INFO": [
        "User login successful for user_id={}",
        "Request processed in {}ms — endpoint /api/v1/data",
        "Database connection pool size: {}/20",
        "Cache hit ratio at {}% for the last 60 seconds",
        "Scheduled job 'cleanup_temp_files' completed in {}s",
        "New session created — session_id={}",
        "Config reloaded from disk — version={}",
    ],
    "WARNING": [
        "Response time exceeded threshold: {}ms (limit: 500ms)",
        "Disk usage at {}% on volume /dev/sda1 — consider cleanup",
        "Deprecated API endpoint /v1/legacy called by client {}",
        "Retry attempt {} of 3 for downstream service call",
        "Memory usage at {}MB — approaching soft limit of 512MB",
        "Rate limit at {}% for IP 192.168.{}.{}",
    ],
    "ERROR": [
        "Failed to connect to database after {} retries — giving up",
        "NullPointerException in module payments.processor at line {}",
        "HTTP 500 returned for request_id={} — internal server error",
        "File not found: /var/data/report_{}.csv",
        "Authentication token expired for user_id={}",
        "Unhandled exception in worker thread-{}: IndexError",
    ],
    "DEBUG": [
        "Entering function process_batch() with batch_size={}",
        "SQL query executed: SELECT * FROM orders WHERE id={} ({}ms)",
        "Cache miss for key='user_profile_{}' — fetching from DB",
        "Serializing response object — {} fields found",
        "Lock acquired on resource 'invoice_{}' by thread-{}",
        "Checkpoint reached at loop iteration {}",
    ],
    "CRITICAL": [
        "SYSTEM SHUTDOWN INITIATED — out of memory (used: {}MB / 512MB)",
        "Data corruption detected in table 'transactions' at row {}",
        "SSL certificate expires in {} hours — immediate action required",
        "Primary database unreachable — all writes failing, queue depth: {}",
        "Security breach detected: {} failed login attempts from IP 10.0.{}.{}",
    ],
}


def _random_message(level: str) -> str:
    """
    Select a random message template for `level` and fill all {} placeholders
    with random integers in [1, 9999].

    Time complexity: O(1) — template list is fixed size; placeholder count
    is bounded by the longest template (≤ 3 placeholders).
    """
    template = random.choice(MESSAGES[level])
    placeholder_count = template.count("{}")
    values = [random.randint(1, 9999) for _ in range(placeholder_count)]
    return template.format(*values)


def generate_log_file(filepath: str, num_lines: int) -> None:
    """
    Write `num_lines` synthetic log entries to `filepath`.

    Key algorithmic decisions:
    ─────────────────────────
    1. STREAMING WRITE — O(1) space:
       We write each line directly to disk rather than accumulating all lines
       in a list first.  For 500,000 lines, an in-memory list would consume
       hundreds of MB — O(N) space.  Streaming keeps RAM usage O(1) regardless
       of N.  The OS page cache handles the write buffering transparently.

    2. INCREMENTAL TIMESTAMP — O(1) per line:
       Each timestamp is computed by adding a random timedelta to the previous
       value.  This is O(1) arithmetic.  An alternative (computing all
       timestamps first with list comprehension) would again be O(N) space.

    3. LEVEL SAMPLING — O(1) per line:
       random.choice(LEVEL_WEIGHTS) is O(1) — it picks a uniform random index
       into a pre-built list.  The weighting is encoded in list length.

    Overall time complexity: O(N)
    Overall space complexity: O(1)
    """
    # Start 30 days in the past so the log file looks like real history.
    current_time = datetime(2025, 1, 1, 0, 0, 0)

    print(f"  Generating {num_lines:,} lines → {os.path.basename(filepath)}")

    with open(filepath, "w", encoding="utf-8") as f:
        for i in range(num_lines):
            # Advance the clock by 1–10 seconds to simulate realistic log cadence
            # (bursts of activity followed by quiet periods).
            current_time += timedelta(seconds=random.randint(1, 10))

            level   = random.choice(LEVEL_WEIGHTS)
            message = _random_message(level)

            # Format: YYYY-MM-DD HH:MM:SS [LEVEL   ] Message
            # Left-padding the level to 8 chars aligns the message column,
            # making the raw file easier to read when debugging.
            timestamp = current_time.strftime("%Y-%m-%d %H:%M:%S")
            line = f"{timestamp} [{level:<8}] {message}\n"
            f.write(line)

            # Progress heartbeat every 100,000 lines so the user knows the
            # script is alive during large-file generation.
            if (i + 1) % 100_000 == 0:
                print(f"    ... {i + 1:,} lines written")

    size_mb = os.path.getsize(filepath) / (1024 * 1024)
    print(f"  Done — {size_mb:.2f} MB\n")


def main() -> None:
    """
    Generate three log files at increasing sizes.

    The size progression is intentional:
      small  →  overhead-dominated regime  (useful to show where parallel HURTS)
      medium →  transition zone             (parallel begins to clearly win)
      large  →  compute-dominated regime   (parallel scales well toward Amdahl limit)

    This gives three data points for the speedup-vs-N plot in the report.
    """
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    files = [
        ("small.log",  10_000),
        ("medium.log", 100_000),
        ("large.log",  500_000),
    ]

    print("=" * 60)
    print("  Log Generator — DAA Algorithms Project")
    print("=" * 60 + "\n")

    for filename, num_lines in files:
        filepath = os.path.join(OUTPUT_DIR, filename)
        generate_log_file(filepath, num_lines)

    print("All files generated successfully.")
    print(f"Output directory: {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
