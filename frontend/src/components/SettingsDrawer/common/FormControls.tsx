/**
 * FormControls - 通用表单控件
 * 
 * 可复用于各种配置面板
 */

import { memo, type ReactNode, type ChangeEvent } from "react";
import { Tooltip } from "../../common/Tooltip";

// ============ ToggleRow - 开关行 ============

interface ToggleRowProps {
  label: string;
  desc?: string;
  checked: boolean;
  onChange: (checked: boolean) => void;
  disabled?: boolean;
}

export const ToggleRow = memo(function ToggleRow({
  label,
  desc,
  checked,
  onChange,
  disabled = false,
}: ToggleRowProps) {
  return (
    <div className="toggle-row">
      <div className="toggle-info">
        <span className="toggle-label">{label}</span>
        {desc && <span className="toggle-desc">{desc}</span>}
      </div>
      <label className="toggle-switch">
        <input
          type="checkbox"
          checked={checked}
          onChange={(e) => onChange(e.target.checked)}
          disabled={disabled}
        />
        <span className="toggle-slider" />
      </label>
    </div>
  );
});

// ============ SliderRow - 滑块行 ============

interface SliderRowProps {
  label: string;
  desc?: string;
  tooltip?: string;
  value: number;
  min: number;
  max: number;
  step?: number;
  onChange: (value: number) => void;
  formatValue?: (value: number) => string;
  disabled?: boolean;
}

export const SliderRow = memo(function SliderRow({
  label,
  desc,
  tooltip,
  value,
  min,
  max,
  step = 0.01,
  onChange,
  formatValue = (v) => v.toFixed(2),
  disabled = false,
}: SliderRowProps) {
  const labelContent = (
    <span className="slider-label">
      {label}
      {tooltip && <Tooltip content={tooltip}><span className="tooltip-trigger">ⓘ</span></Tooltip>}
    </span>
  );

  return (
    <div className="slider-row">
      <div className="slider-info">
        {labelContent}
        {desc && <span className="slider-desc">{desc}</span>}
      </div>
      <div className="slider-control">
        <input
          type="range"
          min={min}
          max={max}
          step={step}
          value={value}
          onChange={(e) => onChange(parseFloat(e.target.value))}
          disabled={disabled}
        />
        <span className="slider-value">{formatValue(value)}</span>
      </div>
    </div>
  );
});

// ============ NumberInput - 数字输入 ============

interface NumberInputProps {
  label: string;
  desc?: string;
  tooltip?: string;
  value: number;
  min?: number;
  max?: number;
  step?: number;
  onChange: (value: number) => void;
  disabled?: boolean;
  suffix?: string;
}

export const NumberInput = memo(function NumberInput({
  label,
  desc,
  tooltip,
  value,
  min,
  max,
  step = 1,
  onChange,
  disabled = false,
  suffix,
}: NumberInputProps) {
  const handleChange = (e: ChangeEvent<HTMLInputElement>) => {
    const val = parseFloat(e.target.value);
    if (!isNaN(val)) {
      onChange(val);
    }
  };

  return (
    <div className="input-row">
      <div className="input-info">
        <span className="input-label">
          {label}
          {tooltip && <Tooltip content={tooltip}><span className="tooltip-trigger">ⓘ</span></Tooltip>}
        </span>
        {desc && <span className="input-desc">{desc}</span>}
      </div>
      <div className="input-control">
        <input
          type="number"
          value={value}
          min={min}
          max={max}
          step={step}
          onChange={handleChange}
          disabled={disabled}
        />
        {suffix && <span className="input-suffix">{suffix}</span>}
      </div>
    </div>
  );
});

// ============ SelectRow - 下拉选择行 ============

interface SelectOption<T> {
  value: T;
  label: string;
  desc?: string;
}

interface SelectRowProps<T extends string | number> {
  label: string;
  desc?: string;
  value: T;
  options: SelectOption<T>[];
  onChange: (value: T) => void;
  disabled?: boolean;
}

export function SelectRow<T extends string | number>({
  label,
  desc,
  value,
  options,
  onChange,
  disabled = false,
}: SelectRowProps<T>) {
  return (
    <div className="select-row">
      <div className="select-info">
        <span className="select-label">{label}</span>
        {desc && <span className="select-desc">{desc}</span>}
      </div>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value as T)}
        disabled={disabled}
      >
        {options.map((opt) => (
          <option key={opt.value} value={opt.value}>
            {opt.label}
          </option>
        ))}
      </select>
    </div>
  );
}

// ============ TextInput - 文本输入 ============

interface TextInputProps {
  label: string;
  desc?: string;
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  disabled?: boolean;
  type?: "text" | "password" | "url";
}

export const TextInput = memo(function TextInput({
  label,
  desc,
  value,
  onChange,
  placeholder,
  disabled = false,
  type = "text",
}: TextInputProps) {
  return (
    <div className="input-row">
      <div className="input-info">
        <span className="input-label">{label}</span>
        {desc && <span className="input-desc">{desc}</span>}
      </div>
      <input
        type={type}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        disabled={disabled}
      />
    </div>
  );
});

// ============ SectionCard - 配置区块卡片 ============

interface SectionCardProps {
  title: string;
  icon?: string;
  desc?: string;
  children: ReactNode;
  actions?: ReactNode;
  collapsible?: boolean;
  defaultCollapsed?: boolean;
}

export const SectionCard = memo(function SectionCard({
  title,
  icon,
  desc,
  children,
  actions,
  collapsible = false,
  defaultCollapsed = false,
}: SectionCardProps) {
  // TODO: 实现可折叠功能
  return (
    <div className="section-card">
      <div className="section-header">
        <div className="section-title">
          {icon && <span className="section-icon">{icon}</span>}
          <span>{title}</span>
        </div>
        {desc && <div className="section-desc">{desc}</div>}
        {actions && <div className="section-actions">{actions}</div>}
      </div>
      <div className="section-content">{children}</div>
    </div>
  );
});

// ============ ConfigGroup - 配置分组 ============

interface ConfigGroupProps {
  title: string;
  children: ReactNode;
}

export const ConfigGroup = memo(function ConfigGroup({
  title,
  children,
}: ConfigGroupProps) {
  return (
    <div className="config-group">
      <div className="config-group-title">{title}</div>
      <div className="config-group-content">{children}</div>
    </div>
  );
});

// ============ ActionButton - 操作按钮 ============

interface ActionButtonProps {
  label: string;
  onClick: () => void;
  variant?: "primary" | "secondary" | "danger";
  icon?: string;
  disabled?: boolean;
  loading?: boolean;
}

export const ActionButton = memo(function ActionButton({
  label,
  onClick,
  variant = "secondary",
  icon,
  disabled = false,
  loading = false,
}: ActionButtonProps) {
  return (
    <button
      className={`action-button ${variant}`}
      onClick={onClick}
      disabled={disabled || loading}
    >
      {loading ? (
        <span className="spinner" style={{ width: 16, height: 16 }} />
      ) : (
        icon && <span className="button-icon">{icon}</span>
      )}
      <span>{label}</span>
    </button>
  );
});

