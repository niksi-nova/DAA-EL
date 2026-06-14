# =============================================================================
# analyzer/chunker.py
# =============================================================================
# PURPOSE:
#   Divide a log file into T byte-range segments (one per thread) so that
#   each segment can be processed independently and in parallel.
#
#   This module implements the SPLIT step of the Map-Reduce pattern:
#
#       SPLIT  → chunker.py          (this file)
#       MAP    → parallel._process_chunk()
#       REDUCE → parallel.analyze_parallel() merge loop
#
# WHY BYTE RANGES INSTEAD OF READING ALL LINES FIRST?
# ─────────────────────────────────────────────────────
#   The naive approach would be:
#       lines = open(file).readlines()   # O(N) space — all lines in RAM
#       chunk_size = len(lines) // T
#       chunks = [lines[i:i+chunk_size] for i in range(0, len(lines), chunk_size)]
#
#   For a 500,000-line file this could occupy hundreds of MB of RAM.  More
#   importantly, it makes the SPLIT step itself O(N) time and O(N) space.
#
#   Our approach instead:
#       file_size_bytes = os.path.getsize(file)   # O(1) — one OS syscall
#       chunk_byte_size = file_size_bytes // T    # O(1) arithmetic
#       # Seek to T candidate split points        # O(T) total seeks
#
#   Time complexity:  O(T)   where T = number of threads (typically 1–16)
#   Space complexity: O(T)   we store T (start, end) tuples, nothing more
#
#   Because T ≪ N in practice, the chunker is essentially O(1) relative to
#   the file size.  The threads then each read 1/T of the file independently.
#
# THE NEWLINE-ALIGNMENT TRICK (CRITICAL CORRECTNESS DETAIL):
# ──────────────────────────────────────────────────────────
#   A naive byte split at position P might fall in the middle of a log line:
#
#       ... 2024-01-15 10:23:44 [ERROR   ] Conn|ection failed\n ...
#                                                  ^ split here
#
#   Thread 1 would see "...Conn" and thread 2 would see "ection failed\n ...".
#   Both partial lines would fail the regex pattern match and be silently
#   discarded — causing an UNDERCOUNTING BUG that is very hard to detect.
#
#   The fix: after computing each candidate split point P, seek to P and read
#   forward byte-by-byte until we find a '\n'.  Record THAT position as the
#   true boundary.  This guarantees every chunk starts and ends on a complete
#   line, so no log entry is ever split between two threads.
#
# HOW THIS MAPS TO MAP-REDUCE:
# ─────────────────────────────
#   In Hadoop/Spark, the InputFormat.getSplits() method does exactly this —
#   it divides HDFS blocks into logical input splits and aligns them to record
#   boundaries (newlines for TextInputFormat).  Our chunker is the same idea
#   at the single-machine level.
# =============================================================================

import os
from typing import List, Tuple


def get_chunks(filepath: str, num_threads: int) -> List[Tuple[int, int]]:
    """
    Divide `filepath` into `num_threads` non-overlapping byte-range chunks,
    each aligned to a newline boundary.

    Parameters
    ──────────
    filepath    : Absolute or relative path to the log file.
    num_threads : Number of chunks to create.  Should equal the number of
                  worker threads that will process them.

    Returns
    ───────
    A list of (start_byte, end_byte) tuples, one per chunk.
    Each tuple defines a half-open interval [start_byte, end_byte) of the
    file that a single thread will read.

    The last chunk's end_byte equals the total file size, ensuring every
    byte of the file belongs to exactly one chunk — no gaps, no overlaps.

    Time complexity:  O(T) — T seeks + T short forward scans (each scan is
                      at most one line length, typically < 200 bytes).
    Space complexity: O(T) — only the T result tuples are stored.

    Algorithm walk-through
    ──────────────────────
    1. Get file size S in bytes via a single OS stat call — O(1).
    2. Compute the ideal chunk size C = S // T — O(1) integer division.
    3. For each chunk i in [0, T):
         a. candidate_start = i * C
            (For i=0, start is always 0 — beginning of file.)
         b. candidate_end   = (i + 1) * C
            (For i=T-1, end is clamped to S so we never go past EOF.)
         c. If candidate_end < S, seek to candidate_end and read forward
            until '\n' — this is the newline-alignment step.
            The true boundary is the byte AFTER the '\n'.
         d. Record (start, end) for this chunk.
    4. Return the list of T chunks.
    """
    file_size = os.path.getsize(filepath)

    # Edge case: if the file is empty, return one empty chunk so callers
    # always receive a list with exactly num_threads entries.
    if file_size == 0:
        return [(0, 0)] * num_threads

    # Ideal chunk size in bytes (integer division — last chunk gets remainder).
    chunk_size = file_size // num_threads

    chunks: List[Tuple[int, int]] = []

    # We open the file once here in binary mode so we can seek freely.
    # We do NOT read the content — only peek at boundaries.
    # Binary mode ('rb') is essential: in text mode, Python on Windows
    # translates '\r\n' to '\n', which would make our byte offsets wrong.
    with open(filepath, "rb") as f:
        start = 0  # The start of the current chunk (byte offset).

        for i in range(num_threads):
            # ── Step 1: Calculate the candidate end of this chunk ──────────
            if i == num_threads - 1:
                # Last chunk always extends to the very end of the file.
                # This handles the case where file_size % num_threads != 0,
                # ensuring no bytes are left unassigned.
                end = file_size
            else:
                # Candidate split point: evenly spaced.
                candidate_end = (i + 1) * chunk_size

                # ── Step 2: Newline alignment ──────────────────────────────
                # Seek to the candidate split point and advance to the next
                # newline.  This turns a "byte split" into a "line split".
                #
                # f.seek(pos) is O(1) — it is a single OS lseek() syscall.
                # The subsequent read is at most ~200 bytes for a typical
                # log line, so this is effectively O(1) per chunk boundary.
                f.seek(candidate_end)

                # Read the remainder of the current line.
                # readline() reads until it finds '\n' or reaches EOF.
                remainder = f.readline()

                # The true end of this chunk is the byte position right
                # after the newline we just consumed.
                end = candidate_end + len(remainder)

                # Clamp to file size in case readline() returned an empty
                # bytes object (we were already at EOF).
                end = min(end, file_size)

            chunks.append((start, end))

            # The next chunk starts exactly where this one ended.
            start = end

    return chunks
