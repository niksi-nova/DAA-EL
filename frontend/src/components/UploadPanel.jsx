import { useState, useCallback } from 'react';
import { useDropzone } from 'react-dropzone';
import LoadingState from './LoadingState.jsx';

const THREAD_OPTIONS = [1, 2, 4, 8, 16];

/** Amdahl's Law theoretical speedup: S=0.05 serial fraction */
function amdahlSpeedup(t) {
  return (1 / (0.05 + 0.95 / t)).toFixed(2);
}

function formatBytes(bytes) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
}

/**
 * UploadPanel — the Analyze page. Tool-config aesthetic.
 *
 * Props:
 *   onAnalyze   (file, threads) => Promise<void>
 *   onBenchmark (file)          => Promise<void>
 *   isLoading   boolean
 */
export default function UploadPanel({ onAnalyze, onBenchmark, isLoading }) {
  const [file,       setFile]       = useState(null);
  const [threads,    setThreads]    = useState(4);
  const [mode,       setMode]       = useState('analyze'); // 'analyze' | 'benchmark'
  const [isDragOver, setIsDragOver] = useState(false);

  const onDrop = useCallback((accepted) => {
    if (accepted.length > 0) setFile(accepted[0]);
    setIsDragOver(false);
  }, []);

  const { getRootProps, getInputProps } = useDropzone({
    onDrop,
    accept: { 'text/plain': ['.log', '.txt'] },
    multiple: false,
    onDragEnter: () => setIsDragOver(true),
    onDragLeave: () => setIsDragOver(false),
  });

  const handleSubmit = () => {
    if (!file || isLoading) return;
    if (mode === 'analyze') onAnalyze(file, threads);
    else                    onBenchmark(file);
  };

  return (
    <div style={{ display: 'flex', gap: '24px', flexWrap: 'wrap' }}>
      {/* ── Left column: config ─────────────────────────────────── */}
      <div style={{ flex: '1 1 320px', minWidth: '280px' }}>

        {/* Section: file */}
        <SectionLabel text="file input" />

        {/* Drop zone */}
        <div
          {...getRootProps()}
          className="glass-card"
          style={{
            border:       `2px dashed ${isDragOver ? 'var(--accent)' : 'var(--border)'}`,
            padding:      '40px 20px',
            textAlign:    'center',
            cursor:       'pointer',
            transition:   'all 0.2s ease',
            marginBottom: '24px',
            position:     'relative',
            background:   isDragOver ? 'rgba(255,255,255,0.7)' : 'var(--bg-surface)'
          }}
        >
          <input {...getInputProps()} />

          {file ? (
            /* File selected state */
            <div>
              {/* Clear button */}
              <button
                onClick={(e) => { e.stopPropagation(); setFile(null); }}
                style={{
                  position:   'absolute',
                  top:        '8px',
                  right:      '10px',
                  background: 'transparent',
                  border:     '1px solid var(--border)',
                  borderRadius:'8px',
                  color:      'var(--text-muted)',
                  fontSize:   '13px',
                  cursor:     'pointer',
                  padding:    '2px 8px',
                  fontFamily: 'Outfit, sans-serif',
                  transition: 'all 0.2s',
                }}
                onMouseEnter={e => { e.currentTarget.style.color = 'var(--text-primary)'; e.currentTarget.style.background = 'var(--bg-hover)'; }}
                onMouseLeave={e => { e.currentTarget.style.color = 'var(--text-muted)'; e.currentTarget.style.background = 'transparent'; }}
              >
                ×
              </button>
              <div style={{
                fontSize:   '14px',
                fontFamily: 'JetBrains Mono, monospace',
                color:      'var(--text-primary)',
                fontWeight: 500,
                marginBottom:'4px',
                wordBreak:  'break-all',
              }}>
                {file.name}
              </div>
              <div style={{
                fontSize:   '12px',
                fontFamily: 'Inter, sans-serif',
                color:      'var(--text-muted)',
              }}>
                {formatBytes(file.size)}
              </div>
            </div>
          ) : (
            /* Empty state */
            <div>
              {/* Upload arrow SVG */}
              <svg width="24" height="24" viewBox="0 0 20 20" fill="none"
                style={{ display: 'block', margin: '0 auto 12px', color: 'var(--text-dim)' }}>
                <path d="M10 3v10M5 8l5-5 5 5" stroke="currentColor" strokeWidth="2"
                  strokeLinecap="round" strokeLinejoin="round"/>
                <path d="M3 15h14" stroke="currentColor" strokeWidth="2" strokeLinecap="round"/>
              </svg>
              <div className="outfit" style={{
                fontSize:   '15px',
                color:      'var(--text-primary)',
                fontWeight: 500,
                marginBottom:'4px',
              }}>
                drop a .log or .txt file
              </div>
              <div style={{
                fontSize:   '13px',
                fontFamily: 'Inter, sans-serif',
                color:      'var(--text-muted)',
              }}>
                or click to browse
              </div>
            </div>
          )}
        </div>

        {/* Section: mode */}
        <SectionLabel text="mode" />
        <div style={{ display: 'flex', gap: '20px', marginBottom: '24px' }}>
          {['analyze', 'benchmark'].map((m) => (
            <button
              key={m}
              onClick={() => setMode(m)}
              className="outfit"
              style={{
                background:    'transparent',
                border:        'none',
                cursor:        'pointer',
                padding:       '0 0 6px',
                fontSize:      '15px',
                fontWeight:    mode === m ? 600 : 500,
                color:         mode === m ? 'var(--text-primary)' : 'var(--text-muted)',
                borderBottom:  mode === m ? '2px solid var(--accent)' : '2px solid transparent',
                transition:    'all 0.2s',
              }}
            >
              {m}
            </button>
          ))}
        </div>

        {/* Section: execution config (hidden in benchmark mode) */}
        {mode === 'analyze' && (
          <>
            <SectionLabel text="execution config" />

            {/* Thread count boxes */}
            <div style={{ display: 'flex', gap: '8px', marginBottom: '12px', flexWrap: 'wrap' }}>
              {THREAD_OPTIONS.map((t) => {
                const selected = threads === t;
                return (
                  <button
                    key={t}
                    onClick={() => setThreads(t)}
                    style={{
                      width:        '40px',
                      height:       '40px',
                      border:       selected ? 'none' : '1px solid var(--border)',
                      borderRadius: '8px',
                      background:   selected ? 'var(--accent)' : 'var(--bg-surface)',
                      color:        selected ? 'var(--text-primary)' : 'var(--text-muted)',
                      fontSize:     '14px',
                      fontFamily:   'JetBrains Mono, monospace',
                      fontWeight:   selected ? 600 : 500,
                      cursor:       'pointer',
                      display:      'flex',
                      alignItems:   'center',
                      justifyContent: 'center',
                      transition:   'all 0.15s',
                      boxShadow:    selected ? '0 4px 12px rgba(255, 209, 220, 0.4)' : 'none',
                    }}
                    onMouseEnter={e => {
                      if (!selected) {
                        e.currentTarget.style.background = 'var(--bg-hover)';
                        e.currentTarget.style.color = 'var(--text-primary)';
                      }
                    }}
                    onMouseLeave={e => {
                      if (!selected) {
                        e.currentTarget.style.background = 'var(--bg-surface)';
                        e.currentTarget.style.color = 'var(--text-muted)';
                      }
                    }}
                  >
                    {t}
                  </button>
                );
              })}
            </div>

            {/* Live Amdahl estimate */}
            <div style={{
              fontSize:   '12px',
              fontFamily: 'JetBrains Mono, monospace',
              color:      'var(--text-muted)',
              marginBottom:'24px',
            }}>
              est. speedup&nbsp;&nbsp;
              <span style={{ color: 'var(--accent-dim)', fontWeight: 600 }}>~{amdahlSpeedup(threads)}×</span>
              &nbsp;&nbsp;(amdahl, s=0.05)
            </div>
          </>
        )}

        {/* Submit */}
        <button
          onClick={handleSubmit}
          disabled={!file || isLoading}
          className="outfit"
          style={{
            width:        '100%',
            padding:      '12px 16px',
            background:   !file || isLoading ? 'var(--border)' : 'var(--accent)',
            color:        !file || isLoading ? 'var(--text-muted)'  : 'var(--text-primary)',
            border:       'none',
            borderRadius: '8px',
            fontSize:     '15px',
            fontWeight:   600,
            cursor:       !file || isLoading ? 'not-allowed' : 'pointer',
            transition:   'all 0.2s ease',
            boxShadow:    !file || isLoading ? 'none' : '0 4px 12px rgba(255, 209, 220, 0.4)',
          }}
        >
          {isLoading
            ? 'running...'
            : mode === 'analyze'
              ? 'run analysis'
              : 'run benchmark'}
        </button>
      </div>

      {/* ── Right column: loading state or quick start ─────────────────── */}
      <div style={{
        flex:       '1 1 260px',
        minWidth:   '220px',
        display:    'flex',
        alignItems: 'stretch',
      }}>
        {isLoading ? (
          <LoadingState />
        ) : (
          <div style={{ width: '100%', display: 'flex', flexDirection: 'column' }}>
            <SectionLabel text="quick start / synthetic logs" />
            <div className="glass-card" style={{ flex: 1, padding: '32px 24px', display: 'flex', flexDirection: 'column', justifyContent: 'center', gap: '24px' }}>
              <div style={{ fontSize: '14px', color: 'var(--text-muted)', lineHeight: '1.6', textAlign: 'center' }}>
                Generate a synthetic log file to instantly test the analyzer without uploading your own.
              </div>
              
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px' }}>
                {[
                  { id: 'small', label: 'Small', sub: '10K lines' },
                  { id: 'medium', label: 'Medium', sub: '100K lines' },
                  { id: 'large', label: 'Large', sub: '500K lines' },
                  { id: 'custom', label: 'Custom', sub: '...' }
                ].map((opt) => (
                  <button
                    key={opt.id}
                    onClick={() => {
                      if (opt.id === 'custom') {
                        const lines = window.prompt("Enter number of lines (e.g., 50000):", "50000");
                        if (!lines) return;
                        const num = parseInt(lines, 10);
                        if (isNaN(num) || num <= 0) {
                          alert("Please enter a valid positive number.");
                          return;
                        }
                        if (mode === 'analyze') onAnalyze(null, threads, 'custom', num);
                        else onBenchmark(null, 'custom', num);
                      } else {
                        if (mode === 'analyze') onAnalyze(null, threads, opt.id, null);
                        else onBenchmark(null, opt.id, null);
                      }
                    }}
                    style={{
                      background: 'var(--bg-base)',
                      border: '1px solid var(--border)',
                      borderRadius: '8px',
                      padding: '12px',
                      textAlign: 'center',
                      cursor: 'pointer',
                      transition: 'all 0.2s ease',
                    }}
                    onMouseEnter={e => { e.currentTarget.style.borderColor = 'var(--accent)'; e.currentTarget.style.boxShadow = '0 2px 8px rgba(255,209,220,0.3)'; }}
                    onMouseLeave={e => { e.currentTarget.style.borderColor = 'var(--border)'; e.currentTarget.style.boxShadow = 'none'; }}
                  >
                    <div className="outfit" style={{ fontSize: '15px', fontWeight: 600, color: 'var(--text-primary)', marginBottom: '4px' }}>
                      {opt.label}
                    </div>
                    <div style={{ fontSize: '11px', fontFamily: 'JetBrains Mono', color: 'var(--text-dim)' }}>
                      {opt.sub}
                    </div>
                  </button>
                ))}
              </div>
              <div style={{ fontSize: '11px', color: 'var(--text-dim)', textAlign: 'center', fontStyle: 'italic', marginTop: 'auto' }}>
                Note: Uses the currently selected mode ({mode}).
              </div>
            </div>
          </div>
        )}
      </div>
      
      {/* ── Bottom Section: Algorithm Overview ────────────────────────── */}
      <div style={{ width: '100%', marginTop: '32px' }}>
        <SectionLabel text="algorithm overview" />
        <div style={{ 
          display: 'grid', 
          gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', 
          gap: '24px',
          marginTop: '16px'
        }}>
          {/* Card 1: MapReduce */}
          <div className="glass-card" style={{ padding: '24px', transition: 'transform 0.2s ease', cursor: 'default' }} onMouseEnter={e => e.currentTarget.style.transform = 'translateY(-4px)'} onMouseLeave={e => e.currentTarget.style.transform = 'none'}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '16px' }}>
              <div style={{ width: '40px', height: '40px', borderRadius: '12px', background: 'rgba(255, 209, 220, 0.2)', display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--accent)' }}>
                <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"></path><polyline points="3.27 6.96 12 12.01 20.73 6.96"></polyline><line x1="12" y1="22.08" x2="12" y2="12"></line></svg>
              </div>
              <h3 className="outfit" style={{ fontSize: '18px', fontWeight: 600, color: 'var(--text-primary)', margin: 0 }}>MapReduce</h3>
            </div>
            <p style={{ fontSize: '14px', color: 'var(--text-muted)', lineHeight: '1.6', margin: 0 }}>
              The file is split into <code style={{ fontFamily: 'JetBrains Mono', color: 'var(--accent-dim)' }}>T</code> newline-aligned chunks in <code style={{ fontFamily: 'JetBrains Mono', color: 'var(--text-primary)' }}>O(T)</code> time. Each chunk is processed simultaneously by a separate OS worker process, bypassing Python's GIL.
            </p>
          </div>

          {/* Card 2: mmap */}
          <div className="glass-card" style={{ padding: '24px', transition: 'transform 0.2s ease', cursor: 'default' }} onMouseEnter={e => e.currentTarget.style.transform = 'translateY(-4px)'} onMouseLeave={e => e.currentTarget.style.transform = 'none'}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '16px' }}>
              <div style={{ width: '40px', height: '40px', borderRadius: '12px', background: 'rgba(255, 209, 220, 0.2)', display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--accent)' }}>
                <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"></polygon></svg>
              </div>
              <h3 className="outfit" style={{ fontSize: '18px', fontWeight: 600, color: 'var(--text-primary)', margin: 0 }}>Fast I/O (mmap)</h3>
            </div>
            <p style={{ fontSize: '14px', color: 'var(--text-muted)', lineHeight: '1.6', margin: 0 }}>
              By memory-mapping the file, we bypass the OS Kernel-to-User double copy. Workers slice bytes directly out of the OS page cache for ultra-fast regex scanning.
            </p>
          </div>

          {/* Card 3: Amdahl's Law */}
          <div className="glass-card" style={{ padding: '24px', transition: 'transform 0.2s ease', cursor: 'default' }} onMouseEnter={e => e.currentTarget.style.transform = 'translateY(-4px)'} onMouseLeave={e => e.currentTarget.style.transform = 'none'}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '16px' }}>
              <div style={{ width: '40px', height: '40px', borderRadius: '12px', background: 'rgba(255, 209, 220, 0.2)', display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--accent)' }}>
                <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><polyline points="22 12 18 12 15 21 9 3 6 12 2 12"></polyline></svg>
              </div>
              <h3 className="outfit" style={{ fontSize: '18px', fontWeight: 600, color: 'var(--text-primary)', margin: 0 }}>Amdahl's Law</h3>
            </div>
            <p style={{ fontSize: '14px', color: 'var(--text-muted)', lineHeight: '1.6', margin: 0 }}>
              Run the benchmark suite to observe theoretical vs actual speedup. Find the exact point of <strong style={{ color: 'var(--text-primary)', fontWeight: 500 }}>superlinear degradation</strong> where threads exceed physical cores.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}

/** Reusable section label with right-extending divider line */
function SectionLabel({ text }) {
  return (
    <div className="section-label" style={{ marginBottom: '14px' }}>
      <span>{text}</span>
    </div>
  );
}
