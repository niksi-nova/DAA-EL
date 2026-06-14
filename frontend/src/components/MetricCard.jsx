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
    default: '#FAFAF9',
    accent:  '#F59E0B',
    danger:  '#EF4444',
    success: '#4ADE80',
  }[variant] ?? '#FAFAF9';

  return (
    <div style={{
      background:   '#292524',
      border:       '1px solid #44403C',
      borderRadius: '6px',
      padding:      '16px',
    }}>
      {/* Label */}
      <div style={{
        fontSize:      '11px',
        fontFamily:    'Inter, sans-serif',
        fontWeight:    500,
        textTransform: 'uppercase',
        letterSpacing: '0.08em',
        color:         '#78716C',
        marginBottom:  '6px',
      }}>
        {label}
      </div>

      {/* Value */}
      <div style={{
        fontSize:    '22px',
        fontFamily:  'JetBrains Mono, monospace',
        fontWeight:  500,
        color:       valueColor,
        lineHeight:  1.2,
      }}>
        {value}
      </div>

      {/* Optional sub-label */}
      {sub && (
        <div style={{
          fontSize:   '11px',
          fontFamily: 'Inter, sans-serif',
          color:      '#78716C',
          marginTop:  '4px',
        }}>
          {sub}
        </div>
      )}
    </div>
  );
}
