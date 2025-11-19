import React, { useEffect, useState } from 'react';
import { createPortal } from 'react-dom';

interface Props {
  title: React.ReactNode;
  children: React.ReactNode;
  onClose?: () => void;
  variant?: 'modal' | 'sidebar-left' | 'sidebar-right' | 'floating';
  width?: string;
  height?: string;
  className?: string;
  icon?: React.ReactNode;
}

export function GamePanel({ 
  title, 
  children, 
  onClose, 
  variant = 'modal', 
  width, 
  height,
  className = '',
  icon
}: Props) {
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
    return () => setMounted(false);
  }, []);

  // Base styles tailored for the "Evolutionary Blueprint" (Vic3-like structure, Sci-fi skin)
  const baseStyle: React.CSSProperties = {
    position: 'fixed',
    backgroundColor: 'rgba(15, 19, 30, 0.96)',
    backdropFilter: 'blur(16px)',
    border: '1px solid rgba(255, 255, 255, 0.12)',
    boxShadow: '0 20px 50px rgba(0,0,0,0.6)',
    color: '#e2ecff',
    display: 'flex',
    flexDirection: 'column',
    zIndex: 2000,
    transition: 'all 0.4s cubic-bezier(0.16, 1, 0.3, 1)', // Smooth mechanical ease
    opacity: mounted ? 1 : 0,
    overflow: 'hidden',
  };

  // Variant specific styles
  const variantStyles: Record<string, React.CSSProperties> = {
    modal: {
      top: '50%',
      left: '50%',
      transform: mounted ? 'translate(-50%, -50%) scale(1)' : 'translate(-50%, -45%) scale(0.95)',
      width: width || '800px',
      height: height || 'auto',
      maxHeight: '90vh',
      maxWidth: '95vw',
      borderRadius: '12px',
    },
    'sidebar-right': {
      top: '60px', // Assuming top bar height
      right: '0',
      bottom: '0',
      transform: mounted ? 'translateX(0)' : 'translateX(100%)',
      width: width || '400px',
      borderRight: 'none',
      borderTopLeftRadius: '12px',
      borderBottomLeftRadius: '12px',
      borderTop: '1px solid rgba(255, 255, 255, 0.12)',
      borderLeft: '1px solid rgba(255, 255, 255, 0.12)',
    },
    'sidebar-left': {
      top: '60px',
      left: '0',
      bottom: '0',
      transform: mounted ? 'translateX(0)' : 'translateX(-100%)',
      width: width || '400px',
      borderLeft: 'none',
      borderTopRightRadius: '12px',
      borderBottomRightRadius: '12px',
      borderTop: '1px solid rgba(255, 255, 255, 0.12)',
      borderRight: '1px solid rgba(255, 255, 255, 0.12)',
    },
    floating: {
      // Floating requires manual positioning or defaults to center-ish
      top: '100px',
      left: '100px',
      width: width || 'auto',
      height: height || 'auto',
      borderRadius: '8px',
      transform: mounted ? 'translateY(0)' : 'translateY(10px)',
    }
  };

  const finalStyle = { ...baseStyle, ...variantStyles[variant] };

  // Header Style
  const headerStyle: React.CSSProperties = {
    padding: '16px 24px',
    background: 'linear-gradient(90deg, rgba(255,255,255,0.03) 0%, rgba(255,255,255,0) 100%)',
    borderBottom: '1px solid rgba(255, 255, 255, 0.1)',
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    userSelect: 'none',
    flexShrink: 0,
  };

  const titleStyle: React.CSSProperties = {
    fontFamily: 'var(--font-display, serif)', // Use CSS var if available
    fontSize: '1.25rem',
    fontWeight: 700,
    letterSpacing: '0.02em',
    color: '#fff',
    display: 'flex',
    alignItems: 'center',
    gap: '12px',
    textShadow: '0 2px 4px rgba(0,0,0,0.5)',
  };

  const closeBtnStyle: React.CSSProperties = {
    background: 'transparent',
    border: 'none',
    color: 'rgba(255, 255, 255, 0.4)',
    cursor: 'pointer',
    padding: '8px',
    borderRadius: '50%',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    transition: 'all 0.2s',
  };

  return createPortal(
    <>
      {/* Backdrop for modals */}
      {variant === 'modal' && (
        <div 
          style={{
            position: 'fixed',
            inset: 0,
            background: 'rgba(0, 0, 0, 0.4)',
            backdropFilter: 'blur(4px)',
            zIndex: 1999,
            opacity: mounted ? 1 : 0,
            transition: 'opacity 0.4s ease',
          }}
          onClick={onClose}
        />
      )}
      
      <div style={finalStyle} className={className}>
        <div style={headerStyle}>
          <div style={titleStyle}>
            {icon && <span style={{ color: '#3b82f6', display: 'flex' }}>{icon}</span>}
            {title}
          </div>
          {onClose && (
            <button 
              onClick={onClose}
              style={closeBtnStyle}
              onMouseEnter={e => {
                e.currentTarget.style.color = '#fff';
                e.currentTarget.style.background = 'rgba(255,255,255,0.1)';
              }}
              onMouseLeave={e => {
                e.currentTarget.style.color = 'rgba(255, 255, 255, 0.4)';
                e.currentTarget.style.background = 'transparent';
              }}
            >
              <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M18 6L6 18M6 6l12 12" strokeLinecap="round" strokeLinejoin="round"/>
              </svg>
            </button>
          )}
        </div>
        
        <div style={{ 
          flex: 1, 
          overflow: 'auto', 
          position: 'relative',
          // Custom Scrollbar logic could go here via class
        }} className="custom-scrollbar">
          {children}
        </div>
      </div>
    </>,
    document.body
  );
}

