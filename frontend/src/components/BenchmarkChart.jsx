import {
  LineChart, Line, XAxis, YAxis, Tooltip,
  ResponsiveContainer,
} from 'recharts';
import MetricCard from './MetricCard.jsx';

/** Section-label divider */
function SectionLabel({ text }) {
  return (
    <div className="section-label">
      <span>{text}</span>
    </div>
  );
}

/** Custom tooltip for the speedup line chart */
function SpeedupTooltip({ active, payload, label }) {
  if (!active || !payload?.length) return null;
  return (
    <div style={{
      background:   '#292524',
      border:       '1px solid #44403C',
      borderRadius: '4px',
      padding:      '8px 12px',
      fontFamily:   'JetBrains Mono, monospace',
      fontSize:     '12px',
    }}>
      <div style={{ color: '#A8A29E', marginBottom: '6px' }}>{label} threads</div>
      {payload.map((entry) => (
        <div key={entry.name} style={{
          color: entry.name === 'actual_speedup' ? '#F59E0B' : '#78716C',
          marginBottom: '2px',
        }}>
          {entry.name === 'actual_speedup' ? 'actual' : 'amdahl'}: {Number(entry.value).toFixed(3)}×
        </div>
      ))}
    </div>
  );
}

/**
 * BenchmarkChart — thread-count scaling analysis view.
 *
 * Props:
 *   result {object} - the full /benchmark response
 */
export default function BenchmarkChart({ result }) {
  const { sequential_ms, results, filename, file_size_kb } = result;

  // Merge theoretical speedup into chart data
  const chartData = results.map((r) => ({
    threads:            r.threads,
    actual_speedup:     r.actual_speedup,
    theoretical_speedup:r.theoretical_speedup,
  }));

  const bestResult  = results.reduce((a, b) => (a.actual_speedup > b.actual_speedup ? a : b), results[0]);
  const bestTime    = results.reduce((a, b) => (a.time_ms < b.time_ms ? a : b), results[0]);
  const bestSpeedupRow = results.indexOf(bestResult);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '28px' }}>

      {/* File info strip */}
      <div style={{ display: 'flex', gap: '16px', flexWrap: 'wrap' }}>
        <span style={{ fontSize: '12px', fontFamily: 'JetBrains Mono, monospace', color: '#78716C' }}>{filename}</span>
        <span style={{ fontSize: '12px', fontFamily: 'JetBrains Mono, monospace', color: '#44403C' }}>{file_size_kb?.toLocaleString()} KB</span>
      </div>

      {/* ── Section: thread scaling analysis ────────────────────────────── */}
      <div>
        <SectionLabel text="thread scaling analysis" />

        {/* Top metric cards */}
        <div style={{
          display:             'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))',
          gap:                 '12px',
          marginBottom:        '20px',
        }}>
          <MetricCard
            label="sequential baseline"
            value={`${sequential_ms} ms`}
            sub="single thread"
            variant="default"
          />
          <MetricCard
            label="best parallel time"
            value={`${bestTime.time_ms} ms`}
            sub={`at ${bestTime.threads} threads`}
            variant="accent"
          />
          <MetricCard
            label="peak speedup"
            value={`${bestResult.actual_speedup}×`}
            sub={`at ${bestResult.threads} threads`}
            variant="accent"
          />
        </div>

        {/* Speedup line chart */}
        <div style={{
          background:   '#292524',
          border:       '1px solid #44403C',
          borderRadius: '6px',
          padding:      '16px 16px 8px',
        }}>
          <ResponsiveContainer width="100%" height={280}>
            <LineChart data={chartData} margin={{ top: 10, right: 20, left: 0, bottom: 20 }}>
              {/* Only axis lines, no grid */}
              <XAxis
                dataKey="threads"
                axisLine={{ stroke: '#44403C' }}
                tickLine={false}
                tick={{ fill: '#78716C', fontFamily: 'JetBrains Mono', fontSize: 11 }}
                label={{ value: 'threads', position: 'insideBottom', offset: -12, fill: '#78716C', fontSize: 11, fontFamily: 'JetBrains Mono' }}
              />
              <YAxis
                axisLine={{ stroke: '#44403C' }}
                tickLine={false}
                tick={{ fill: '#78716C', fontFamily: 'JetBrains Mono', fontSize: 11 }}
                label={{ value: 'speedup ×', angle: -90, position: 'insideLeft', offset: 10, fill: '#78716C', fontSize: 11, fontFamily: 'JetBrains Mono' }}
                width={55}
              />
              <Tooltip content={<SpeedupTooltip />} />

              {/* Actual speedup — amber solid */}
              <Line
                type="monotone"
                dataKey="actual_speedup"
                stroke="#F59E0B"
                strokeWidth={2}
                dot={{ fill: '#F59E0B', r: 4, strokeWidth: 0 }}
                activeDot={{ r: 5, fill: '#F59E0B' }}
              />

              {/* Amdahl theoretical — stone dashed */}
              <Line
                type="monotone"
                dataKey="theoretical_speedup"
                stroke="#44403C"
                strokeWidth={1.5}
                strokeDasharray="4 4"
                dot={false}
                activeDot={false}
              />
            </LineChart>
          </ResponsiveContainer>

          {/* Chart legend */}
          <div style={{ display: 'flex', gap: '20px', justifyContent: 'center', marginBottom: '8px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
              <div style={{ width: '14px', height: '2px', background: '#F59E0B' }} />
              <span style={{ fontSize: '11px', fontFamily: 'Inter, sans-serif', color: '#78716C' }}>actual</span>
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
              <div style={{
                width: '14px', height: '2px',
                background: 'repeating-linear-gradient(90deg, #44403C 0 4px, transparent 4px 8px)',
              }} />
              <span style={{ fontSize: '11px', fontFamily: 'Inter, sans-serif', color: '#78716C' }}>amdahl (s=0.05)</span>
            </div>
          </div>

          {/* Annotation */}
          <div style={{
            fontSize:   '11px',
            fontFamily: 'Inter, sans-serif',
            color:      '#78716C',
            textAlign:  'center',
            fontStyle:  'italic',
          }}>
            the gap between actual and theoretical represents thread overhead and i/o variance
          </div>
        </div>
      </div>

      {/* ── Section: detailed results table ─────────────────────────────── */}
      <div>
        <SectionLabel text="detailed results" />
        <div style={{
          background:   '#111110',
          border:       '1px solid #44403C',
          borderRadius: '6px',
          padding:      '12px 16px',
          fontFamily:   'JetBrains Mono, monospace',
          fontSize:     '12px',
          overflowX:    'auto',
        }}>
          {/* Header */}
          <div style={{
            display:             'grid',
            gridTemplateColumns: '80px 100px 120px 120px 100px',
            gap:                 '8px',
            color:               '#78716C',
            paddingBottom:       '8px',
            borderBottom:        '1px solid #2C2A28',
            marginBottom:        '4px',
            minWidth:            '500px',
          }}>
            <span>threads</span>
            <span style={{ textAlign: 'right' }}>time (ms)</span>
            <span style={{ textAlign: 'right' }}>actual ×</span>
            <span style={{ textAlign: 'right' }}>theoretical ×</span>
            <span style={{ textAlign: 'right' }}>efficiency</span>
          </div>

          {/* Rows */}
          {results.map((r, idx) => {
            const isBest = idx === bestSpeedupRow;
            return (
              <div
                key={r.threads}
                style={{
                  display:             'grid',
                  gridTemplateColumns: '80px 100px 120px 120px 100px',
                  gap:                 '8px',
                  color:               '#A8A29E',
                  paddingTop:          '5px',
                  paddingBottom:       '5px',
                  paddingLeft:         isBest ? '6px' : '8px',
                  borderLeft:          isBest ? '2px solid #F59E0B' : '2px solid transparent',
                  minWidth:            '500px',
                }}
              >
                <span>{r.threads}</span>
                <span style={{ textAlign: 'right' }}>{r.time_ms.toFixed(2)}</span>
                <span style={{ textAlign: 'right', color: '#F59E0B' }}>{r.actual_speedup.toFixed(3)}</span>
                <span style={{ textAlign: 'right' }}>{r.theoretical_speedup.toFixed(3)}</span>
                <span style={{ textAlign: 'right' }}>{r.efficiency_pct?.toFixed(1)}%</span>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
