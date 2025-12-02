/**
 * AutosaveSection - 自动存档配置 (全新设计)
 */

import { memo, type Dispatch } from "react";
import type { SettingsAction } from "../types";
import { SectionHeader, Card, ToggleRow, NumberInput, InfoBox } from "../common/Controls";

interface Props {
  autosaveEnabled: boolean;
  autosaveInterval: number;
  autosaveMaxSlots: number;
  dispatch: Dispatch<SettingsAction>;
}

export const AutosaveSection = memo(function AutosaveSection({
  autosaveEnabled,
  autosaveInterval,
  autosaveMaxSlots,
  dispatch,
}: Props) {
  const handleUpdate = (field: string, value: unknown) => {
    dispatch({ type: "UPDATE_GLOBAL", field, value });
  };

  return (
    <div className="section-page">
      <SectionHeader
        icon="💾"
        title="自动存档"
        subtitle="配置游戏进度的自动保存策略"
      />

      {/* 自动存档设置 */}
      <Card title="自动存档设置" icon="⚙️" desc="控制自动保存的行为">
        <ToggleRow
          label="启用自动存档"
          desc="每隔一定回合数自动保存游戏进度"
          checked={autosaveEnabled}
          onChange={(v) => handleUpdate("autosave_enabled", v)}
        />

        <NumberInput
          label="存档间隔"
          desc="每隔多少回合自动保存一次"
          value={autosaveInterval}
          min={1}
          max={50}
          step={1}
          onChange={(v) => handleUpdate("autosave_interval", v)}
          suffix="回合"
          disabled={!autosaveEnabled}
        />

        <NumberInput
          label="最大存档数"
          desc="保留的自动存档数量，超出后删除最旧的"
          value={autosaveMaxSlots}
          min={1}
          max={10}
          step={1}
          onChange={(v) => handleUpdate("autosave_max_slots", v)}
          suffix="个"
          disabled={!autosaveEnabled}
        />
      </Card>

      {/* 存档说明 */}
      <Card title="存档说明" icon="📋">
        <div style={{ display: "flex", flexDirection: "column", gap: "12px" }}>
          {[
            { icon: "🔹", text: "自动存档会在每次回合结束后检查是否需要保存" },
            { icon: "🔹", text: "自动存档文件命名格式：autosave_N_日期时间" },
            { icon: "🔹", text: "自动存档不会覆盖手动存档，两者独立管理" },
            { icon: "🔹", text: "建议保留至少 2 个自动存档槽位以防数据损坏" },
          ].map((item, idx) => (
            <div
              key={idx}
              style={{
                display: "flex",
                alignItems: "flex-start",
                gap: "10px",
                fontSize: "0.88rem",
                color: "var(--s-text-secondary)",
                lineHeight: 1.6,
              }}
            >
              <span style={{ color: "var(--s-accent)", flexShrink: 0 }}>{item.icon}</span>
              <span>{item.text}</span>
            </div>
          ))}
        </div>
      </Card>

      {/* 存档位置提示 */}
      <InfoBox variant="info" title="存档位置">
        存档文件保存在 <code style={{
          background: "rgba(0, 0, 0, 0.3)",
          padding: "2px 6px",
          borderRadius: "4px",
          fontFamily: "var(--s-font-mono)",
          fontSize: "0.85rem",
          color: "var(--s-accent)",
        }}>data/saves/</code> 目录下，可以手动备份或复制到其他设备。
      </InfoBox>
    </div>
  );
});
