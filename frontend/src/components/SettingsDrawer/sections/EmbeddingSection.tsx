/**
 * EmbeddingSection - 向量记忆配置
 * 单列布局，配置语义搜索引擎
 */

import { memo, useState, useCallback, useMemo, type Dispatch } from "react";
import type { ProviderConfig } from "@/services/api.types";
import type { SettingsAction, TestResult } from "../types";
import { testApiConnection } from "@/services/api";
import {
  canonicalizeProviderRecords,
  getCanonicalProviderId,
  getProviderLogo,
} from "../reducer";
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

const hasUsableApiKey = (provider: ProviderConfig) =>
  Boolean(provider.api_key || provider.api_key_configured) && !provider.api_key_clear_requested;

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
  const canonicalProviders = useMemo(() => canonicalizeProviderRecords(providers), [providers]);
  const providerList = Object.values(canonicalProviders).filter(hasUsableApiKey);
  const effectiveProviderId = getCanonicalProviderId(
    providers,
    embeddingProviderId || embeddingProvider
  );
  const selectedProvider = effectiveProviderId ? canonicalProviders[effectiveProviderId] : null;
  const concurrencyEnabled = Boolean(embeddingConcurrencyEnabled);
  const concurrencyLimit = embeddingConcurrencyLimit && embeddingConcurrencyLimit > 0 ? embeddingConcurrencyLimit : 2;
  const hotspotOnly = Boolean(embeddingSemanticHotspotOnly);
  const hotspotLimit = embeddingSemanticHotspotLimit && embeddingSemanticHotspotLimit > 0 ? embeddingSemanticHotspotLimit : 400;

  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState<TestResult | null>(null);

  const handleTest = useCallback(async () => {
    if (!selectedProvider?.base_url || !hasUsableApiKey(selectedProvider)) {
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
        provider_id: selectedProvider.id,
        base_url: selectedProvider.base_url,
        api_key: selectedProvider.api_key || "",
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
    dispatch({ type: "UPDATE_GLOBAL", field: "embedding_provider", value: providerId || null });
    if (!providerId) {
      dispatch({ type: "UPDATE_GLOBAL", field: "embedding_model", value: null });
    }
  };

  const handleModelChange = (model: string) => {
    dispatch({ type: "UPDATE_GLOBAL", field: "embedding_model", value: model || null });
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
    if (Number.isNaN(value)) return;
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
            <div className="form-label-desc">选择提供 Embedding 能力的服务商</div>
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
          <div className="info-box warning" style={{ marginTop: "12px", marginBottom: 0 }}>
             ⚠️ 未配置 Embedding 将无法使用语义搜索功能
          </div>
        )}

        {effectiveProviderId && (
          <>
            {/* 模型选择 */}
            <div className="form-row">
              <div className="form-label">
                <div className="form-label-text">Embedding 模型</div>
                <div className="form-label-desc">选择用于生成向量的模型</div>
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
            <div className="form-row form-row-compact">
              <div className="form-label">
                <div className="form-label-text">并发加速</div>
                <div className="form-label-desc">启用后可同时向服务商发送多个批次</div>
              </div>
              <div className="form-control" style={{ display: "flex", alignItems: "center", gap: "12px" }}>
                <label className="switch">
                  <input
                    type="checkbox"
                    checked={concurrencyEnabled}
                    onChange={(e) => handleConcurrencyToggle(e.target.checked)}
                  />
                  <span className="switch-track">
                    <span className="switch-thumb" />
                  </span>
                </label>
                {concurrencyEnabled && (
                  <div className="number-input" style={{ width: "100px" }}>
                    <input
                      type="number"
                      min={2}
                      max={16}
                      value={concurrencyLimit}
                      onChange={(e) => handleConcurrencyLimitChange(parseInt(e.target.value, 10))}
                    />
                    <span className="number-input-suffix">并发</span>
                  </div>
                )}
              </div>
            </div>

            {/* 热点地块语义 */}
            <div className="form-row form-row-compact">
              <div className="form-label">
                <div className="form-label-text">热点语义模式</div>
                <div className="form-label-desc">仅对关键地块计算语义，减少 API 压力</div>
              </div>
              <div className="form-control" style={{ display: "flex", alignItems: "center", gap: "12px" }}>
                <label className="switch">
                  <input
                    type="checkbox"
                    checked={hotspotOnly}
                    onChange={(e) => handleHotspotToggle(e.target.checked)}
                  />
                  <span className="switch-track">
                    <span className="switch-thumb" />
                  </span>
                </label>
                {hotspotOnly && (
                  <div className="number-input" style={{ width: "120px" }}>
                    <input
                      type="number"
                      min={50}
                      max={5120}
                      value={hotspotLimit}
                      onChange={(e) => handleHotspotLimitChange(parseInt(e.target.value, 10))}
                    />
                    <span className="number-input-suffix">地块</span>
                  </div>
                )}
              </div>
            </div>

            {/* 自定义模型输入 */}
            <div className="form-row">
              <div className="form-label">
                <div className="form-label-text">自定义模型名</div>
                <div className="form-label-desc">如果模型不在预设列表中，可手动输入</div>
              </div>
              <div className="form-control">
                <input
                  type="text"
                  value={embeddingModel || ""}
                  onChange={(e) => handleModelChange(e.target.value)}
                  placeholder="输入模型名称..."
                  style={{ width: "100%" }}
                />
              </div>
            </div>

            {/* 测试按钮 */}
            <div style={{ marginTop: "16px", paddingTop: "16px", borderTop: "1px solid var(--s-border)" }}>
              <button
                className="btn btn-primary"
                onClick={handleTest}
                disabled={testing || !selectedProvider || !hasUsableApiKey(selectedProvider)}
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
        <div className="feature-grid">
          <div className="feature-item">
            <span className="feature-item-icon">⭐</span>
            <div className="feature-item-title">Qwen3-Embedding-8B</div>
            <div className="feature-item-desc">4096 维 · 最高精度 · 推荐</div>
          </div>
          <div className="feature-item">
            <span className="feature-item-icon">💎</span>
            <div className="feature-item-title">Qwen3-Embedding-4B</div>
            <div className="feature-item-desc">2560 维 · 性价比最高</div>
          </div>
          <div className="feature-item">
            <span className="feature-item-icon">🌐</span>
            <div className="feature-item-title">text-embedding-3-small</div>
            <div className="feature-item-desc">1536 维 · OpenAI 稳定</div>
          </div>
          <div className="feature-item">
            <span className="feature-item-icon">🔓</span>
            <div className="feature-item-title">BGE-M3</div>
            <div className="feature-item-desc">1024 维 · 开源多语言</div>
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
