/**
 * ChartContainer - 图表容器组件
 */

import { memo, type ReactNode } from "react";
import { THEME } from "../theme";

interface ChartContainerProps {
  title: string;
  subtitle?: string;
  children: ReactNode;
  actions?: ReactNode;
  height?: number | string;
}

export const ChartContainer = memo(function ChartContainer({
  title,
  subtitle,
  children,
  actions,
  height = 300,
}: ChartContainerProps) {
  return (
    <div
      style={{
        background: THEME.bgCard,
        borderRadius: "16px",
        border: `1px solid ${THEME.borderSubtle}`,
        overflow: "hidden",
      }}
    >
      {/* 头部 */}
      <div
        style={{
          padding: "16px 20px",
          borderBottom: `1px solid ${THEME.borderSubtle}`,
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
        }}
      >
        <div>
          <h4
            style={{
              margin: 0,
              fontSize: "15px",
              fontWeight: 600,
              color: THEME.textPrimary,
            }}
          >
            {title}
          </h4>
          {subtitle && (
            <p
              style={{
                margin: "4px 0 0",
                fontSize: "12px",
                color: THEME.textSecondary,
              }}
            >
              {subtitle}
            </p>
          )}
        </div>
        {actions && <div style={{ display: "flex", gap: "8px" }}>{actions}</div>}
      </div>

      {/* 图表区域 */}
      <div
        style={{
          padding: "16px",
          height: typeof height === "number" ? `${height}px` : height,
        }}
      >
        {children}
      </div>
    </div>
  );
});

// 图表类型切换按钮
export const ChartTypeButton = memo(function ChartTypeButton({
  active,
  onClick,
  icon,
  label,
}: {
  active: boolean;
  onClick: () => void;
  icon: ReactNode;
  label: string;
}) {
  return (
    <button
      onClick={onClick}
      title={label}
      style={{
        width: "32px",
        height: "32px",
        borderRadius: "8px",
        border: `1px solid ${active ? THEME.borderActive : THEME.borderSubtle}`,
        background: active ? THEME.bgCardHover : "transparent",
        color: active ? THEME.textBright : THEME.textMuted,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        cursor: "pointer",
        transition: "all 0.2s",
      }}
    >
      {icon}
    </button>
  );
});

// 时间范围选择器
export const TimeRangeSelector = memo(function TimeRangeSelector({
  value,
  onChange,
}: {
  value: string;
  onChange: (value: string) => void;
}) {
  const options = [
    { value: "all", label: "全部" },
    { value: "50", label: "50回合" },
    { value: "20", label: "20回合" },
    { value: "10", label: "10回合" },
  ];

  return (
    <div style={{ display: "flex", gap: "4px" }}>
      {options.map((opt) => (
        <button
          key={opt.value}
          onClick={() => onChange(opt.value)}
          style={{
            padding: "4px 10px",
            borderRadius: "6px",
            border: `1px solid ${value === opt.value ? THEME.borderActive : THEME.borderSubtle}`,
            background: value === opt.value ? THEME.bgCardHover : "transparent",
            color: value === opt.value ? THEME.textBright : THEME.textMuted,
            fontSize: "12px",
            cursor: "pointer",
            transition: "all 0.2s",
          }}
        >
          {opt.label}
        </button>
      ))}
    </div>
  );
});



