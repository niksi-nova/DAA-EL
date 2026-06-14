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
  const handleAnalyze = async (file, threads) => {
    setError(null);
    setIsLoading(true);
    try {
      const result = await analyzeFile(file, threads);
      setAnalysisResult(result);
      setActivePage('results');      // auto-navigate on success
    } catch (err) {
      setError(err.message);
    } finally {
      setIsLoading(false);
    }
  };

  // ── Benchmark handler ────────────────────────────────────────────────────
  const handleBenchmark = async (file) => {
    setError(null);
    setIsLoading(true);
    try {
      const result = await benchmarkFile(file);
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
          <div style={{
            background:  '#450A0A',
            borderBottom:'1px solid #EF4444',
            padding:     '8px 16px',
            display:     'flex',
            alignItems:  'center',
            justifyContent:'space-between',
            gap:         '12px',
            flexShrink:  0,
          }}>
            <span style={{
              fontSize:   '12px',
              fontFamily: 'JetBrains Mono, monospace',
              color:      '#EF4444',
            }}>
              &gt; error: {error}
            </span>
            <button
              onClick={() => setError(null)}
              style={{
                background:   'transparent',
                border:       '1px solid #EF4444',
                borderRadius: '4px',
                color:        '#EF4444',
                fontSize:     '11px',
                fontFamily:   'Inter, sans-serif',
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
  const titles = {
    analyze:   'analyze',
    results:   'results',
    benchmark: 'benchmark',
  };
  const subs = {
    analyze:   'upload a log file and run the parallel analysis engine',
    results:   'sequential · parallel · mmap comparison',
    benchmark: 'thread-count scaling — amdahl\'s law vs. measured performance',
  };

  return (
    <div style={{ marginBottom: '24px' }}>
      <div style={{
        fontSize:      '16px',
        fontFamily:    'Inter, sans-serif',
        fontWeight:    500,
        color:         '#FAFAF9',
        marginBottom:  '4px',
        letterSpacing: '-0.01em',
      }}>
        {titles[activePage] ?? 'analyze'}
        {isLoading && (
          <span style={{
            fontSize:   '11px',
            fontFamily: 'JetBrains Mono, monospace',
            color:      '#F59E0B',
            marginLeft: '12px',
            fontWeight: 400,
          }}>
            running...
          </span>
        )}
      </div>
      <div style={{
        fontSize:   '12px',
        fontFamily: 'Inter, sans-serif',
        color:      '#78716C',
      }}>
        {subs[activePage] ?? ''}
      </div>
    </div>
  );
}

/** Empty state placeholder */
function EmptyState({ message }) {
  return (
    <div style={{
      display:        'flex',
      alignItems:     'center',
      justifyContent: 'center',
      minHeight:      '200px',
    }}>
      <span style={{
        fontSize:   '13px',
        fontFamily: 'JetBrains Mono, monospace',
        color:      '#78716C',
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
      className="mobile-nav"
      style={{
        display:        'none', // overridden by media query in index.css
        position:       'fixed',
        bottom:         0,
        left:           0,
        right:          0,
        background:     '#111110',
        borderTop:      '1px solid #2C2A28',
        zIndex:         100,
        justifyContent: 'space-around',
        alignItems:     'center',
        paddingBottom:  'env(safe-area-inset-bottom)',
      }}
    >
      {items.map(({ id, label }) => {
        const isActive = activePage === id;
        return (
          <button
            key={id}
            onClick={() => onNavigate(id)}
            style={{
              flex:       1,
              padding:    '12px 4px',
              background: 'transparent',
              border:     'none',
              borderTop:  isActive ? '2px solid #F59E0B' : '2px solid transparent',
              cursor:     'pointer',
              fontSize:   '11px',
              fontFamily: 'Inter, sans-serif',
              fontWeight: isActive ? 500 : 400,
              color:      isActive ? '#FAFAF9' : '#78716C',
              transition: 'color 0.15s',
            }}
          >
            {label}
          </button>
        );
      })}
    </nav>
  );
}
