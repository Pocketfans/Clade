/**
 * EmbeddingSection - 向量记忆/Embedding 配置
 * 
 * 独立的 Embedding 配置页面，提供详细的说明和配置选项
 */

import { memo, type Dispatch } from "react";
import type { ProviderConfig } from "@/services/api.types";
import type { SettingsAction } from "../types";
import { getProviderLogo } from "../reducer";
import { EMBEDDING_PRESETS } from "../constants";

interface EmbeddingSectionProps {
  providers: Record<string, ProviderConfig>;
  embeddingProvider: string | null | undefined;
  embeddingModel: string | null | undefined;
  embeddingDimensions: number | undefined;
  dispatch: Dispatch<SettingsAction>;
}

export const EmbeddingSection = memo(function EmbeddingSection({
  providers,
  embeddingProvider,
  embeddingModel,
  embeddingDimensions,
  dispatch,
}: EmbeddingSectionProps) {
  const providerList = Object.values(providers).filter((p) => p.api_key);
  const selectedProvider = embeddingProvider ? providers[embeddingProvider] : null;
  
  const handleProviderChange = (providerId: string) => {
    dispatch({ type: "UPDATE_GLOBAL", field: "embedding_provider", value: providerId || null });
    // 重置模型选择
    if (!providerId) {
      dispatch({ type: "UPDATE_GLOBAL", field: "embedding_model", value: null });
    }
  };

  const handleModelChange = (model: string) => {
    dispatch({ type: "UPDATE_GLOBAL", field: "embedding_model", value: model || null });
    // 自动设置维度
    const preset = EMBEDDING_PRESETS.find(p => p.name === model);
    if (preset) {
      dispatch({ type: "UPDATE_GLOBAL", field: "embedding_dimensions", value: preset.dimensions });
    }
  };

  const handleDimensionsChange = (dims: number) => {
    dispatch({ type: "UPDATE_GLOBAL", field: "embedding_dimensions", value: dims });
  };

  return (
    <div className="settings-section embedding-section">
      <div className="section-header-bar">
        <div>
          <h2>🧠 向量记忆系统</h2>
          <p className="section-subtitle">Embedding 语义搜索引擎配置</p>
        </div>
      </div>

      {/* 功能介绍 */}
      <div className="feature-intro">
        <div className="intro-card">
          <div className="intro-icon">📚</div>
          <div className="intro-content">
            <h3>什么是向量记忆？</h3>
            <p>
              向量记忆系统使用 Embedding 技术将物种描述、历史事件等文本转换为高维向量，
              实现<strong>语义级别</strong>的相似度搜索。这让 AI 能够"记住"和"联想"相关内容，
              生成更连贯、更有深度的演化叙事。
            </p>
          </div>
        </div>
      </div>

      {/* 功能特性 */}
      <div className="feature-grid">
        <div className="feature-card">
          <span className="feature-icon">🔍</span>
          <h4>智能相似度搜索</h4>
          <p>根据语义而非关键词匹配相似物种和历史事件</p>
        </div>
        <div className="feature-card">
          <span className="feature-icon">📖</span>
          <h4>叙事连贯性</h4>
          <p>AI 生成描述时可参考相关历史，保持故事一致性</p>
        </div>
        <div className="feature-card">
          <span className="feature-icon">🧬</span>
          <h4>演化关联分析</h4>
          <p>发现物种间的隐性关联，辅助分化决策</p>
        </div>
        <div className="feature-card">
          <span className="feature-icon">💾</span>
          <h4>本地向量缓存</h4>
          <p>计算结果本地存储，减少重复 API 调用</p>
        </div>
      </div>

      {/* 配置区域 */}
      <div className="config-panel">
        <div className="config-header">
          <h3>⚙️ Embedding 服务配置</h3>
          <span className="status-badge enabled">
            {embeddingProvider ? "已启用" : "未配置"}
          </span>
        </div>

        <div className="config-form">
          <div className="form-group">
            <label>
              <span className="label-text">Embedding 服务商</span>
              <span className="label-required">*必选</span>
            </label>
            <select
              value={embeddingProvider || ""}
              onChange={(e) => handleProviderChange(e.target.value)}
              className={!embeddingProvider ? "warning" : ""}
            >
              <option value="">请选择服务商</option>
              {providerList.map((p) => (
                <option key={p.id} value={p.id}>
                  {getProviderLogo(p)} {p.name}
                </option>
              ))}
            </select>
            {!embeddingProvider && (
              <p className="field-warning">⚠️ 未配置 Embedding 将无法使用语义搜索功能</p>
            )}
          </div>

          {embeddingProvider && (
            <>
              <div className="form-group">
                <label>
                  <span className="label-text">Embedding 模型</span>
                </label>
                <select
                  value={embeddingModel || ""}
                  onChange={(e) => handleModelChange(e.target.value)}
                >
                  <option value="">选择或输入模型名称</option>
                  {EMBEDDING_PRESETS.map((preset) => (
                    <option key={preset.id} value={preset.name}>
                      {preset.name} ({preset.dimensions}维)
                    </option>
                  ))}
                </select>
                <input
                  type="text"
                  value={embeddingModel || ""}
                  onChange={(e) => handleModelChange(e.target.value)}
                  placeholder="或手动输入模型名称..."
                  className="custom-model-input"
                />
              </div>

              <div className="form-group">
                <label>
                  <span className="label-text">向量维度</span>
                </label>
                <input
                  type="number"
                  value={embeddingDimensions || 1536}
                  onChange={(e) => handleDimensionsChange(parseInt(e.target.value) || 1536)}
                  min={256}
                  max={8192}
                  step={256}
                />
                <p className="field-hint">常见维度：1536 (OpenAI), 1024 (BGE-M3), 4096 (Qwen)</p>
              </div>
            </>
          )}
        </div>
      </div>

      {/* 推荐模型 */}
      <div className="recommendations">
        <h3>📌 推荐 Embedding 模型</h3>
        <div className="model-cards">
          <div className="model-card recommended">
            <div className="model-badge">推荐</div>
            <h4>Qwen3-Embedding-4B</h4>
            <p className="model-provider">硅基流动 / 阿里云</p>
            <ul>
              <li>4096 维向量</li>
              <li>中英文双语优化</li>
              <li>性价比最高</li>
            </ul>
          </div>
          <div className="model-card">
            <h4>text-embedding-3-small</h4>
            <p className="model-provider">OpenAI</p>
            <ul>
              <li>1536 维向量</li>
              <li>稳定可靠</li>
              <li>全球可用</li>
            </ul>
          </div>
          <div className="model-card">
            <h4>BGE-M3</h4>
            <p className="model-provider">BAAI / 智源</p>
            <ul>
              <li>1024 维向量</li>
              <li>开源模型</li>
              <li>多语言支持</li>
            </ul>
          </div>
        </div>
      </div>

      {/* 使用提示 */}
      <div className="usage-tips">
        <h3>💡 使用建议</h3>
        <ul>
          <li>
            <strong>首次使用：</strong>系统会自动为所有物种生成向量，这可能需要几分钟时间。
          </li>
          <li>
            <strong>API 消耗：</strong>Embedding 调用费用远低于 Chat 模型，通常可忽略不计。
          </li>
          <li>
            <strong>维度选择：</strong>更高维度不一定更好，1024-2048 维通常足够，且查询更快。
          </li>
          <li>
            <strong>缓存机制：</strong>已计算的向量会本地缓存，重启游戏不会重复计算。
          </li>
        </ul>
      </div>
    </div>
  );
});

