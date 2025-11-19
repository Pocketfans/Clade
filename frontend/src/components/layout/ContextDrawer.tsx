import { ReactNode } from "react";

interface Props {
  title: string;
  onClose: () => void;
  children: ReactNode;
}

export function ContextDrawer({ title, onClose, children }: Props) {
  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%" }}>
      <div style={{ 
        padding: "1rem", 
        borderBottom: "1px solid rgba(255,255,255,0.1)", 
        display: "flex", 
        justifyContent: "space-between", 
        alignItems: "center",
        background: "rgba(255,255,255,0.05)"
      }}>
        <h2 style={{ margin: 0, fontSize: "1.1rem" }}>{title}</h2>
        <button onClick={onClose} className="btn-icon" style={{ fontSize: "0.9rem" }} title="关闭面板">✕</button>
      </div>
      <div style={{ flex: 1, overflowY: "auto", padding: "1rem" }}>
        {children}
      </div>
    </div>
  );
}


