import { useEffect, useState } from 'react';
import { checkHealth } from '../api.js';

const NAV_ITEMS = [
  { id: 'analyze',   label: 'Analyze'   },
  { id: 'results',   label: 'Results'   },
  { id: 'benchmark', label: 'Benchmark' },
];

/**
 * Sidebar — fixed left navigation column, 220px wide.
 *
 * Props:
 *   activePage  {'analyze'|'results'|'benchmark'}
 *   onNavigate  (page: string) => void
 */
export default function Sidebar({ activePage, onNavigate }) {
  const [apiOnline, setApiOnline] = useState(null); // null = checking

  // Poll the /health endpoint once on mount, then every 15 s.
  useEffect(() => {
    let mounted = true;
    const poll = async () => {
      const ok = await checkHealth();
      if (mounted) setApiOnline(ok);
    };
    poll();
    const id = setInterval(poll, 15_000);
    return () => { mounted = false; clearInterval(id); };
  }, []);

  return (
    <aside
      className="sidebar-fixed glass-card"
      style={{
        width:          '220px',
        minWidth:       '220px',
        height:         '100vh',
        display:        'flex',
        flexDirection:  'column',
        position:       'sticky',
        top:            0,
        flexShrink:     0,
        borderRadius:   '0 16px 16px 0', /* Only round right side for sidebar */
        borderLeft:     'none',
        borderTop:      'none',
        borderBottom:   'none',
      }}
    >
      {/* Logo / app name */}
      <div style={{ padding: '24px 16px 0' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '3px' }}>
          {/* Pastel square logo mark */}
          <div style={{
            width:        '8px',
            height:       '8px',
            background:   'var(--accent)',
            flexShrink:   0,
            borderRadius: '2px',
          }} />
          <span className="outfit" style={{
            fontWeight:  600,
            fontSize:    '17px',
            color:       'var(--text-primary)',
            letterSpacing: '-0.01em',
          }}>
            logscope
          </span>
        </div>
        <div style={{
          fontSize:   '12px',
          fontFamily: 'Inter, sans-serif',
          color:      'var(--text-muted)',
          paddingLeft:'16px',
        }}>
          parallel analyzer
        </div>
      </div>

      {/* Divider */}
      <div style={{ height: '1px', background: 'var(--border-subtle)', margin: '16px 0' }} />

      {/* Nav items */}
      <nav style={{ flex: 1, padding: '0 8px' }}>
        {NAV_ITEMS.map(({ id, label }) => {
          const isActive = activePage === id;
          return (
            <button
              key={id}
              onClick={() => onNavigate(id)}
              className="outfit"
              style={{
                display:         'block',
                width:           '100%',
                padding:         '10px 16px',
                textAlign:       'left',
                fontSize:        '14px',
                fontWeight:      isActive ? 600 : 500,
                color:           isActive ? 'var(--text-primary)' : 'var(--text-muted)',
                background:      isActive ? 'var(--bg-hover)' : 'transparent',
                border:          'none',
                borderRadius:    '8px',
                cursor:          'pointer',
                transition:      'all 0.2s ease',
                marginBottom:    '4px',
              }}
              onMouseEnter={e => {
                if (!isActive) {
                  e.currentTarget.style.color = 'var(--text-primary)';
                  e.currentTarget.style.background = 'rgba(255,255,255,0.3)';
                }
              }}
              onMouseLeave={e => {
                if (!isActive) {
                  e.currentTarget.style.color = 'var(--text-muted)';
                  e.currentTarget.style.background = 'transparent';
                }
              }}
            >
              {label}
            </button>
          );
        })}
      </nav>

      {/* API status indicator */}
      <div style={{
        padding:     '16px',
        borderTop:   '1px solid var(--border-subtle)',
        display:     'flex',
        alignItems:  'center',
        gap:         '7px',
      }}>
        {/* Status dot */}
        <div style={{
          width:        '6px',
          height:       '6px',
          borderRadius: '50%',
          flexShrink:   0,
          background:
            apiOnline === null ? 'var(--text-dim)' :
            apiOnline           ? 'var(--success)' :
                                  'var(--danger)',
        }} />
        <span style={{
          fontSize:   '11px',
          fontFamily: 'JetBrains Mono, monospace',
          color:      'var(--text-muted)',
        }}>
          api
        </span>
        <span style={{
          fontSize:   '11px',
          fontFamily: 'JetBrains Mono, monospace',
          color:
            apiOnline === null ? 'var(--text-dim)' :
            apiOnline           ? 'var(--text-primary)' :
                                  'var(--danger)',
        }}>
          {apiOnline === null ? 'checking' : apiOnline ? 'connected' : 'offline'}
        </span>
      </div>
    </aside>
  );
}
