/**
 * SettingsPanel - 全新现代化设置面板
 * 
 * 特性：
 * - 优雅的毛玻璃设计
 * - 流畅的过渡动画
 * - 完善的响应式布局 (4K/2K/1080p/720p)
 * - 模块化的 Section 组件
 */

import { useReducer, useCallback, useEffect, useRef, type ReactNode } from "react";
import type { UIConfig } from "@/services/api.types";
import { createDefaultConfig, settingsReducer, createInitialState } from "./reducer";
import type { SettingsTab, ConfirmState } from "./types";
import "./Settings.css";

// Section 组件
import {
  ConnectionSection,
  ModelsSection,
  EmbeddingSection,
  PerformanceSection,
  SpeciationSection,
  ReproductionSection,
  AutosaveSection,
  MortalitySection,
  EcologySection,
  MapSection,
} from "./sections";

interface Props {
  config: UIConfig;
  onClose: () => void;
  onSave: (config: UIConfig) => Promise<void>;
}

// Tab 配置
const TABS: {
  id: SettingsTab;
  label: string;
  icon: string;
  desc: string;
  group: "ai" | "system" | "gameplay";
}[] = [
  // AI 配置
  { id: "connection", label: "服务商配置", icon: "🔌", desc: "API 连接", group: "ai" },
  { id: "models", label: "智能路由", icon: "🤖", desc: "模型分配", group: "ai" },
  { id: "embedding", label: "向量记忆", icon: "🧠", desc: "语义搜索", group: "ai" },
  // 系统设置
  { id: "autosave", label: "自动存档", icon: "💾", desc: "自动保存", group: "system" },
  { id: "performance", label: "性能调优", icon: "⚡", desc: "超时并发", group: "system" },
  // 游戏设置
  { id: "speciation", label: "分化设置", icon: "🧬", desc: "物种演化", group: "gameplay" },
  { id: "reproduction", label: "繁殖设置", icon: "🐣", desc: "种群增长", group: "gameplay" },
  { id: "mortality", label: "死亡率", icon: "💀", desc: "压力死亡", group: "gameplay" },
  { id: "ecology", label: "生态平衡", icon: "🌿", desc: "动态平衡", group: "gameplay" },
  { id: "map", label: "地图环境", icon: "🗺️", desc: "气候地形", group: "gameplay" },
];

const GROUP_LABELS = {
  ai: "AI 配置",
  system: "系统设置",
  gameplay: "游戏设置",
};

export function SettingsPanel({ config, onClose, onSave }: Props) {
  const [state, dispatch] = useReducer(settingsReducer, config, createInitialState);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // 同步外部配置
  useEffect(() => {
    dispatch({ type: "SET_FORM", form: config });
  }, [config]);

  // 键盘快捷键
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.ctrlKey && e.key === "s") {
        e.preventDefault();
        handleSave();
      }
      if (e.key === "Escape") {
        onClose();
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [onClose]);

  // 保存配置
  const handleSave = useCallback(async () => {
    dispatch({ type: "SET_SAVING", saving: true });
    try {
      await onSave(state.form);
      dispatch({ type: "SET_SAVE_SUCCESS", success: true });
      setTimeout(() => dispatch({ type: "SET_SAVE_SUCCESS", success: false }), 2000);
    } catch (err) {
      console.error("保存配置失败:", err);
    } finally {
      dispatch({ type: "SET_SAVING", saving: false });
    }
  }, [state.form, onSave]);

  // 导出配置
  const handleExport = useCallback(() => {
    const exportData = {
      version: 1,
      exportedAt: new Date().toISOString(),
      config: state.form,
    };
    const blob = new Blob([JSON.stringify(exportData, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `clade-settings-${new Date().toISOString().slice(0, 10)}.json`;
    a.click();
    URL.revokeObjectURL(url);
  }, [state.form]);

  // 导入配置
  const handleImport = useCallback(() => {
    fileInputRef.current?.click();
  }, []);

  const handleFileChange = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    const reader = new FileReader();
    reader.onload = (event) => {
      try {
        const data = JSON.parse(event.target?.result as string);
        if (data.config && data.config.providers) {
          dispatch({
            type: "SET_CONFIRM_DIALOG",
            dialog: {
              isOpen: true,
              title: "导入配置",
              message: "导入将覆盖当前所有设置，确定要继续吗？",
              variant: "warning",
              onConfirm: () => {
                dispatch({ type: "SET_FORM", form: data.config });
              },
            },
          });
        } else {
          dispatch({
            type: "SET_CONFIRM_DIALOG",
            dialog: {
              isOpen: true,
              title: "导入失败",
              message: "无效的配置文件格式",
              variant: "danger",
              onConfirm: () => {},
            },
          });
        }
      } catch (err) {
        dispatch({
          type: "SET_CONFIRM_DIALOG",
          dialog: {
            isOpen: true,
            title: "导入失败",
            message: "解析文件失败: " + String(err),
            variant: "danger",
            onConfirm: () => {},
          },
        });
      }
    };
    reader.readAsText(file);
    e.target.value = "";
  }, []);

  // 重置配置
  const handleReset = useCallback(() => {
    dispatch({
      type: "SET_CONFIRM_DIALOG",
      dialog: {
        isOpen: true,
        title: "重置为默认",
        message: "这将清除所有自定义配置并恢复默认设置，确定要继续吗？",
        variant: "danger",
        onConfirm: () => {
          dispatch({ type: "SET_FORM", form: createDefaultConfig() });
        },
      },
    });
  }, []);

  // 关闭确认对话框
  const handleConfirmClose = useCallback(() => {
    dispatch({ type: "CLOSE_CONFIRM" });
  }, []);

  const handleConfirm = useCallback(() => {
    state.confirmDialog.onConfirm();
    dispatch({ type: "CLOSE_CONFIRM" });
  }, [state.confirmDialog]);

  // 切换 Tab
  const handleTabChange = useCallback((tab: SettingsTab) => {
    dispatch({ type: "SET_TAB", tab });
  }, []);

  // 渲染当前 Section
  const renderContent = () => {
    const props = { dispatch };
    
    switch (state.tab) {
      case "connection":
        return (
          <ConnectionSection
            providers={state.form.providers || {}}
            selectedProviderId={state.selectedProviderId}
            testResults={state.testResults}
            testingProviderId={state.testingProviderId}
            showApiKeys={state.showApiKeys}
            dispatch={dispatch}
          />
        );
      case "models":
        return (
          <ModelsSection
            providers={state.form.providers || {}}
            capabilityRoutes={state.form.capability_routes || {}}
            aiProvider={state.form.ai_provider}
            aiModel={state.form.ai_model}
            aiTimeout={state.form.ai_timeout || 60}
            dispatch={dispatch}
          />
        );
      case "embedding":
        return (
          <EmbeddingSection
            providers={state.form.providers || {}}
            embeddingProvider={state.form.embedding_provider}
            embeddingProviderId={state.form.embedding_provider_id}
            embeddingModel={state.form.embedding_model}
            dispatch={dispatch}
          />
        );
      case "performance":
        return <PerformanceSection config={state.form} dispatch={dispatch} />;
      case "speciation":
        return <SpeciationSection config={state.form.speciation || {}} dispatch={dispatch} />;
      case "reproduction":
        return <ReproductionSection config={state.form.reproduction || {}} dispatch={dispatch} />;
      case "mortality":
        return <MortalitySection config={state.form.mortality || {}} dispatch={dispatch} />;
      case "ecology":
        return <EcologySection config={state.form.ecology_balance || {}} dispatch={dispatch} />;
      case "map":
        return <MapSection config={state.form.map_environment || {}} dispatch={dispatch} />;
      case "autosave":
        return (
          <AutosaveSection
            autosaveEnabled={state.form.autosave_enabled ?? true}
            autosaveInterval={state.form.autosave_interval ?? 5}
            autosaveMaxSlots={state.form.autosave_max_slots ?? 3}
            dispatch={dispatch}
          />
        );
      default:
        return <EmptySection />;
    }
  };

  // 按组分类 tabs
  const groupedTabs = TABS.reduce((acc, tab) => {
    if (!acc[tab.group]) acc[tab.group] = [];
    acc[tab.group].push(tab);
    return acc;
  }, {} as Record<string, typeof TABS>);

  return (
    <div className="settings-panel" onClick={onClose}>
      <div className="settings-modal" onClick={(e) => e.stopPropagation()}>
        {/* 头部 */}
        <header className="settings-header">
          <div className="settings-title">
            <div className="settings-title-icon">⚙️</div>
            <div>
              <h1>系统设置</h1>
              <div className="settings-title-sub">
                {TABS.find((t) => t.id === state.tab)?.label}
              </div>
            </div>
          </div>
          <button className="settings-close" onClick={onClose} title="关闭 (Esc)">
            ✕
          </button>
        </header>

        {/* 主体 */}
        <div className="settings-body">
          {/* 侧边导航 */}
          <nav className="settings-sidebar">
            <div className="sidebar-scroll">
              {(["ai", "system", "gameplay"] as const).map((groupKey) => (
                <div key={groupKey} className="nav-group">
                  <div className="nav-group-title">{GROUP_LABELS[groupKey]}</div>
                  {groupedTabs[groupKey]?.map((tab) => (
                    <button
                      key={tab.id}
                      className={`nav-item ${state.tab === tab.id ? "active" : ""}`}
                      onClick={() => handleTabChange(tab.id)}
                    >
                      <span className="nav-item-icon">{tab.icon}</span>
                      <span className="nav-item-text">
                        <span className="nav-item-label">{tab.label}</span>
                        <span className="nav-item-desc">{tab.desc}</span>
                      </span>
                    </button>
                  ))}
                </div>
              ))}
            </div>
          </nav>

          {/* 内容区 */}
          <main className="settings-content">
            <div className="content-scroll">{renderContent()}</div>
          </main>
        </div>

        {/* 页脚 */}
        <footer className="settings-footer">
          <div className="footer-left">
            <div className="footer-shortcuts">
              <span className="shortcut-badge">Ctrl+S 保存</span>
              <span className="shortcut-badge">Esc 关闭</span>
            </div>
            <div className="footer-actions">
              <button className="btn btn-ghost" onClick={handleExport}>
                📤 导出
              </button>
              <button className="btn btn-ghost" onClick={handleImport}>
                📥 导入
              </button>
              <button className="btn btn-ghost danger" onClick={handleReset}>
                ↻ 重置
              </button>
            </div>
          </div>
          <div className="footer-right">
            <button className="btn btn-outline" onClick={onClose}>
              取消
            </button>
            <button
              className={`btn ${state.saveSuccess ? "btn-success" : "btn-primary"}`}
              onClick={handleSave}
              disabled={state.saving}
            >
              {state.saving ? (
                <>
                  <span className="spinner" /> 保存中...
                </>
              ) : state.saveSuccess ? (
                "✓ 已保存"
              ) : (
                "💾 保存配置"
              )}
            </button>
          </div>
          <input
            ref={fileInputRef}
            type="file"
            accept=".json"
            style={{ display: "none" }}
            onChange={handleFileChange}
          />
        </footer>

        {/* 确认对话框 */}
        {state.confirmDialog.isOpen && (
          <ConfirmDialog
            title={state.confirmDialog.title}
            message={state.confirmDialog.message}
            variant={state.confirmDialog.variant}
            onConfirm={handleConfirm}
            onCancel={handleConfirmClose}
          />
        )}
      </div>
    </div>
  );
}

// 空状态组件
function EmptySection() {
  return (
    <div className="empty-state">
      <div className="empty-state-icon">📋</div>
      <div className="empty-state-title">选择一个设置项</div>
      <div className="empty-state-desc">从左侧导航选择要配置的项目</div>
    </div>
  );
}

// 确认对话框组件
interface ConfirmDialogProps {
  title: string;
  message: string;
  variant: "warning" | "danger" | "info";
  onConfirm: () => void;
  onCancel: () => void;
}

function ConfirmDialog({ title, message, variant, onConfirm, onCancel }: ConfirmDialogProps) {
  return (
    <div className="confirm-overlay" onClick={onCancel}>
      <div className="confirm-dialog" onClick={(e) => e.stopPropagation()}>
        <div className="confirm-header">
          <div className={`confirm-icon ${variant}`}>
            {variant === "danger" ? "⚠️" : variant === "warning" ? "❓" : "ℹ️"}
          </div>
          <div className="confirm-title">{title}</div>
        </div>
        <div className="confirm-body">{message}</div>
        <div className="confirm-footer">
          <button className="btn btn-outline" onClick={onCancel}>
            取消
          </button>
          <button
            className={`btn ${variant === "danger" ? "btn-primary" : "btn-primary"}`}
            onClick={onConfirm}
          >
            确定
          </button>
        </div>
      </div>
    </div>
  );
}

export default SettingsPanel;

