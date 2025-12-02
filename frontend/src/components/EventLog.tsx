import type { TurnReport } from "@/services/api.types";

interface Props {
  report?: TurnReport | null;
}

export function EventLog({ report }: Props) {
  const events: { type: string; message: string }[] = [];
  
  if (report) {
    report.major_events.forEach((event) =>
      events.push({ type: 'danger', message: `灾变 ${event.description}（${event.severity}）` }),
    );
    report.migration_events.forEach((event) =>
      events.push({ type: 'info', message: `迁徙 ${event.lineage_code} → ${event.destination}` }),
    );
    report.branching_events.forEach((event) =>
      events.push({ type: 'success', message: `分化 ${event.parent_lineage} → ${event.new_lineage}` }),
    );
  }

  return (
    <div className="card">
      <div className="card-header">
        <h3 className="card-title">事件日志</h3>
        <span className="badge badge-secondary badge-sm">最近 8 条</span>
      </div>
      <div className="card-body">
        {events.length === 0 ? (
          <p className="text-muted text-sm">暂无新事件。</p>
        ) : (
          <ul style={{ listStyle: 'none', padding: 0, margin: 0, display: 'flex', flexDirection: 'column', gap: 'var(--spacing-xs)' }}>
            {events.slice(0, 8).map((event, idx) => (
              <li 
                key={idx}
                className="text-sm"
                style={{ 
                  display: 'flex', 
                  alignItems: 'center', 
                  gap: 'var(--spacing-sm)',
                  padding: 'var(--spacing-xs) var(--spacing-sm)',
                  borderRadius: 'var(--radius-sm)',
                  background: 'var(--bg-glass)'
                }}
              >
                <span 
                  className={`badge badge-${event.type} badge-sm`}
                  style={{ minWidth: '60px', justifyContent: 'center' }}
                >
                  {event.type === 'danger' ? '灾变' : event.type === 'info' ? '迁徙' : '分化'}
                </span>
                <span className="text-secondary">{event.message}</span>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
