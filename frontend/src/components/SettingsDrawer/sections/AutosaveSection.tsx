/**
 * AutosaveSection - 自动存档配置
 */

import { memo, type Dispatch } from "react";
import type { UIConfig } from "@/services/api.types";
import type { SettingsAction } from "../types";
import { SectionCard, ToggleRow, NumberInput } from "../common";

interface AutosaveSectionProps {
  config: UIConfig;
  dispatch: Dispatch<SettingsAction>;
}

export const AutosaveSection = memo(function AutosaveSection({
  config,
  dispatch,
}: AutosaveSectionProps) {
  const handleUpdate = (field: keyof UIConfig, value: unknown) => {
    dispatch({ type: "UPDATE_GLOBAL", field, value });
  };

  return (
    <div className="settings-section">
      <div className="section-header-bar">
        <div>
          <h2>💾 自动存档</h2>
          <p className="section-subtitle">配置游戏进度的自动保存策略</p>
        </div>
      </div>

      <SectionCard title="自动存档设置" icon="⚙️" desc="控制自动保存的行为">
        <ToggleRow
          label="启用自动存档"
          desc="每隔一定回合数自动保存游戏进度"
          checked={config.autosave_enabled ?? true}
          onChange={(v) => handleUpdate("autosave_enabled", v)}
        />

        <NumberInput
          label="存档间隔"
          desc="每隔多少回合自动保存一次"
          value={config.autosave_interval ?? 5}
          min={1}
          max={50}
          step={1}
          onChange={(v) => handleUpdate("autosave_interval", v)}
          suffix="回合"
          disabled={!config.autosave_enabled}
        />

        <NumberInput
          label="最大存档数"
          desc="保留的自动存档数量，超出后删除最旧的"
          value={config.autosave_max_slots ?? 3}
          min={1}
          max={10}
          step={1}
          onChange={(v) => handleUpdate("autosave_max_slots", v)}
          suffix="个"
          disabled={!config.autosave_enabled}
        />
      </SectionCard>

      <SectionCard title="存档说明" icon="📋">
        <div className="info-box">
          <p>
            🔹 自动存档会在每次回合结束后检查是否需要保存
          </p>
          <p>
            🔹 自动存档文件命名格式：<code>autosave_N_日期时间</code>
          </p>
          <p>
            🔹 自动存档不会覆盖手动存档，两者独立管理
          </p>
          <p>
            🔹 建议保留至少 2 个自动存档槽位以防数据损坏
          </p>
        </div>
      </SectionCard>
    </div>
  );
});

