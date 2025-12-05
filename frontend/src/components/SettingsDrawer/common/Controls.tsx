/**
 * Controls - 精美的表单控件组件
 * 单列布局，优雅的交互效果
 */

import { memo, type ReactNode, type ChangeEvent } from "react";

// ==================== SliderRow ====================
interface SliderRowProps {
  label: string;
  desc?: string;
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
  value,
  min,
  max,
  step = 0.01,
  onChange,
  formatValue = (v) => v.toFixed(2),
  disabled = false,
}: SliderRowProps) {
  return (
    <div className={`form-row ${disabled ? 'disabled' : ''}`}>
      <div className="form-label">
        <div className="form-label-text">{label}</div>
        {desc && <div className="form-label-desc">{desc}</div>}
      </div>
      <div className="form-control">
        <div className="slider-control">
          <input
            type="range"
            className="slider-track"
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
    </div>
  );
});

// ==================== ToggleRow ====================
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
    <div className={`form-row form-row-compact ${disabled ? 'disabled' : ''}`}>
      <div className="form-label">
        <div className="form-label-text">{label}</div>
        {desc && <div className="form-label-desc">{desc}</div>}
      </div>
      <div className="form-control">
        <label className="switch">
          <input
            type="checkbox"
            checked={checked}
            onChange={(e) => onChange(e.target.checked)}
            disabled={disabled}
          />
          <span className="switch-track">
            <span className="switch-thumb" />
          </span>
        </label>
      </div>
    </div>
  );
});

// ==================== NumberInput ====================
interface NumberInputProps {
  label: string;
  desc?: string;
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
    <div className={`form-row ${disabled ? 'disabled' : ''}`}>
      <div className="form-label">
        <div className="form-label-text">{label}</div>
        {desc && <div className="form-label-desc">{desc}</div>}
      </div>
      <div className="form-control">
        <div className="number-input">
          <input
            type="number"
            value={value}
            min={min}
            max={max}
            step={step}
            onChange={handleChange}
            disabled={disabled}
          />
          {suffix && <span className="number-input-suffix">{suffix}</span>}
        </div>
      </div>
    </div>
  );
});

// ==================== SelectRow ====================
interface SelectOption<T> {
  value: T;
  label: string;
}

interface SelectRowProps<T extends string | number> {
  label: string;
  desc?: string;
  value: T;
  options: SelectOption<T>[];
  onChange: (value: T) => void;
  disabled?: boolean;
  placeholder?: string;
}

export function SelectRow<T extends string | number>({
  label,
  desc,
  value,
  options,
  onChange,
  disabled = false,
  placeholder,
}: SelectRowProps<T>) {
  return (
    <div className={`form-row ${disabled ? 'disabled' : ''}`}>
      <div className="form-label">
        <div className="form-label-text">{label}</div>
        {desc && <div className="form-label-desc">{desc}</div>}
      </div>
      <div className="form-control">
        <div className="select-control">
          <select
            value={value}
            onChange={(e) => onChange(e.target.value as T)}
            disabled={disabled}
          >
            {placeholder && <option value="">{placeholder}</option>}
            {options.map((opt) => (
              <option key={String(opt.value)} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </select>
        </div>
      </div>
    </div>
  );
}

// ==================== Card ====================
interface CardProps {
  title: string;
  icon?: string;
  desc?: string;
  children: ReactNode;
  actions?: ReactNode;
}

export const Card = memo(function Card({
  title,
  icon,
  desc,
  children,
  actions,
}: CardProps) {
  return (
    <div className="card">
      <div className="card-header">
        <div className="card-title">
          {icon && <span className="card-title-icon">{icon}</span>}
          <span className="card-title-text">{title}</span>
        </div>
        {desc && <span className="card-title-desc">{desc}</span>}
        {actions}
      </div>
      <div className="card-body">{children}</div>
    </div>
  );
});

// ==================== SectionCard (alias for Card) ====================
export const SectionCard = Card;

// ==================== ConfigGroup ====================
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
      <div className="config-group-grid">{children}</div>
    </div>
  );
});

// ==================== ActionButton ====================
interface ActionButtonProps {
  label: string;
  onClick: () => void;
  variant?: "primary" | "secondary" | "danger" | "ghost";
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
  const btnClass = {
    primary: "btn btn-primary",
    secondary: "btn btn-outline",
    danger: "btn btn-outline danger",
    ghost: "btn btn-ghost",
  }[variant];

  return (
    <button
      className={btnClass}
      onClick={onClick}
      disabled={disabled || loading}
    >
      {loading ? (
        <span className="spinner" />
      ) : (
        icon && <span>{icon}</span>
      )}
      <span>{label}</span>
    </button>
  );
});

// ==================== InfoBox ====================
interface InfoBoxProps {
  variant?: "info" | "warning" | "success";
  icon?: string;
  title?: string;
  children: ReactNode;
}

export const InfoBox = memo(function InfoBox({
  variant = "info",
  icon,
  title,
  children,
}: InfoBoxProps) {
  const defaultIcon = {
    info: "💡",
    warning: "⚠️",
    success: "✅",
  }[variant];

  return (
    <div className={`info-box ${variant}`}>
      <span className="info-box-icon">{icon || defaultIcon}</span>
      <div className="info-box-content">
        {title && <h4>{title}</h4>}
        <div className="info-box-text">{children}</div>
      </div>
    </div>
  );
});

// ==================== FeatureGrid ====================
interface FeatureItem {
  icon: string;
  title: string;
  desc: string;
}

interface FeatureGridProps {
  items: FeatureItem[];
}

export const FeatureGrid = memo(function FeatureGrid({ items }: FeatureGridProps) {
  return (
    <div className="feature-grid">
      {items.map((item, idx) => (
        <div key={idx} className="feature-item">
          <span className="feature-item-icon">{item.icon}</span>
          <div className="feature-item-title">{item.title}</div>
          <div className="feature-item-desc">{item.desc}</div>
        </div>
      ))}
    </div>
  );
});

// ==================== SectionHeader ====================
interface SectionHeaderProps {
  icon: string;
  title: string;
  subtitle?: string;
  actions?: ReactNode;
}

export const SectionHeader = memo(function SectionHeader({
  icon,
  title,
  subtitle,
  actions,
}: SectionHeaderProps) {
  return (
    <div className="section-header">
      <div className="section-title-area">
        <div className="section-icon">{icon}</div>
        <div>
          <h2 className="section-title">{title}</h2>
          {subtitle && <p className="section-subtitle">{subtitle}</p>}
        </div>
      </div>
      {actions && <div className="section-actions">{actions}</div>}
    </div>
  );
});
