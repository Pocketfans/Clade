import type { ActionQueueStatus, PressureDraft } from "@/services/api.types";

interface Props {
  drafts: PressureDraft[];
  status: ActionQueueStatus | null;
  onOpenPlanner: () => void;
}

export function PressureSummaryPanel({ drafts, status, onOpenPlanner }: Props) {
  const isRunning = status?.running ?? false;
  
  return (
    <div className="card">
      <div className="card-header">
        <h3 className="card-title">压力策划</h3>
        <div className={`status-indicator ${isRunning ? 'status-running' : 'status-idle'}`}>
          <span className="status-dot"></span>
          <span className="text-sm">{isRunning ? '推演中' : '待命'}</span>
        </div>
      </div>
      
      <div className="card-body">
        <dl className="flex gap-lg">
          <div className="flex flex-col gap-xs">
            <dt className="text-xs text-tertiary font-medium" style={{ textTransform: 'uppercase', letterSpacing: '0.1em' }}>队列回合</dt>
            <dd className="text-lg font-semibold text-primary">{status?.queued_rounds ?? 0}</dd>
          </div>
          <div className="flex flex-col gap-xs">
            <dt className="text-xs text-tertiary font-medium" style={{ textTransform: 'uppercase', letterSpacing: '0.1em' }}>草稿压力</dt>
            <dd className="text-lg font-semibold text-primary">{drafts.length}</dd>
          </div>
        </dl>
        
        <div className="mt-md">
          {drafts.length === 0 ? (
            <p className="text-sm text-muted">尚未设置压力，环境保持稳定。</p>
          ) : (
            <ul style={{ listStyle: 'none', padding: 0, margin: 0, display: 'flex', flexDirection: 'column', gap: 'var(--spacing-xs)' }}>
              {drafts.map((draft, idx) => (
                <li 
                  key={`${draft.kind}-${idx}`}
                  className="flex justify-between items-center p-sm rounded-sm"
                  style={{ background: 'var(--bg-glass)' }}
                >
                  <span className="text-sm">{draft.kind}</span>
                  <span className="badge badge-warning badge-sm">强度 {draft.intensity}</span>
                </li>
              ))}
            </ul>
          )}
        </div>
        
        <button 
          type="button" 
          className="btn btn-ghost mt-md" 
          onClick={onOpenPlanner}
          style={{ width: '100%' }}
        >
          打开压力策划界面
        </button>
      </div>
    </div>
  );
}
