import { clearQueue } from "../services/api";
import type { ActionQueueStatus } from "../services/api.types";

interface Props {
  status: ActionQueueStatus | null;
  onOpenPressure: () => void;
  onOpenCreateSpecies: () => void;
}

const presets = ["极寒风暴", "干旱裂谷", "洪水泛滥", "火山喷发", "捕食盛潮", "资源馈赠"];

export function ControlPanel({ status, onOpenPressure, onOpenCreateSpecies }: Props) {
  const isRunning = status?.running ?? false;
  
  async function handleClearQueue() {
    if (!confirm("确定要清空所有待执行的回合吗？")) return;
    try {
      await clearQueue();
      // 状态更新依赖父组件的轮询，可能会有几秒延迟
    } catch (e) {
      console.error("清空队列失败:", e);
      alert("操作失败");
    }
  }
  
  return (
    <div className="card">
      <div className="card-header">
        <h3 className="card-title">行动队列</h3>
        <div className={`status-indicator ${isRunning ? 'status-running' : 'status-success'}`}>
          <span className="status-dot"></span>
          <span className="text-sm">{isRunning ? '推演中' : '待命'}</span>
        </div>
      </div>
      <div className="card-body">
        <dl className="flex gap-lg">
          <div className="flex flex-col gap-xs">
            <dt className="text-xs text-tertiary font-medium" style={{ textTransform: 'uppercase', letterSpacing: '0.1em' }}>待执行</dt>
            <dd className="text-lg font-semibold text-primary">{status?.queued_rounds ?? 0} 回合</dd>
          </div>
          <div className="flex flex-col gap-xs">
            <dt className="text-xs text-tertiary font-medium" style={{ textTransform: 'uppercase', letterSpacing: '0.1em' }}>状态</dt>
            <dd className="text-lg font-semibold text-primary">{isRunning ? "自动执行" : "等待指令"}</dd>
          </div>
        </dl>
        
        {isRunning && (
          <p className="text-sm text-info flex items-center gap-sm">
            <span className="spinner"></span>
            正在执行推演，请查看浏览器控制台或后端日志了解详细进度...
          </p>
        )}

        {status && status.queued_rounds > 0 && !isRunning && (
          <div style={{ marginTop: '12px', padding: '8px', background: 'rgba(0,0,0,0.2)', borderRadius: '4px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '4px' }}>
              <span className="text-xs text-tertiary">待执行计划</span>
              <button 
                type="button"
                onClick={handleClearQueue}
                style={{ fontSize: '0.75rem', padding: '2px 8px', background: '#d32f2f', border: 'none', color: 'white', borderRadius: '4px', cursor: 'pointer' }}
              >
                清空队列
              </button>
            </div>
            {status.queue_preview && status.queue_preview.length > 0 ? (
              <ul style={{ margin: 0, paddingLeft: '16px', fontSize: '0.85rem', color: '#aaa', maxHeight: '100px', overflowY: 'auto' }}>
                {status.queue_preview.map((item, idx) => (
                  <li key={idx}>{item}</li>
                ))}
              </ul>
            ) : (
              <p className="text-sm text-tertiary">自然演化 (无特殊事件)</p>
            )}
          </div>
        )}
        
        {!isRunning && (status?.queued_rounds === 0) && (
          <p className="text-sm text-tertiary">使用压力面板编排多个回合的剧变或奖励。</p>
        )}
        
        <div className="flex flex-col gap-sm mt-md">
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 'var(--spacing-sm)' }}>
            {presets.map((label) => (
              <button 
                key={label} 
                type="button" 
                className="btn btn-sm btn-secondary" 
                onClick={onOpenPressure}
                disabled={isRunning}
              >
                {label}
              </button>
            ))}
          </div>
          <button 
            type="button" 
            className="btn btn-primary" 
            onClick={onOpenPressure}
            disabled={isRunning}
          >
            打开压力策划界面
          </button>
          <button 
            type="button" 
            className="btn btn-secondary" 
            onClick={onOpenCreateSpecies}
            disabled={isRunning}
            title="直接向世界注入一个新物种"
          >
            🧬 上帝之手：创造新物种
          </button>
        </div>
      </div>
    </div>
  );
}
