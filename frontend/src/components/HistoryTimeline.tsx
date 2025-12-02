import type { TurnReport } from "@/services/api.types";
import { MarkdownRenderer, MarkdownCompact } from "./MarkdownRenderer";

interface Props {
  reports: TurnReport[];
  variant?: "bar" | "panel" | "overlay";
}

export function HistoryTimeline({ reports, variant = "bar" }: Props) {
  if (variant === "panel") {
    return (
      <div className="glass-card timeline-panel">
        <h3>灾变档案</h3>
        {reports.length === 0 ? (
          <p className="placeholder">暂无历史记录。</p>
        ) : (
          <ul>
            {reports
              .slice()
              .reverse()
              .slice(0, 6)
              .map((report) => (
                <li key={report.turn_index}>
                  <strong>回合 #{report.turn_index + 1}</strong>
                  <span>{report.pressures_summary || "平稳"}</span>
                </li>
              ))}
          </ul>
        )}
      </div>
    );
  }

  if (variant === "overlay") {
    if (reports.length === 0) {
      return <p className="placeholder">暂无历史记录。</p>;
    }
    return (
      <div className="timeline-overlay-grid">
        {reports
          .slice()
          .reverse()
          .slice(0, 12)
          .map((report) => (
            <article key={report.turn_index} className="timeline-card">
              <header>
                <span>回合 #{report.turn_index + 1}</span>
                <small>{report.pressures_summary || "平稳"}</small>
              </header>
              <div style={{ 
                maxHeight: '300px',
                overflow: 'auto'
              }}>
                <MarkdownRenderer content={report.narrative} />
              </div>
            </article>
          ))}
      </div>
    );
  }

  return (
    <section className="chronicle-bar">
      <h3>编年史</h3>
      {reports.length === 0 ? (
        <p className="placeholder">暂无历史记录。</p>
      ) : (
        <div className="timeline-cards">
          {reports
            .slice()
            .reverse()
            .slice(0, 5)
            .map((report) => (
              <article key={report.turn_index} className="timeline-card">
                <header>
                  <span>回合 #{report.turn_index + 1}</span>
                  <small>{report.pressures_summary || "平稳"}</small>
                </header>
                <div style={{ 
                  lineHeight: '1.5',
                  display: '-webkit-box',
                  WebkitLineClamp: 3,
                  WebkitBoxOrient: 'vertical',
                  overflow: 'hidden',
                  textOverflow: 'ellipsis'
                }} title={report.narrative}>
                  <MarkdownCompact content={report.narrative} />
                </div>
              </article>
            ))}
        </div>
      )}
    </section>
  );
}
