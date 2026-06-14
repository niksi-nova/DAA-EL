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
          style={{
            border:       `1px dashed ${isDragOver ? '#F59E0B' : '#44403C'}`,
            borderRadius: '6px',
            background:   '#1C1917',
            padding:      '32px 20px',
            textAlign:    'center',
            cursor:       'pointer',
            transition:   'border-color 0.15s',
            marginBottom: '20px',
            position:     'relative',
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
                  border:     '1px solid #44403C',
                  borderRadius:'4px',
                  color:      '#78716C',
                  fontSize:   '11px',
                  cursor:     'pointer',
                  padding:    '2px 6px',
                  fontFamily: 'Inter, sans-serif',
                }}
                onMouseEnter={e => { e.currentTarget.style.color = '#FAFAF9'; e.currentTarget.style.borderColor = '#78716C'; }}
                onMouseLeave={e => { e.currentTarget.style.color = '#78716C'; e.currentTarget.style.borderColor = '#44403C'; }}
              >
                ×
              </button>
              <div style={{
                fontSize:   '13px',
                fontFamily: 'JetBrains Mono, monospace',
                color:      '#FAFAF9',
                marginBottom:'4px',
                wordBreak:  'break-all',
              }}>
                {file.name}
              </div>
              <div style={{
                fontSize:   '11px',
                fontFamily: 'Inter, sans-serif',
                color:      '#78716C',
              }}>
                {formatBytes(file.size)}
              </div>
            </div>
          ) : (
            /* Empty state */
            <div>
              {/* Upload arrow SVG */}
              <svg width="20" height="20" viewBox="0 0 20 20" fill="none"
                style={{ display: 'block', margin: '0 auto 10px', color: '#44403C' }}>
                <path d="M10 3v10M5 8l5-5 5 5" stroke="#44403C" strokeWidth="1.5"
                  strokeLinecap="round" strokeLinejoin="round"/>
                <path d="M3 15h14" stroke="#44403C" strokeWidth="1.5" strokeLinecap="round"/>
              </svg>
              <div style={{
                fontSize:   '12px',
                fontFamily: 'Inter, sans-serif',
                color:      '#78716C',
                marginBottom:'4px',
              }}>
                drop a .log or .txt file
              </div>
              <div style={{
                fontSize:   '11px',
                fontFamily: 'Inter, sans-serif',
                color:      '#44403C',
              }}>
                or click to browse
              </div>
            </div>
          )}
        </div>

        {/* Section: mode */}
        <SectionLabel text="mode" />
        <div style={{ display: 'flex', gap: '20px', marginBottom: '20px' }}>
          {['analyze', 'benchmark'].map((m) => (
            <button
              key={m}
              onClick={() => setMode(m)}
              style={{
                background:    'transparent',
                border:        'none',
                cursor:        'pointer',
                padding:       '0 0 4px',
                fontSize:      '13px',
                fontFamily:    'Inter, sans-serif',
                fontWeight:    mode === m ? 500 : 400,
                color:         mode === m ? '#FAFAF9' : '#78716C',
                borderBottom:  mode === m ? '1px solid #F59E0B' : '1px solid transparent',
                transition:    'color 0.15s, border-color 0.15s',
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
            <div style={{ display: 'flex', gap: '8px', marginBottom: '10px', flexWrap: 'wrap' }}>
              {THREAD_OPTIONS.map((t) => {
                const selected = threads === t;
                return (
                  <button
                    key={t}
                    onClick={() => setThreads(t)}
                    style={{
                      width:        '36px',
                      height:       '36px',
                      border:       `1px solid ${selected ? '#F59E0B' : '#44403C'}`,
                      borderRadius: '4px',
                      background:   selected ? '#F59E0B' : '#1C1917',
                      color:        selected ? '#1C1917' : '#78716C',
                      fontSize:     '13px',
                      fontFamily:   'JetBrains Mono, monospace',
                      fontWeight:   selected ? 500 : 400,
                      cursor:       'pointer',
                      display:      'flex',
                      alignItems:   'center',
                      justifyContent: 'center',
                      transition:   'all 0.1s',
                    }}
                    onMouseEnter={e => {
                      if (!selected) {
                        e.currentTarget.style.borderColor = '#78716C';
                        e.currentTarget.style.color = '#A8A29E';
                      }
                    }}
                    onMouseLeave={e => {
                      if (!selected) {
                        e.currentTarget.style.borderColor = '#44403C';
                        e.currentTarget.style.color = '#78716C';
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
              fontSize:   '11px',
              fontFamily: 'JetBrains Mono, monospace',
              color:      '#78716C',
              marginBottom:'20px',
            }}>
              est. speedup&nbsp;&nbsp;
              <span style={{ color: '#F59E0B' }}>~{amdahlSpeedup(threads)}×</span>
              &nbsp;&nbsp;(amdahl, s=0.05)
            </div>
          </>
        )}

        {/* Submit */}
        <button
          onClick={handleSubmit}
          disabled={!file || isLoading}
          style={{
            width:        '100%',
            padding:      '9px 16px',
            background:   !file || isLoading ? '#44403C' : '#F59E0B',
            color:        !file || isLoading ? '#78716C'  : '#1C1917',
            border:       'none',
            borderRadius: '4px',
            fontSize:     '13px',
            fontFamily:   'Inter, sans-serif',
            fontWeight:   500,
            cursor:       !file || isLoading ? 'not-allowed' : 'pointer',
            transition:   'background 0.15s, color 0.15s',
          }}
        >
          {isLoading
            ? 'running...'
            : mode === 'analyze'
              ? 'run analysis'
              : 'run benchmark'}
        </button>
      </div>

      {/* ── Right column: loading state ──────────────────────────── */}
      <div style={{
        flex:       '1 1 260px',
        minWidth:   '220px',
        display:    'flex',
        alignItems: 'center',
      }}>
        {isLoading && <LoadingState />}
      </div>
    </div>
  );
}

/** Reusable section label with right-extending divider line */
function SectionLabel({ text }) {
  return (
    <div className="section-label" style={{ marginBottom: '12px' }}>
      <span>{text}</span>
    </div>
  );
}
