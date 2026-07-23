import type { ProviderConfig } from "@/services/api.types";

interface Props {
  enabled: boolean;
  savedEnabled: boolean;
  providers: Record<string, ProviderConfig>;
  adminToken: string;
  saveError: string | null;
  onEnabledChange: (enabled: boolean) => void;
  onAdminTokenChange: (value: string) => void;
}

const LOOPBACK_HOSTNAMES = new Set(["localhost", "localhost.", "127.0.0.1", "[::1]", "::1"]);

function hasLoopbackProviderForDisplay(providers: Record<string, ProviderConfig>): boolean {
  return Object.values(providers).some((provider) => {
    if (!provider.base_url) return false;
    try {
      return LOOPBACK_HOSTNAMES.has(new URL(provider.base_url).hostname.toLowerCase());
    } catch {
      return false;
    }
  });
}

export function LocalAIEndpointControl({
  enabled,
  savedEnabled,
  providers,
  adminToken,
  saveError,
  onEnabledChange,
  onAdminTokenChange,
}: Props) {
  const changed = enabled !== savedEnabled;
  const hasLoopbackProvider = hasLoopbackProviderForDisplay(providers);

  return (
    <section
      className={`config-group local-ai-control ${savedEnabled ? "is-enabled" : "is-restricted"}`}
      aria-labelledby="local-ai-control-title"
    >
      <div className="local-ai-control__header">
        <div>
          <h3 id="local-ai-control-title" className="local-ai-control__title">
            本地 AI 访问
          </h3>
          <p className="local-ai-control__description">
            控制是否允许连接本机运行的 AI 服务，修改此设置需要管理员令牌。
          </p>
        </div>
        <label className="switch">
          <input
            type="checkbox"
            aria-label="允许访问本机 AI 服务"
            checked={enabled}
            onChange={(event) => onEnabledChange(event.target.checked)}
          />
          <span className="switch-track">
            <span className="switch-thumb" />
          </span>
        </label>
      </div>

      {hasLoopbackProvider && !savedEnabled && (
        <div className="info-box warning local-ai-control__notice">
          <div className="info-box-content">
            <div className="info-box-text">
              检测到本地 AI 地址。配置已保留，当前被安全策略阻止；保存并授权后才能访问。
            </div>
          </div>
        </div>
      )}

      <div className="info-box info local-ai-control__notice">
        <div className="info-box-content">
          <div className="info-box-text">
            本设置不放行家庭局域网或其他私有网络地址；公网 AI 地址仍必须使用 HTTPS。
          </div>
        </div>
      </div>

      {changed && (
        <div className="local-ai-control__token form-control">
          <label htmlFor="local-ai-admin-token">管理员令牌</label>
          <input
            id="local-ai-admin-token"
            type="password"
            value={adminToken}
            autoComplete="off"
            spellCheck={false}
            onChange={(event) => onAdminTokenChange(event.target.value)}
          />
          <div className="local-ai-control__token-help">
            令牌只用于本次保存，保存完成或关闭设置后会立即清除。
          </div>
        </div>
      )}

      {saveError && (
        <div className="info-box warning local-ai-control__error" role="alert">
          <div className="info-box-content">
            <div className="info-box-text">{saveError}</div>
          </div>
        </div>
      )}
    </section>
  );
}
