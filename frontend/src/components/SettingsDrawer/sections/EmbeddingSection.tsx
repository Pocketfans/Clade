/**
 * EmbeddingSection - 向量记忆配置 (全新设计)
 */

import { memo, useState, useCallback, type Dispatch } from "react";
import type { ProviderConfig } from "@/services/api.types";
import type { SettingsAction, TestResult } from "../types";
import { testApiConnection } from "@/services/api";
import { getProviderLogo } from "../reducer";
import { EMBEDDING_PRESETS } from "../constants";
import { SectionHeader, Card, FeatureGrid, InfoBox } from "../common/Controls";

interface Props {
  providers: Record<string, ProviderConfig>;
  embeddingProvider: string | null | undefined;
  embeddingProviderId: string | null | undefined;
  embeddingModel: string | null | undefined;
  embeddingConcurrencyEnabled?: boolean | null;
  embeddingConcurrencyLimit?: number | null;
  embeddingSemanticHotspotOnly?: boolean | null;
  embeddingSemanticHotspotLimit?: number | null;
  dispatch: Dispatch<SettingsAction>;
}

export const EmbeddingSection = memo(function EmbeddingSection({
  providers,
  embeddingProvider,
  embeddingProviderId,
  embeddingModel,
  embeddingConcurrencyEnabled,
  embeddingConcurrencyLimit,
  embeddingSemanticHotspotOnly,
  embeddingSemanticHotspotLimit,
  dispatch,
}: Props) {
  const providerList = Object.values(providers).filter((p) => p.api_key);
  // 优先使用 embedding_provider_id，兼容旧的 embedding_provider
  const effectiveProviderId = embeddingProviderId || embeddingProvider;
  const selectedProvider = effectiveProviderId ? providers[effectiveProviderId] : null;
  const concurrencyEnabled = Boolean(embeddingConcurrencyEnabled);
  const concurrencyLimit = embeddingConcurrencyLimit && embeddingConcurrencyLimit > 0 ? embeddingConcurrencyLimit : 2;
  const hotspotOnly = Boolean(embeddingSemanticHotspotOnly);
  const hotspotLimit = embeddingSemanticHotspotLimit && embeddingSemanticHotspotLimit > 0 ? embeddingSemanticHotspotLimit : 400;

  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState<TestResult | null>(null);

  // 测试连接
  const handleTest = useCallback(async () => {
    if (!selectedProvider?.base_url || !selectedProvider?.api_key) {
      setTestResult({
        success: false,
        message: "请先选择服务商并确保已配置 API Key",
      });
      return;
    }

    setTesting(true);
    setTestResult(null);

    try {
      const result = await testApiConnection({
        type: "embedding",
        base_url: selectedProvider.base_url,
        api_key: selectedProvider.api_key,
        model: embeddingModel || "Qwen/Qwen3-Embedding-4B",
        provider_type: selectedProvider.provider_type || "openai",
      });
      setTestResult(result);
    } catch (err: unknown) {
      setTestResult({
        success: false,
        message: err instanceof Error ? err.message : "测试失败",
      });
    } finally {
      setTesting(false);
    }
  }, [selectedProvider, embeddingModel]);

  const handleProviderChange = (providerId: string) => {
    dispatch({ type: "UPDATE_GLOBAL", field: "embedding_provider_id", value: providerId || null });
    // 兼容旧字段名
    dispatch({ type: "UPDATE_GLOBAL", field: "embedding_provider", value: providerId || null });
    if (!providerId) {
      dispatch({ type: "UPDATE_GLOBAL", field: "embedding_model", value: null });
    }
  };

  const handleModelChange = (model: string) => {
    dispatch({ type: "UPDATE_GLOBAL", field: "embedding_model", value: model || null });
    // 自动设置模型对应的向量维度
    const preset = EMBEDDING_PRESETS.find((p) => p.name === model);
    if (preset) {
      dispatch({ type: "UPDATE_GLOBAL", field: "embedding_dimensions", value: preset.dimensions });
    }
  };

  const handleConcurrencyToggle = (enabled: boolean) => {
    dispatch({ type: "UPDATE_GLOBAL", field: "embedding_concurrency_enabled", value: enabled });
    if (enabled && (!embeddingConcurrencyLimit || embeddingConcurrencyLimit < 2)) {
      dispatch({ type: "UPDATE_GLOBAL", field: "embedding_concurrency_limit", value: 2 });
    }
  };

  const handleConcurrencyLimitChange = (value: number) => {
    if (Number.isNaN(value)) {
      return;
    }
    const clamped = Math.min(16, Math.max(2, value));
    dispatch({ type: "UPDATE_GLOBAL", field: "embedding_concurrency_limit", value: clamped });
  };

  const handleHotspotToggle = (enabled: boolean) => {
    dispatch({ type: "UPDATE_GLOBAL", field: "embedding_semantic_hotspot_only", value: enabled });
  };

  const handleHotspotLimitChange = (value: number) => {
    if (Number.isNaN(value)) return;
    const clamped = Math.min(5120, Math.max(50, value));
    dispatch({ type: "UPDATE_GLOBAL", field: "embedding_semantic_hotspot_limit", value: clamped });
  };

  return (
    <div className="section-page">
      <SectionHeader
        icon="🧠"
        title="向量记忆系统"
        subtitle="配置 Embedding 语义搜索引擎，让 AI 能够记忆和联想相关内容"
      />

      {/* 功能介绍 */}
      <InfoBox icon="📚" title="什么是向量记忆？">
        向量记忆系统使用 Embedding 技术将文本转换为高维向量，实现语义级别的相似度搜索。
        这让 AI 能够"记住"和"联想"相关内容，生成更连贯、更有深度的演化叙事。
      </InfoBox>

      {/* 功能特性 */}
      <FeatureGrid
        items={[
          { icon: "🔍", title: "智能搜索", desc: "语义匹配而非关键词" },
          { icon: "📖", title: "叙事连贯", desc: "参考历史保持一致性" },
          { icon: "🧬", title: "关联分析", desc: "发现物种隐性关联" },
          { icon: "💾", title: "本地缓存", desc: "减少重复 API 调用" },
        ]}
      />

      {/* 配置面板 */}
      <Card
        title="Embedding 服务配置"
        icon="⚙️"
        desc={effectiveProviderId ? "已启用" : "未配置"}
      >
        {/* 服务商选择 */}
        <div className="form-row">
          <div className="form-label">
            <div className="form-label-text">
              Embedding 服务商 <span style={{ color: "var(--s-warning)", fontSize: "0.75rem" }}>*必选</span>
            </div>
          </div>
          <div className="form-control">
            <div className="select-control">
              <select
                value={effectiveProviderId || ""}
                onChange={(e) => handleProviderChange(e.target.value)}
              >
                <option value="">请选择服务商</option>
                {providerList.map((p) => (
                  <option key={p.id} value={p.id}>
                    {getProviderLogo(p)} {p.name}
                  </option>
                ))}
              </select>
            </div>
          </div>
        </div>

        {!effectiveProviderId && (
          <div style={{
            padding: "12px 16px",
            background: "var(--s-warning-bg)",
            border: "1px solid rgba(251, 191, 36, 0.3)",
            borderRadius: "var(--s-radius-md)",
            color: "var(--s-warning)",
            fontSize: "0.85rem",
            marginTop: "12px",
          }}>
            ⚠️ 未配置 Embedding 将无法使用语义搜索功能
          </div>
        )}

        {effectiveProviderId && (
          <>
            {/* 模型选择 */}
            <div className="form-row">
              <div className="form-label">
                <div className="form-label-text">Embedding 模型</div>
              </div>
              <div className="form-control">
                <div className="select-control">
                  <select
                    value={embeddingModel || ""}
                    onChange={(e) => handleModelChange(e.target.value)}
                  >
                    <option value="">选择模型</option>
                    {EMBEDDING_PRESETS.map((preset) => (
                      <option key={preset.id} value={preset.name}>
                        {preset.name} ({preset.dimensions}维)
                      </option>
                    ))}
                  </select>
                </div>
              </div>
            </div>

            {/* 并发控制 */}
            <div className="form-row">
              <div className="form-label">
                <div className="form-label-text">并发加速</div>
                <div className="form-label-desc">启用后可同时向服务商发送多个批次</div>
              </div>
              <div className="form-control" style={{ gap: "10px" }}>
                <label style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                  <input
                    type="checkbox"
                    checked={concurrencyEnabled}
                    onChange={(e) => handleConcurrencyToggle(e.target.checked)}
                  />
                  <span>允许多并发请求</span>
                </label>
                {concurrencyEnabled && (
                  <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                    <input
                      type="number"
                      min={2}
                      max={16}
                      value={concurrencyLimit}
                      onChange={(e) => handleConcurrencyLimitChange(parseInt(e.target.value, 10))}
                      style={{
                        width: "80px",
                        padding: "6px 8px",
                        background: "var(--s-bg-deep)",
                        border: "1px solid var(--s-border)",
                        borderRadius: "var(--s-radius-sm)",
                        color: "var(--s-text)",
                      }}
                    />
                    <span style={{ fontSize: "0.8rem", color: "var(--s-text-muted)" }}>建议 2 - 8</span>
                  </div>
                )}
              </div>
            </div>

            {/* 热点地块语义 */}
            <div className="form-row">
              <div className="form-label">
                <div className="form-label-text">热点语义模式</div>
                <div className="form-label-desc">仅对关键地块计算语义，减少 API 压力</div>
              </div>
              <div className="form-control" style={{ gap: "10px" }}>
                <label style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                  <input
                    type="checkbox"
                    checked={hotspotOnly}
                    onChange={(e) => handleHotspotToggle(e.target.checked)}
                  />
                  <span>只对热点地块启用语义</span>
                </label>
                {hotspotOnly && (
                  <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                    <input
                      type="number"
                      min={50}
                      max={5120}
                      value={hotspotLimit}
                      onChange={(e) => handleHotspotLimitChange(parseInt(e.target.value, 10))}
                      style={{
                        width: "100px",
                        padding: "6px 8px",
                        background: "var(--s-bg-deep)",
                        border: "1px solid var(--s-border)",
                        borderRadius: "var(--s-radius-sm)",
                        color: "var(--s-text)",
                      }}
                    />
                    <span style={{ fontSize: "0.8rem", color: "var(--s-text-muted)" }}>最大热点地块数</span>
                  </div>
                )}
              </div>
            </div>

            {/* 自定义模型输入 */}
            <div className="form-row">
              <div className="form-label">
                <div className="form-label-text">自定义模型名</div>
                <div className="form-label-desc">如果模型不在列表中</div>
              </div>
              <div className="form-control" style={{ flex: 1 }}>
                <input
                  type="text"
                  value={embeddingModel || ""}
                  onChange={(e) => handleModelChange(e.target.value)}
                  placeholder="输入模型名称..."
                  style={{
                    width: "100%",
                    maxWidth: "280px",
                    padding: "8px 12px",
                    background: "var(--s-bg-deep)",
                    border: "1px solid var(--s-border)",
                    borderRadius: "var(--s-radius-md)",
                    color: "var(--s-text)",
                    fontSize: "0.88rem",
                  }}
                />
              </div>
            </div>

            {/* 测试按钮 */}
            <div style={{ marginTop: "16px", paddingTop: "16px", borderTop: "1px solid var(--s-border)" }}>
              <button
                className="btn btn-primary"
                onClick={handleTest}
                disabled={testing || !selectedProvider}
              >
                {testing ? (
                  <>
                    <span className="spinner" /> 测试中...
                  </>
                ) : (
                  "🧬 测试向量服务"
                )}
              </button>
            </div>

            {testResult && (
              <div className={`test-result ${testResult.success ? "success" : "error"}`}>
                <span>{testResult.success ? "✓" : "✗"}</span>
                <span>{testResult.message}</span>
              </div>
            )}
          </>
        )}
      </Card>

      {/* 推荐模型 */}
      <Card title="推荐 Embedding 模型" icon="📌">
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))", gap: "14px" }}>
          {/* Qwen-8B - 高精度推荐 */}
          <div style={{
            padding: "18px",
            background: "var(--s-bg-active)",
            border: "1px solid var(--s-primary)",
            borderRadius: "var(--s-radius-md)",
            position: "relative",
          }}>
            <div style={{
              position: "absolute",
              top: "-8px",
              right: "14px",
              background: "var(--s-primary)",
              color: "white",
              fontSize: "0.68rem",
              padding: "2px 10px",
              borderRadius: "10px",
            }}>
              推荐
            </div>
            <h4 style={{ margin: "0 0 6px", fontSize: "0.95rem", color: "var(--s-text)" }}>
              Qwen3-Embedding-8B
            </h4>
            <p style={{ margin: "0 0 10px", fontSize: "0.78rem", color: "var(--s-text-muted)" }}>
              硅基流动 / 阿里云
            </p>
            <ul style={{ margin: 0, paddingLeft: "16px", fontSize: "0.78rem", color: "var(--s-text-secondary)" }}>
              <li>4096 维向量</li>
              <li>最高精度</li>
              <li>中英文双语优化</li>
            </ul>
          </div>

          {/* Qwen-4B - 性价比 */}
          <div style={{
            padding: "18px",
            background: "var(--s-bg-glass)",
            border: "1px solid var(--s-border)",
            borderRadius: "var(--s-radius-md)",
          }}>
            <h4 style={{ margin: "0 0 6px", fontSize: "0.95rem", color: "var(--s-text)" }}>
              Qwen3-Embedding-4B
            </h4>
            <p style={{ margin: "0 0 10px", fontSize: "0.78rem", color: "var(--s-text-muted)" }}>
              硅基流动 / 阿里云
            </p>
            <ul style={{ margin: 0, paddingLeft: "16px", fontSize: "0.78rem", color: "var(--s-text-secondary)" }}>
              <li>2560 维向量</li>
              <li>性价比最高</li>
              <li>速度更快</li>
            </ul>
          </div>

          {/* OpenAI */}
          <div style={{
            padding: "18px",
            background: "var(--s-bg-glass)",
            border: "1px solid var(--s-border)",
            borderRadius: "var(--s-radius-md)",
          }}>
            <h4 style={{ margin: "0 0 6px", fontSize: "0.95rem", color: "var(--s-text)" }}>
              text-embedding-3-small
            </h4>
            <p style={{ margin: "0 0 10px", fontSize: "0.78rem", color: "var(--s-text-muted)" }}>
              OpenAI
            </p>
            <ul style={{ margin: 0, paddingLeft: "16px", fontSize: "0.78rem", color: "var(--s-text-secondary)" }}>
              <li>1536 维向量</li>
              <li>稳定可靠</li>
              <li>全球可用</li>
            </ul>
          </div>

          {/* BGE */}
          <div style={{
            padding: "18px",
            background: "var(--s-bg-glass)",
            border: "1px solid var(--s-border)",
            borderRadius: "var(--s-radius-md)",
          }}>
            <h4 style={{ margin: "0 0 6px", fontSize: "0.95rem", color: "var(--s-text)" }}>
              BGE-M3
            </h4>
            <p style={{ margin: "0 0 10px", fontSize: "0.78rem", color: "var(--s-text-muted)" }}>
              BAAI / 智源
            </p>
            <ul style={{ margin: 0, paddingLeft: "16px", fontSize: "0.78rem", color: "var(--s-text-secondary)" }}>
              <li>1024 维向量</li>
              <li>开源模型</li>
              <li>多语言支持</li>
            </ul>
          </div>
        </div>
      </Card>

      {/* 使用提示 */}
      <InfoBox variant="warning" title="使用建议">
        <ul style={{ margin: 0, paddingLeft: "18px", lineHeight: 1.8 }}>
          <li><strong>首次使用：</strong>系统会自动为所有物种生成向量，可能需要几分钟</li>
          <li><strong>API 消耗：</strong>Embedding 费用远低于 Chat 模型，通常可忽略</li>
          <li><strong>维度选择：</strong>1024-2048 维通常足够，查询更快</li>
          <li><strong>缓存机制：</strong>已计算的向量会本地缓存，重启不会重复计算</li>
        </ul>
      </InfoBox>
    </div>
  );
});
