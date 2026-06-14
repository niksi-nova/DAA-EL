# =============================================================================
# analyzer/__init__.py
# =============================================================================
# PURPOSE:
#   Makes the `analyzer` directory a Python package and exposes its four
#   sub-modules through a clean public interface.
#
# USAGE (from app.py or test_engine.py):
#   from analyzer import chunker, sequential, parallel, metrics
#
#   Then call:
#   chunker.get_chunks(filepath, num_threads)
#   sequential.analyze_sequential(filepath)
#   parallel.analyze_parallel(filepath, chunks)
#   metrics.compute_metrics(seq_time, par_time, num_threads)
#   metrics.amdahl_speedup(num_threads)
#
# WHY EXPLICIT IMPORTS HERE?
#   Without these lines, `from analyzer import chunker` would still work
#   because Python will search the package directory for a `chunker.py`.
#   However, listing them here makes the package's public API explicit and
#   self-documenting — a reader of __init__.py immediately knows what the
#   package provides without scanning the directory.
# =============================================================================

from analyzer import chunker    # File splitting — SPLIT step
from analyzer import sequential # Single-threaded baseline
from analyzer import parallel   # Multi-threaded engine — MAP + REDUCE steps
from analyzer import metrics    # Amdahl's Law, speedup, efficiency calculations
