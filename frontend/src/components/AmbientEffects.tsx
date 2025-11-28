/**
 * 环境氛围效果组件
 * 包含扫描线、角落装饰、浮动粒子等视觉增强
 */

import { useEffect, useState, memo } from "react";

interface ParticleConfig {
  id: number;
  left: string;
  delay: string;
  duration: string;
  size: number;
  color: string;
}

// 生成随机粒子配置
function generateParticles(count: number): ParticleConfig[] {
  const colors = [
    "rgba(45, 212, 191, 0.6)",
    "rgba(34, 197, 94, 0.5)",
    "rgba(167, 139, 250, 0.4)",
  ];
  
  return Array.from({ length: count }, (_, i) => ({
    id: i,
    left: `${Math.random() * 100}%`,
    delay: `${Math.random() * 15}s`,
    duration: `${15 + Math.random() * 10}s`,
    size: 2 + Math.random() * 4,
    color: colors[Math.floor(Math.random() * colors.length)],
  }));
}

// 扫描线组件
export const Scanlines = memo(function Scanlines() {
  return <div className="scanlines" aria-hidden="true" />;
});

// 角落装饰组件
export const CornerDecorations = memo(function CornerDecorations() {
  return (
    <>
      <div className="corner-deco top-left" aria-hidden="true" />
      <div className="corner-deco top-right" aria-hidden="true" />
      <div className="corner-deco bottom-left" aria-hidden="true" />
      <div className="corner-deco bottom-right" aria-hidden="true" />
    </>
  );
});

// 浮动粒子组件
export const AmbientParticles = memo(function AmbientParticles({ count = 15 }: { count?: number }) {
  const [particles, setParticles] = useState<ParticleConfig[]>([]);

  useEffect(() => {
    setParticles(generateParticles(count));
  }, [count]);

  return (
    <div className="ambient-particles" aria-hidden="true">
      {particles.map((p) => (
        <div
          key={p.id}
          className="ambient-particle"
          style={{
            left: p.left,
            width: p.size,
            height: p.size,
            background: `radial-gradient(circle, ${p.color}, transparent)`,
            animationDelay: p.delay,
            animationDuration: p.duration,
          }}
        />
      ))}
    </div>
  );
});

// 全局光效组件
export const GlobalGlow = memo(function GlobalGlow() {
  return (
    <div className="global-glow" aria-hidden="true">
      <div className="glow-orb glow-orb-1" />
      <div className="glow-orb glow-orb-2" />
      <div className="glow-orb glow-orb-3" />
      <style>{`
        .global-glow {
          position: fixed;
          inset: 0;
          pointer-events: none;
          z-index: 0;
          overflow: hidden;
        }
        
        .glow-orb {
          position: absolute;
          border-radius: 50%;
          filter: blur(80px);
          opacity: 0.15;
        }
        
        .glow-orb-1 {
          top: 10%;
          left: 10%;
          width: 400px;
          height: 400px;
          background: radial-gradient(circle, rgba(45, 212, 191, 0.4), transparent 70%);
          animation: orb-drift 20s ease-in-out infinite;
        }
        
        .glow-orb-2 {
          bottom: 20%;
          right: 15%;
          width: 300px;
          height: 300px;
          background: radial-gradient(circle, rgba(34, 197, 94, 0.3), transparent 70%);
          animation: orb-drift 25s ease-in-out infinite reverse;
        }
        
        .glow-orb-3 {
          top: 50%;
          left: 50%;
          width: 500px;
          height: 500px;
          background: radial-gradient(circle, rgba(167, 139, 250, 0.2), transparent 70%);
          animation: orb-drift 30s ease-in-out infinite 10s;
        }
        
        @keyframes orb-drift {
          0%, 100% {
            transform: translate(0, 0) scale(1);
          }
          25% {
            transform: translate(50px, -30px) scale(1.1);
          }
          50% {
            transform: translate(20px, 40px) scale(0.9);
          }
          75% {
            transform: translate(-30px, 20px) scale(1.05);
          }
        }
      `}</style>
    </div>
  );
});

// 组合所有效果的主组件
interface AmbientEffectsProps {
  showScanlines?: boolean;
  showCorners?: boolean;
  showParticles?: boolean;
  showGlow?: boolean;
  particleCount?: number;
}

export function AmbientEffects({
  showScanlines = false, // 默认关闭扫描线，因为可能影响视觉
  showCorners = true,
  showParticles = true,
  showGlow = true,
  particleCount = 12,
}: AmbientEffectsProps) {
  return (
    <>
      {showGlow && <GlobalGlow />}
      {showParticles && <AmbientParticles count={particleCount} />}
      {showCorners && <CornerDecorations />}
      {showScanlines && <Scanlines />}
    </>
  );
}

export default AmbientEffects;

