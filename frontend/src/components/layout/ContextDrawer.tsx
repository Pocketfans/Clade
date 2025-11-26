import { ReactNode } from "react";

interface Props {
  title?: string;
  onClose: () => void;
  children: ReactNode;
  noPadding?: boolean;
  hideHeader?: boolean;
}

export function ContextDrawer({ title, onClose, children, noPadding = false, hideHeader = false }: Props) {
  return (
    <div className="context-drawer">
      {!hideHeader && (
        <header className="drawer-header">
          <h2 className="drawer-title">{title}</h2>
          <button 
            onClick={onClose} 
            className="btn-icon btn-ghost btn-sm" 
            title="关闭面板"
            style={{ width: 28, height: 28, minHeight: 0 }} // Ensure small button
          >
            ✕
          </button>
        </header>
      )}
      <div className={`drawer-body ${noPadding ? 'no-padding' : 'padded'}`}>
        {children}
      </div>
    </div>
  );
}
