import type { ReactNode } from "react";

interface Props {
  title: string;
  onClose: () => void;
  children: ReactNode;
}

export function FullscreenOverlay({ title, onClose, children }: Props) {
  return (
    <div className="fullscreen-overlay">
      <div className="fullscreen-panel">
        <header className="flex justify-between items-center">
          <h2 className="text-2xl font-bold font-display">{title}</h2>
          <button 
            type="button" 
            onClick={onClose}
            className="btn-icon"
            aria-label="关闭"
          >
            ×
          </button>
        </header>
        <div className="fullscreen-body">{children}</div>
      </div>
    </div>
  );
}
