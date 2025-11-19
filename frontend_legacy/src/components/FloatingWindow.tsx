import type { ReactNode } from "react";

interface Props {
  title: string;
  anchor?: { x: number; y: number };
  inline?: boolean;
  onClose: () => void;
  children: ReactNode;
}

export function FloatingWindow({ title, anchor, inline = false, onClose, children }: Props) {
  const style = anchor
    ? {
        left: `${Math.max(anchor.x - 160, 16)}px`,
        top: `${Math.max(anchor.y - 40, 16)}px`,
      }
    : undefined;

  return (
    <div className={inline ? "floating-window inline" : "floating-window"} style={style}>
      <header className="floating-header">
        <h3 className="text-base font-semibold">{title}</h3>
        <button 
          type="button" 
          onClick={onClose} 
          className="btn-icon-sm"
          aria-label="关闭窗口"
        >
          ×
        </button>
      </header>
      <div className="floating-body">{children}</div>
    </div>
  );
}
