import { useEffect, useRef, useState } from 'react';

const LEVEL_COLORS = {
  INFO:     '#A8A29E',
  WARNING:  '#F59E0B',
  DEBUG:    '#78716C',
  ERROR:    '#EF4444',
  CRITICAL: '#DC2626',
};

const LEVELS_ORDER = ['INFO', 'WARNING', 'ERROR', 'DEBUG', 'CRITICAL'];

/**
 * LogLevelBar — renders all five log levels as stacked horizontal bars.
 *
 * Props:
 *   counts {object} - { INFO, WARNING, ERROR, DEBUG, CRITICAL }
 *   total  {number} - total line count (sum of all levels)
 */
export default function LogLevelBar({ counts, total }) {
  // Animate bars from 0 → final width on mount using a small state flag.
  const [animated, setAnimated] = useState(false);
  useEffect(() => {
    const raf = requestAnimationFrame(() => setAnimated(true));
    return () => cancelAnimationFrame(raf);
  }, [counts]);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
      {LEVELS_ORDER.map((level) => {
        const count   = counts?.[level] ?? 0;
        const pct     = total > 0 ? (count / total) * 100 : 0;
        const color   = LEVEL_COLORS[level];

        return (
          <div key={level} style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            {/* Level name — fixed 70px */}
            <span style={{
              fontSize:      '11px',
              fontFamily:    'Inter, sans-serif',
              fontWeight:    500,
              textTransform: 'uppercase',
              letterSpacing: '0.06em',
              color:         '#78716C',
              width:         '70px',
              flexShrink:    0,
            }}>
              {level}
            </span>

            {/* Track */}
            <div style={{
              flex:         1,
              height:       '3px',
              background:   '#2C2A28',
              borderRadius: '2px',
              overflow:     'hidden',
            }}>
              {/* Fill — animated width */}
              <div style={{
                height:          '100%',
                width:           animated ? `${pct}%` : '0%',
                background:      color,
                borderRadius:    '2px',
                transition:      'width 0.6s ease',
              }} />
            </div>

            {/* Count — fixed 60px right-aligned */}
            <span style={{
              fontSize:   '12px',
              fontFamily: 'JetBrains Mono, monospace',
              color:      '#FAFAF9',
              width:      '60px',
              textAlign:  'right',
              flexShrink: 0,
            }}>
              {count.toLocaleString()}
            </span>
          </div>
        );
      })}

      {/* Total line */}
      <div style={{
        display:       'flex',
        justifyContent:'flex-end',
        marginTop:     '4px',
        paddingTop:    '8px',
        borderTop:     '1px solid #2C2A28',
      }}>
        <span style={{
          fontSize:   '11px',
          fontFamily: 'JetBrains Mono, monospace',
          color:      '#78716C',
        }}>
          total&nbsp;&nbsp;{total?.toLocaleString() ?? 0}&nbsp;lines
        </span>
      </div>
    </div>
  );
}
