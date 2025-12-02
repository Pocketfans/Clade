/**
 * SettingsDrawer - 设置面板（重构版）
 * 
 * 优化：
 * - 宽屏横向布局，支持全屏模式
 * - 服务商连接左右分栏
 * - Embedding 独立分页
 * - 性能调优分页
 * - 模型路由分组展示
 * - 更好的滚动和内容显示
 */

import { useReducer, useCallback, useEffect, useState } from "react";
import type { UIConfig } from "@/services/api.types";
import { GamePanel } from "../common/GamePanel";
import { ConfirmDialog } from "../common/ConfirmDialog";

// 模块化组件
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

// State 管理
import { settingsReducer, createInitialState } from "./reducer";
import type { SettingsTab } from "./types";
import { NavButton } from "./common/NavButton";

// 样式
import "../SettingsDrawer.css";

interface Props {
  config: UIConfig;
  onClose: () => void;
  onSave: (config: UIConfig) => Promise<void>;
}

// Tab 配置 - 重新组织，更简洁的描述
const TABS: { id: SettingsTab; label: string; icon: string; desc?: string; group: string }[] = [
  // AI 配置
  { id: "connection", label: "服务商配置", icon: "🔌", desc: "API 连接管理", group: "AI" },
  { id: "models", label: "智能路由", icon: "🤖", desc: "模型能力分配", group: "AI" },
  { id: "embedding", label: "向量记忆", icon: "🧠", desc: "语义搜索配置", group: "AI" },
  { id: "autosave", label: "自动存档", icon: "💾", desc: "自动保存设置", group: "系统" },
  { id: "performance", label: "性能调优", icon: "⚡", desc: "超时并发控制", group: "系统" },
  // 游戏设置
  { id: "speciation", label: "分化设置", icon: "🧬", desc: "物种演化参数", group: "游戏" },
  { id: "reproduction", label: "繁殖设置", icon: "🐣", desc: "种群增长参数", group: "游戏" },
  { id: "mortality", label: "死亡率设置", icon: "💀", desc: "压力与死亡", group: "游戏" },
  { id: "ecology", label: "生态平衡", icon: "🌿", desc: "动态平衡参数", group: "游戏" },
  { id: "map", label: "地图环境", icon: "🗺️", desc: "气候地形参数", group: "游戏" },
];

export function SettingsDrawer({ config, onClose, onSave }: Props) {
  const [state, dispatch] = useReducer(settingsReducer, config, createInitialState);
  const [isFullscreen, setIsFullscreen] = useState(false);

  // 同步外部配置变化
  useEffect(() => {
    dispatch({ type: "SET_FORM", form: config });
  }, [config]);

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

  // 键盘快捷键
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      // F11 或 Ctrl+Shift+F 切换全屏
      if (e.key === "F11" || (e.ctrlKey && e.shiftKey && e.key === "F")) {
        e.preventDefault();
        setIsFullscreen(prev => !prev);
      }
      // Ctrl+S 保存
      if (e.ctrlKey && e.key === "s") {
        e.preventDefault();
        handleSave();
      }
      // Escape 关闭（非全屏时）
      if (e.key === "Escape" && !isFullscreen) {
        onClose();
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [isFullscreen, onClose, handleSave]);

  // 确认对话框
  const handleConfirmClose = useCallback(() => {
    dispatch({ type: "CLOSE_CONFIRM" });
  }, []);

  const handleConfirm = useCallback(() => {
    state.confirmDialog.onConfirm();
    dispatch({ type: "CLOSE_CONFIRM" });
  }, [state.confirmDialog]);

  // 渲染当前 Tab 内容
  const renderContent = () => {
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
            embeddingModel={state.form.embedding_model}
            embeddingDimensions={state.form.embedding_dimensions}
            dispatch={dispatch}
          />
        );
      case "performance":
        return (
          <PerformanceSection
            config={state.form}
            dispatch={dispatch}
          />
        );
      case "speciation":
        return (
          <SpeciationSection
            config={state.form.speciation || {}}
            dispatch={dispatch}
          />
        );
      case "reproduction":
        return (
          <ReproductionSection
            config={state.form.reproduction || {}}
            dispatch={dispatch}
          />
        );
      case "mortality":
        return (
          <MortalitySection
            config={state.form.mortality || {}}
            dispatch={dispatch}
          />
        );
      case "ecology":
        return (
          <EcologySection
            config={state.form.ecology_balance || {}}
            dispatch={dispatch}
          />
        );
      case "map":
        return (
          <MapSection
            config={state.form.map_environment || {}}
            dispatch={dispatch}
          />
        );
      case "autosave":
        return (
          <AutosaveSection
            config={state.form.gameplay || {}}
            dispatch={dispatch}
          />
        );
      default:
        return <div className="empty-section">选择一个设置项</div>;
    }
  };

  // 按组分类 tabs
  const groupedTabs = TABS.reduce((acc, tab) => {
    if (!acc[tab.group]) acc[tab.group] = [];
    acc[tab.group].push(tab);
    return acc;
  }, {} as Record<string, typeof TABS>);

  return (
    <GamePanel
      title={
        <span style={{ display: "flex", alignItems: "center", gap: "12px" }}>
          ⚙️ 系统设置
          <span style={{ 
            fontSize: "0.7rem", 
            color: "rgba(255,255,255,0.4)", 
            fontWeight: 400,
            marginLeft: "8px" 
          }}>
            {TABS.find(t => t.id === state.tab)?.label}
          </span>
        </span>
      }
      onClose={onClose}
      className={`settings-drawer ${isFullscreen ? 'fullscreen' : ''}`}
      footer={
        <div className="settings-footer">
          <div className="footer-left">
            <span className="shortcut-hint">Ctrl+S 保存</span>
            <span className="shortcut-hint">F11 全屏</span>
          </div>
          <div className="footer-buttons">
            <button 
              className="btn secondary" 
              onClick={() => setIsFullscreen(!isFullscreen)}
              title={isFullscreen ? "退出全屏" : "全屏模式"}
            >
              {isFullscreen ? "⛶ 退出全屏" : "⛶ 全屏"}
            </button>
            <button className="btn secondary" onClick={onClose}>
              取消
            </button>
            <button
              className="btn primary"
              onClick={handleSave}
              disabled={state.saving}
            >
              {state.saving ? "保存中..." : state.saveSuccess ? "✓ 已保存" : "💾 保存配置"}
            </button>
          </div>
        </div>
      }
    >
      <div className="settings-layout">
        {/* 侧边导航 */}
        <nav className="settings-nav">
          {Object.entries(groupedTabs).map(([group, tabs]) => (
            <div key={group} className="nav-group">
              <div className="nav-group-label"><span>{group}</span></div>
              {tabs.map((tab) => (
                <NavButton
                  key={tab.id}
                  icon={tab.icon}
                  label={tab.label}
                  desc={tab.desc}
                  isActive={state.tab === tab.id}
                  onClick={() => dispatch({ type: "SET_TAB", tab: tab.id })}
                />
              ))}
            </div>
          ))}
        </nav>

        {/* 内容区 */}
        <div className="settings-content">
          {renderContent()}
        </div>
      </div>

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
    </GamePanel>
  );
}

export default SettingsDrawer;
