/**
 * LoadingState — terminal-style status display shown while the API is running.
 *
 * Three lines appear with 400 ms stagger. A blinking cursor follows line 3.
 * No spinner — just text, matching the engineering aesthetic of the tool.
 */
export default function LoadingState() {
  return (
    <div style={{
      display:        'flex',
      flexDirection:  'column',
      justifyContent: 'center',
      alignItems:     'flex-start',
      height:         '100%',
      minHeight:      '160px',
      padding:        '24px',
    }}>
      <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
        <div className="terminal-line-1" style={{
          fontSize:   '12px',
          fontFamily: 'JetBrains Mono, monospace',
          color:      '#78716C',
        }}>
          &gt; chunking file into segments...
        </div>

        <div className="terminal-line-2" style={{
          fontSize:   '12px',
          fontFamily: 'JetBrains Mono, monospace',
          color:      '#78716C',
        }}>
          &gt; spawning thread pool...
        </div>

        <div className="terminal-line-3" style={{
          fontSize:   '12px',
          fontFamily: 'JetBrains Mono, monospace',
          color:      '#78716C',
        }}>
          &gt; merging partial results...
          <span className="terminal-cursor" style={{ marginLeft: '2px' }}>|</span>
        </div>
      </div>
    </div>
  );
}
