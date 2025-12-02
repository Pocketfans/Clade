/**
 * NavButton - 设置导航按钮
 */

import { memo } from "react";

interface NavButtonProps {
  isActive?: boolean;
  active?: boolean;
  onClick: () => void;
  icon: string;
  label: string;
  desc?: string;
}

export const NavButton = memo(function NavButton({
  isActive,
  active,
  onClick,
  icon,
  label,
  desc,
}: NavButtonProps) {
  const isCurrentActive = isActive ?? active ?? false;
  
  return (
    <button
      onClick={onClick}
      className={`nav-button ${isCurrentActive ? "active" : ""}`}
      aria-current={isCurrentActive ? "page" : undefined}
    >
      <span className="nav-icon">{icon}</span>
      <div className="nav-text">
        <div className="nav-label">{label}</div>
        {desc && <div className="nav-desc">{desc}</div>}
      </div>
    </button>
  );
});

