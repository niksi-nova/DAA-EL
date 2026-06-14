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
      className="sidebar-fixed"
      style={{
        width:          '220px',
        minWidth:       '220px',
        height:         '100vh',
        background:     '#111110',
        borderRight:    '1px solid #2C2A28',
        display:        'flex',
        flexDirection:  'column',
        position:       'sticky',
        top:            0,
        flexShrink:     0,
      }}
    >
      {/* Logo / app name */}
      <div style={{ padding: '20px 16px 0' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '3px' }}>
          {/* Amber square logo mark */}
          <div style={{
            width:        '8px',
            height:       '8px',
            background:   '#F59E0B',
            flexShrink:   0,
            borderRadius: '1px',
          }} />
          <span style={{
            fontFamily:  'Inter, sans-serif',
            fontWeight:  500,
            fontSize:    '15px',
            color:       '#FAFAF9',
            letterSpacing: '-0.01em',
          }}>
            logscope
          </span>
        </div>
        <div style={{
          fontSize:   '11px',
          fontFamily: 'Inter, sans-serif',
          color:      '#78716C',
          paddingLeft:'16px',
        }}>
          parallel analyzer
        </div>
      </div>

      {/* Divider */}
      <div style={{ height: '1px', background: '#2C2A28', margin: '16px 0' }} />

      {/* Nav items */}
      <nav style={{ flex: 1 }}>
        {NAV_ITEMS.map(({ id, label }) => {
          const isActive = activePage === id;
          return (
            <button
              key={id}
              onClick={() => onNavigate(id)}
              style={{
                display:         'block',
                width:           '100%',
                padding:         '8px 16px',
                textAlign:       'left',
                fontSize:        '13px',
                fontFamily:      'Inter, sans-serif',
                fontWeight:      isActive ? 500 : 400,
                color:           isActive ? '#FAFAF9' : '#78716C',
                background:      isActive ? '#292524' : 'transparent',
                borderLeft:      isActive ? '2px solid #F59E0B' : '2px solid transparent',
                borderRight:     'none',
                borderTop:       'none',
                borderBottom:    'none',
                borderRadius:    0,
                cursor:          'pointer',
                transition:      'color 0.15s, background 0.15s',
              }}
              onMouseEnter={e => {
                if (!isActive) {
                  e.currentTarget.style.color = '#A8A29E';
                  e.currentTarget.style.background = '#1C1917';
                }
              }}
              onMouseLeave={e => {
                if (!isActive) {
                  e.currentTarget.style.color = '#78716C';
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
        padding:     '12px 16px',
        borderTop:   '1px solid #2C2A28',
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
            apiOnline === null ? '#78716C' :
            apiOnline           ? '#4ADE80' :
                                  '#EF4444',
        }} />
        <span style={{
          fontSize:   '11px',
          fontFamily: 'JetBrains Mono, monospace',
          color:      '#78716C',
        }}>
          api
        </span>
        <span style={{
          fontSize:   '11px',
          fontFamily: 'JetBrains Mono, monospace',
          color:
            apiOnline === null ? '#78716C' :
            apiOnline           ? '#4ADE80' :
                                  '#EF4444',
        }}>
          {apiOnline === null ? 'checking' : apiOnline ? 'connected' : 'offline'}
        </span>
      </div>
    </aside>
  );
}
