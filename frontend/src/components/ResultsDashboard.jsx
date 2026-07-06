import {
  BarChart, Bar, XAxis, YAxis, Tooltip,
  ResponsiveContainer, Cell,
} from 'recharts';
import MetricCard from './MetricCard.jsx';
import LogLevelBar from './LogLevelBar.jsx';

const LEVELS = ['INFO', 'WARNING', 'ERROR', 'DEBUG', 'CRITICAL'];

const LEVEL_TEXT_COLORS = {
  INFO:     'var(--log-info)',
  WARNING:  'var(--log-warning)',
  ERROR:    'var(--log-error)',
  DEBUG:    'var(--log-debug)',
  CRITICAL: 'var(--log-critical)',
};

/** Section-label divider helper */
function SectionLabel({ text }) {
  return (
    <div className="section-label">
      <span>{text}</span>
    </div>
  );
}

function TimingTooltip({ active, payload }) {
  if (!active || !payload?.length) return null;
  const entry = payload[0];
  return (
    <div className="glass-card" style={{
      padding:      '12px 16px',
      fontFamily:   'JetBrains Mono, monospace',
      fontSize:     '13px',
      border:       '1px solid var(--border)',
    }}>
      <div style={{ color: 'var(--text-muted)', marginBottom: '4px' }}>{entry.payload.name}</div>
      <div style={{ color: 'var(--accent-dim)', fontWeight: 600 }}>{entry.value.toFixed(2)} ms</div>
    </div>
  );
}

/**
 * ResultsDashboard — full analysis results view with four sections:
 *   1. Overview metric cards
 *   2. Log level breakdown bars
 *   3. Timing comparison bar chart
 *   4. Raw output table + CSV export
 *
 * Props:
 *   result {object} - the full /analyze response
 */
export default function ResultsDashboard({ result }) {
  const { counts, metrics, total_lines, mmap_time_ms, filename, file_size_kb } = result;

  // ── Timing chart data ────────────────────────────────────────────────────
  const chartData = [
    { name: 'sequential', value: metrics.sequential_time_ms, fill: 'var(--text-dim)' },
    { name: 'parallel',   value: metrics.parallel_time_ms,   fill: 'var(--accent)' },
    { name: 'mmap',       value: mmap_time_ms,               fill: 'var(--success)' },
  ];

  // ── CSV export ───────────────────────────────────────────────────────────
  const exportCSV = () => {
    const rows = [
      ['level', 'count', 'share_pct'],
      ...LEVELS.map(l => [
        l,
        counts[l],
        ((counts[l] / total_lines) * 100).toFixed(2),
      ]),
      ['TOTAL', total_lines, '100.00'],
    ];
    const csv = rows.map(r => r.join(',')).join('\n');
    const blob = new Blob([csv], { type: 'text/csv' });
    const url  = URL.createObjectURL(blob);
    const a    = document.createElement('a');
    a.href     = url;
    a.download = `logscope_${filename?.replace(/\.[^.]+$/, '')}_counts.csv`;
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '28px' }}>

      {/* ── File info strip ─────────────────────────────────────────────── */}
      <div style={{
        display:    'flex',
        gap:        '16px',
        alignItems: 'center',
        flexWrap:   'wrap',
      }}>
        <span style={{ fontSize: '13px', fontFamily: 'JetBrains Mono, monospace', color: 'var(--text-primary)', fontWeight: 500 }}>
          {filename}
        </span>
        <span style={{ fontSize: '12px', fontFamily: 'JetBrains Mono, monospace', color: 'var(--text-muted)' }}>
          {file_size_kb?.toLocaleString()} KB
        </span>
        <span style={{ fontSize: '12px', fontFamily: 'JetBrains Mono, monospace', color: 'var(--text-muted)' }}>
          {total_lines?.toLocaleString()} lines
        </span>
        <span style={{ fontSize: '12px', fontFamily: 'JetBrains Mono, monospace', color: 'var(--text-muted)' }}>
          {metrics.num_threads}T
        </span>
      </div>

      {/* ── Section 1: Overview ─────────────────────────────────────────── */}
      <div>
        <SectionLabel text="overview" />
        <div style={{
          display:             'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))',
          gap:                 '12px',
        }}>
          <MetricCard
            label="speedup"
            value={`${metrics.speedup}×`}
            sub={`${metrics.num_threads} threads`}
            variant={metrics.speedup >= 1 ? 'accent' : 'danger'}
          />
          <MetricCard
            label="efficiency"
            value={`${metrics.efficiency_pct}%`}
            sub="vs ideal 100%"
            variant="default"
          />
          <MetricCard
            label="parallel time"
            value={`${metrics.parallel_time_ms} ms`}
            sub={`seq: ${metrics.sequential_time_ms} ms`}
            variant="default"
          />
          <MetricCard
            label="mmap time"
            value={`${mmap_time_ms} ms`}
            sub={`vs ${metrics.parallel_time_ms} ms parallel`}
            variant={mmap_time_ms < metrics.parallel_time_ms ? 'success' : 'default'}
          />
        </div>
      </div>

      {/* ── Section 2: Log level breakdown ──────────────────────────────── */}
      <div>
        <SectionLabel text="log level breakdown" />
        <div className="glass-card" style={{
          padding:      '20px',
        }}>
          <LogLevelBar counts={counts} total={total_lines} />
        </div>
      </div>

      {/* ── Section 3: Timing comparison chart ──────────────────────────── */}
      <div>
        <SectionLabel text="timing comparison" />
        <div className="glass-card" style={{
          padding:      '20px',
        }}>
          <ResponsiveContainer width="100%" height={180}>
            <BarChart data={chartData} margin={{ top: 10, right: 16, left: 0, bottom: 8 }}
              barCategoryGap="40%">
              <XAxis
                dataKey="name"
                axisLine={{ stroke: 'var(--border-subtle)' }}
                tickLine={false}
                tick={{ fill: 'var(--text-muted)', fontFamily: 'JetBrains Mono', fontSize: 11 }}
              />
              <YAxis
                axisLine={{ stroke: 'var(--border-subtle)' }}
                tickLine={false}
                tick={{ fill: 'var(--text-muted)', fontFamily: 'JetBrains Mono', fontSize: 11 }}
                unit=" ms"
                width={70}
              />
              <Tooltip content={<TimingTooltip />} cursor={{ fill: 'rgba(255,255,255,0.03)' }} />
              <Bar dataKey="value" radius={[3, 3, 0, 0]}>
                {chartData.map((entry) => (
                  <Cell key={entry.name} fill={entry.fill} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>

          {/* Legend */}
          <div style={{ display: 'flex', gap: '16px', justifyContent: 'center', marginTop: '4px' }}>
            {[
              { color: '#44403C', label: 'sequential' },
              { color: '#F59E0B', label: 'parallel' },
              { color: '#4ADE80', label: 'mmap+parallel' },
            ].map(({ color, label }) => (
              <div key={label} style={{ display: 'flex', alignItems: 'center', gap: '5px' }}>
                <div style={{ width: '8px', height: '8px', background: color, borderRadius: '1px', flexShrink: 0 }} />
                <span style={{ fontSize: '11px', fontFamily: 'Inter, sans-serif', color: '#78716C' }}>{label}</span>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* ── Section 4: Raw output table ──────────────────────────────────── */}
      <div>
        <SectionLabel text="raw output" />
        <div className="glass-card" style={{
          padding:      '16px 20px',
          fontFamily:   'JetBrains Mono, monospace',
          fontSize:     '13px',
        }}>
          {/* Header */}
          <div style={{
            display:             'grid',
            gridTemplateColumns: '100px 1fr 80px',
            gap:                 '8px',
            color:               'var(--text-muted)',
            marginBottom:        '12px',
            paddingBottom:       '8px',
            borderBottom:        '1px solid var(--border-subtle)',
          }}>
            <span>level</span>
            <span style={{ textAlign: 'right' }}>count</span>
            <span style={{ textAlign: 'right' }}>share</span>
          </div>

          {/* Rows */}
          {LEVELS.map((level) => {
            const count = counts[level] ?? 0;
            const pct   = total_lines > 0 ? ((count / total_lines) * 100).toFixed(1) : '0.0';
            return (
              <div key={level} style={{
                display:             'grid',
                gridTemplateColumns: '100px 1fr 80px',
                gap:                 '8px',
                color:               LEVEL_TEXT_COLORS[level],
                marginBottom:        '5px',
              }}>
                <span>{level}</span>
                <span style={{ textAlign: 'right' }}>{count.toLocaleString()}</span>
                <span style={{ textAlign: 'right' }}>{pct}%</span>
              </div>
            );
          })}

          {/* Total */}
          <div style={{
            display:             'grid',
            gridTemplateColumns: '100px 1fr 80px',
            gap:                 '8px',
            color:               'var(--text-primary)',
            marginTop:           '12px',
            paddingTop:          '12px',
            borderTop:           '1px solid var(--border-subtle)',
            fontWeight:          600,
          }}>
            <span>total</span>
            <span style={{ textAlign: 'right' }}>{total_lines?.toLocaleString()}</span>
            <span style={{ textAlign: 'right' }}>100.0%</span>
          </div>
        </div>

        {/* CSV export */}
        <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: '12px' }}>
          <button
            onClick={exportCSV}
            className="outfit"
            style={{
              background:   'var(--bg-surface)',
              color:        'var(--text-primary)',
              border:       '1px solid var(--border)',
              borderRadius: '6px',
              padding:      '6px 14px',
              fontSize:     '13px',
              fontWeight:   500,
              cursor:       'pointer',
              transition:   'all 0.2s',
            }}
            onMouseEnter={e => { e.currentTarget.style.background = 'var(--bg-hover)'; e.currentTarget.style.borderColor = 'var(--text-muted)'; }}
            onMouseLeave={e => { e.currentTarget.style.background = 'var(--bg-surface)'; e.currentTarget.style.borderColor = 'var(--border)'; }}
          >
            export csv
          </button>
        </div>
      </div>

      {/* ── Section 5: File Preview ─────────────────────────────────────── */}
      {result.file_preview && result.file_preview.length > 0 && (
        <div>
          <SectionLabel text="file preview (first 10 lines)" />
          <div className="glass-card" style={{
            padding:      '16px 20px',
            fontFamily:   'JetBrains Mono, monospace',
            fontSize:     '12px',
            color:        'var(--text-muted)',
            overflowX:    'auto',
            whiteSpace:   'pre',
            lineHeight:   '1.6',
            background:   'var(--bg-base)'
          }}>
            {result.file_preview.map((line, idx) => (
              <div key={idx}>{line}</div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
