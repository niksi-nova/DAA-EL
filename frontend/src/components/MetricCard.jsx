/**
 * MetricCard — a compact labelled value tile used throughout the dashboard.
 *
 * Props:
 *   label   {string}  - Short uppercase label shown above the value
 *   value   {string|number} - The primary value displayed in large mono type
 *   sub     {string}  - Optional sub-label shown below the value
 *   variant {'default'|'accent'|'danger'|'success'} - Controls value colour
 */
export default function MetricCard({ label, value, sub, variant = 'default' }) {
  const valueColor = {
    default: 'var(--text-primary)',
    accent:  'var(--accent)',
    danger:  'var(--danger)',
    success: 'var(--success)',
  }[variant] ?? 'var(--text-primary)';

  return (
    <div className="glass-card" style={{
      padding:      '20px',
    }}>
      {/* Label */}
      <div className="outfit" style={{
        fontSize:      '12px',
        fontWeight:    600,
        textTransform: 'uppercase',
        letterSpacing: '0.08em',
        color:         'var(--text-muted)',
        marginBottom:  '8px',
      }}>
        {label}
      </div>

      {/* Value */}
      <div style={{
        fontSize:    '24px',
        fontFamily:  'JetBrains Mono, monospace',
        fontWeight:  600,
        color:       valueColor,
        lineHeight:  1.2,
      }}>
        {value}
      </div>

      {/* Optional sub-label */}
      {sub && (
        <div style={{
          fontSize:   '12px',
          fontFamily: 'Inter, sans-serif',
          color:      'var(--text-dim)',
          marginTop:  '6px',
        }}>
          {sub}
        </div>
      )}
    </div>
  );
}
