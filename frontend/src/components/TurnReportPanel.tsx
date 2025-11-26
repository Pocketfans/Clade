import type { TurnReport } from "../services/api.types";

interface Props {
  report: TurnReport;
}

export function TurnReportPanel({ report }: Props) {
  return (
    <div className="card">
      <div className="card-header">
        <h3 className="card-title font-display">回合 #{report.turn_index + 1}</h3>
        <span className="badge badge-primary">{report.species.length} 个重点物种</span>
      </div>
      
      <div className="card-body">
        <section className="mb-md">
          <p className="text-sm text-tertiary mb-sm">{report.pressures_summary || "本回合稳定，无额外输入。"}</p>
          <p className="text-base text-secondary">{report.narrative}</p>
        </section>
        
        <section className="mb-md">
          <h4 className="text-lg font-semibold mb-sm font-display">重点物种</h4>
          <ul style={{ listStyle: 'none', padding: 0, margin: 0, display: 'flex', flexDirection: 'column', gap: 'var(--spacing-sm)' }}>
            {report.species.map((sp) => (
              <li 
                key={sp.lineage_code}
                style={{
                  padding: 'var(--spacing-md)',
                  background: 'var(--bg-glass)',
                  borderRadius: 'var(--radius-md)',
                  borderLeft: `3px solid var(--color-primary)`
                }}
              >
                <div className="flex items-center justify-between mb-xs">
                  <strong className="text-base font-semibold">
                    {sp.latin_name} / {sp.common_name}
                  </strong>
                  <span className="badge badge-secondary badge-sm">{sp.tier ?? "未分级"}</span>
                </div>
                <small className="text-sm text-tertiary">
                  数量 {sp.population.toLocaleString()} · 死亡 {sp.deaths.toLocaleString()}（{(sp.death_rate * 100).toFixed(1)}%）
                </small>
              </li>
            ))}
          </ul>
        </section>
        
        {report.major_events.length > 0 && (
          <section className="mb-md">
            <h4 className="text-lg font-semibold mb-sm font-display">高级压力</h4>
            <ul style={{ listStyle: 'none', padding: 0, margin: 0, display: 'flex', flexDirection: 'column', gap: 'var(--spacing-xs)' }}>
              {report.major_events.map((event, idx) => (
                <li 
                  key={`${event.description}-${idx}`}
                  className="text-sm flex items-center gap-sm"
                  style={{
                    padding: 'var(--spacing-sm) var(--spacing-md)',
                    background: 'rgba(239, 68, 68, 0.1)',
                    borderRadius: 'var(--radius-sm)',
                    borderLeft: '3px solid var(--color-danger)'
                  }}
                >
                  <span className="badge badge-danger badge-sm">{event.severity}</span>
                  <span className="text-secondary">{event.description}</span>
                </li>
              ))}
            </ul>
          </section>
        )}
        
        {report.map_changes.length > 0 && (
          <section>
            <h4 className="text-lg font-semibold mb-sm font-display">地图演化</h4>
            <ul style={{ listStyle: 'none', padding: 0, margin: 0, display: 'flex', flexDirection: 'column', gap: 'var(--spacing-xs)' }}>
              {report.map_changes.map((change, idx) => (
                <li 
                  key={`${change.stage}-${idx}`}
                  className="text-sm"
                  style={{
                    padding: 'var(--spacing-sm) var(--spacing-md)',
                    background: 'rgba(6, 182, 212, 0.1)',
                    borderRadius: 'var(--radius-sm)',
                    borderLeft: '3px solid var(--color-info)'
                  }}
                >
                  <span className="badge badge-info badge-sm">{change.stage}</span>
                  <span className="text-secondary ml-sm">{change.description}（{change.affected_region}）</span>
                </li>
              ))}
            </ul>
          </section>
        )}
      </div>
    </div>
  );
}
