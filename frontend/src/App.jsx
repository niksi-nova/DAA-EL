import { useState } from 'react';
import Sidebar        from './components/Sidebar.jsx';
import UploadPanel    from './components/UploadPanel.jsx';
import ResultsDashboard from './components/ResultsDashboard.jsx';
import BenchmarkChart from './components/BenchmarkChart.jsx';
import { analyzeFile, benchmarkFile } from './api.js';

/**
 * App — root component.
 *
 * State:
 *   activePage      'analyze' | 'results' | 'benchmark'
 *   analysisResult  null | /analyze response object
 *   benchmarkResult null | /benchmark response object
 *   isLoading       boolean — true while any API call is in flight
 *   error           null | string — shown in dismissible error bar
 */
export default function App() {
  const [activePage,      setActivePage]      = useState('analyze');
  const [analysisResult,  setAnalysisResult]  = useState(null);
  const [benchmarkResult, setBenchmarkResult] = useState(null);
  const [isLoading,       setIsLoading]       = useState(false);
  const [error,           setError]           = useState(null);

  // ── Analyze handler ──────────────────────────────────────────────────────
  const handleAnalyze = async (file, threads, synthetic = null, customLines = null) => {
    setError(null);
    setIsLoading(true);
    try {
      const result = await analyzeFile(file, threads, synthetic, customLines);
      setAnalysisResult(result);
      setActivePage('results');      // auto-navigate on success
    } catch (err) {
      setError(err.message);
    } finally {
      setIsLoading(false);
    }
  };

  // ── Benchmark handler ────────────────────────────────────────────────────
  const handleBenchmark = async (file, synthetic = null, customLines = null) => {
    setError(null);
    setIsLoading(true);
    try {
      const result = await benchmarkFile(file, synthetic, customLines);
      setBenchmarkResult(result);
      setActivePage('benchmark');    // auto-navigate on success
    } catch (err) {
      setError(err.message);
    } finally {
      setIsLoading(false);
    }
  };

  // ── Page content ─────────────────────────────────────────────────────────
  let pageContent;
  if (isLoading) {
    // LoadingState is embedded in UploadPanel's right column while running,
    // so we keep UploadPanel mounted but in its loading visual state.
    pageContent = (
      <UploadPanel
        onAnalyze={handleAnalyze}
        onBenchmark={handleBenchmark}
        isLoading={true}
      />
    );
  } else if (activePage === 'analyze') {
    pageContent = (
      <UploadPanel
        onAnalyze={handleAnalyze}
        onBenchmark={handleBenchmark}
        isLoading={false}
      />
    );
  } else if (activePage === 'results') {
    pageContent = analysisResult
      ? <ResultsDashboard result={analysisResult} />
      : <EmptyState message="run an analysis first" />;
  } else if (activePage === 'benchmark') {
    pageContent = benchmarkResult
      ? <BenchmarkChart result={benchmarkResult} />
      : <EmptyState message="run a benchmark first" />;
  }

  return (
    <div id="app" style={{ display: 'flex', minHeight: '100vh' }}>

      {/* Fixed sidebar — desktop */}
      <Sidebar activePage={activePage} onNavigate={setActivePage} />

      {/* Main content area */}
      <div style={{
        flex:        1,
        display:     'flex',
        flexDirection:'column',
        minWidth:    0,
      }}>
        {/* Error bar */}
        {error && (
          <div className="glass-card" style={{
            background:  'var(--danger-dim)',
            borderBottom:'1px solid var(--danger)',
            padding:     '8px 16px',
            display:     'flex',
            alignItems:  'center',
            justifyContent:'space-between',
            gap:         '12px',
            flexShrink:  0,
            margin:      '16px 32px 0 32px',
            borderRadius:'8px',
          }}>
            <span style={{
              fontSize:   '12px',
              fontFamily: 'JetBrains Mono, monospace',
              color:      '#842029',
            }}>
              &gt; error: {error}
            </span>
            <button
              onClick={() => setError(null)}
              style={{
                background:   'rgba(255, 255, 255, 0.5)',
                border:       '1px solid rgba(132, 32, 41, 0.2)',
                borderRadius: '4px',
                color:        '#842029',
                fontSize:     '11px',
                fontFamily:   'Outfit, sans-serif',
                cursor:       'pointer',
                padding:      '2px 8px',
                flexShrink:   0,
              }}
            >
              ×
            </button>
          </div>
        )}

        {/* Page body */}
        <div
          className="content-area"
          style={{
            flex:      1,
            overflowY: 'auto',
            padding:   '28px 32px',
          }}
        >
          {/* Page heading */}
          <PageHeading activePage={activePage} isLoading={isLoading} />

          {pageContent}
        </div>
      </div>

      {/* Mobile bottom nav */}
      <MobileNav activePage={activePage} onNavigate={setActivePage} />
    </div>
  );
}

/** Page heading strip — changes per active page */
function PageHeading({ activePage, isLoading }) {
  if (activePage === 'analyze') {
    return (
      <div style={{ marginBottom: '40px', marginTop: '12px' }}>
        <h1 className="outfit" style={{
          fontSize:      '36px',
          fontWeight:    700,
          color:         'var(--text-primary)',
          marginBottom:  '12px',
          letterSpacing: '-0.02em',
          lineHeight:    '1.2',
        }}>
          DAA Parallel Log Analyzer
        </h1>
        <p style={{
          fontSize:   '15px',
          fontFamily: 'Inter, sans-serif',
          color:      'var(--text-muted)',
          maxWidth:   '600px',
          lineHeight: '1.5',
        }}>
          Upload a massive log file and watch the backend split it into chunks, distribute it across CPU cores, and merge the results using MapReduce-style parallelism.
        </p>
      </div>
    );
  }

  const titles = {
    results:   'results',
    benchmark: 'benchmark',
  };
  const subs = {
    results:   'sequential · parallel · mmap comparison',
    benchmark: 'thread-count scaling — amdahl\'s law vs. measured performance',
  };

  return (
    <div style={{ marginBottom: '24px' }}>
      <div className="outfit" style={{
        fontSize:      '24px',
        fontWeight:    600,
        color:         'var(--text-primary)',
        marginBottom:  '4px',
        letterSpacing: '-0.01em',
      }}>
        {titles[activePage] ?? 'analyze'}
        {isLoading && (
          <span style={{
            fontSize:   '12px',
            fontFamily: 'JetBrains Mono, monospace',
            color:      'var(--text-muted)',
            marginLeft: '12px',
            fontWeight: 400,
          }}>
            running...
          </span>
        )}
      </div>
      <div style={{
        fontSize:   '14px',
        fontFamily: 'Inter, sans-serif',
        color:      'var(--text-muted)',
      }}>
        {subs[activePage] ?? ''}
      </div>
    </div>
  );
}

/** Empty state placeholder */
function EmptyState({ message }) {
  return (
    <div className="glass-card" style={{
      display:        'flex',
      alignItems:     'center',
      justifyContent: 'center',
      minHeight:      '200px',
      marginTop:      '24px',
    }}>
      <span style={{
        fontSize:   '13px',
        fontFamily: 'JetBrains Mono, monospace',
        color:      'var(--text-muted)',
      }}>
        &gt; {message}
      </span>
    </div>
  );
}

/**
 * MobileNav — bottom tab bar shown only on screens ≤ 768px.
 * Hidden on desktop via the CSS class `.mobile-nav { display: none }` in index.css.
 */
function MobileNav({ activePage, onNavigate }) {
  const items = [
    { id: 'analyze',   label: 'Analyze'   },
    { id: 'results',   label: 'Results'   },
    { id: 'benchmark', label: 'Benchmark' },
  ];

  return (
    <nav
      className="mobile-nav glass-card"
      style={{
        display:        'none', // overridden by media query in index.css
        position:       'fixed',
        bottom:         0,
        left:           0,
        right:          0,
        zIndex:         100,
        justifyContent: 'space-around',
        alignItems:     'center',
        paddingBottom:  'env(safe-area-inset-bottom)',
        borderRadius:   '16px 16px 0 0',
        borderBottom:   'none',
        margin:         '0 -1px', // Hide side borders slightly
      }}
    >
      {items.map(({ id, label }) => {
        const isActive = activePage === id;
        return (
          <button
            key={id}
            onClick={() => onNavigate(id)}
            className="outfit"
            style={{
              flex:       1,
              padding:    '16px 4px',
              background: 'transparent',
              border:     'none',
              borderTop:  isActive ? '3px solid var(--text-primary)' : '3px solid transparent',
              cursor:     'pointer',
              fontSize:   '13px',
              fontWeight: isActive ? 600 : 500,
              color:      isActive ? 'var(--text-primary)' : 'var(--text-muted)',
              transition: 'all 0.2s',
            }}
          >
            {label}
          </button>
        );
      })}
    </nav>
  );
}
