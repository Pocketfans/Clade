import type { TurnReport } from "../services/api.types";

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
                  <strong>回合 #{report.turn_index}</strong>
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
                <span>回合 #{report.turn_index}</span>
                <small>{report.pressures_summary || "平稳"}</small>
              </header>
              <p>{report.narrative.slice(0, 160)}...</p>
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
                  <span>回合 #{report.turn_index}</span>
                  <small>{report.pressures_summary || "平稳"}</small>
                </header>
                <p>{report.narrative.slice(0, 90)}...</p>
              </article>
            ))}
        </div>
      )}
    </section>
  );
}
