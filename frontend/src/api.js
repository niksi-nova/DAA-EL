const BASE_URL = 'http://localhost:5000';

/**
 * POST /analyze
 * Uploads a log file and runs sequential + parallel + mmap analysis.
 *
 * @param {File}   file     - The log file to analyse
 * @param {number} threads  - Thread count for parallel analysis
 * @returns {Promise<{
 *   job_id: string,
 *   filename: string,
 *   file_size_kb: number,
 *   total_lines: number,
 *   counts: { INFO: number, WARNING: number, ERROR: number, DEBUG: number, CRITICAL: number },
 *   metrics: {
 *     sequential_time_ms: number,
 *     parallel_time_ms: number,
 *     speedup: number,
 *     efficiency_pct: number,
 *     num_threads: number
 *   },
 *   mmap_time_ms: number
 * }>}
 */
export async function analyzeFile(file, threads = 4) {
  try {
    const formData = new FormData();
    formData.append('file', file);
    formData.append('threads', String(threads));

    const res = await fetch(`${BASE_URL}/analyze`, {
      method: 'POST',
      body: formData,
    });

    if (!res.ok) {
      const err = await res.json().catch(() => ({ error: `HTTP ${res.status}` }));
      throw new Error(err.error || `Server returned ${res.status}`);
    }

    return await res.json();
  } catch (err) {
    if (err instanceof TypeError && err.message.includes('fetch')) {
      throw new Error('Cannot reach the Flask API — is the backend running on port 5000?');
    }
    throw new Error(err.message || 'Analysis request failed');
  }
}

/**
 * POST /benchmark
 * Uploads a log file and runs a full thread-count sweep (1, 2, 4, 8, 16 threads).
 *
 * @param {File} file - The log file to benchmark
 * @returns {Promise<{
 *   filename: string,
 *   file_size_kb: number,
 *   sequential_ms: number,
 *   results: Array<{
 *     threads: number,
 *     time_ms: number,
 *     actual_speedup: number,
 *     theoretical_speedup: number,
 *     efficiency_pct: number
 *   }>
 * }>}
 */
export async function benchmarkFile(file) {
  try {
    const formData = new FormData();
    formData.append('file', file);

    const res = await fetch(`${BASE_URL}/benchmark`, {
      method: 'POST',
      body: formData,
    });

    if (!res.ok) {
      const err = await res.json().catch(() => ({ error: `HTTP ${res.status}` }));
      throw new Error(err.error || `Server returned ${res.status}`);
    }

    return await res.json();
  } catch (err) {
    if (err instanceof TypeError && err.message.includes('fetch')) {
      throw new Error('Cannot reach the Flask API — is the backend running on port 5000?');
    }
    throw new Error(err.message || 'Benchmark request failed');
  }
}

/**
 * GET /health
 * Simple liveness check — resolves true if reachable, false otherwise.
 */
export async function checkHealth() {
  try {
    const res = await fetch(`${BASE_URL}/health`, { signal: AbortSignal.timeout(3000) });
    return res.ok;
  } catch {
    return false;
  }
}
