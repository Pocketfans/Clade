import { useState, useEffect } from "react";
import type { ViewMode } from "./MapViewSelector";

interface Props {
  viewMode: ViewMode;
  hasSelectedSpecies: boolean;
}

// 视图模式的详细说明
const MODE_INFO: Record<ViewMode, { 
  title: string; 
  icon: string; 
  description: string;
  tip?: string;
}> = {
  terrain: {
    title: "实景地图",
    icon: "🌍",
    description: "显示真实世界风格的地形、植被和覆盖物",
  },
  terrain_type: {
    title: "地形分类",
    icon: "🏔️",
    description: "按海拔分为35级地形类型",
    tip: "深色=海洋，绿色=平原，棕色=山地，白色=雪山",
  },
  elevation: {
    title: "海拔高度",
    icon: "📐",
    description: "显示相对于海平面的海拔高度",
    tip: "深蓝=深海，浅蓝=浅海，绿=低地，棕=高山",
  },
  biodiversity: {
    title: "生物热力图",
    icon: "🧬",
    description: "显示每个地块的物种数量分布",
    tip: "冷色=少，暖色=多 | 陆地暖色系，海洋蓝色系",
  },
  climate: {
    title: "温度分布",
    icon: "🌡️",
    description: "基于实际温度的连续渐变色阶",
    tip: "白/蓝=寒冷，绿=温和，黄/橙/红=炎热",
  },
  suitability: {
    title: "生存适宜度",
    icon: "🎯",
    description: "显示选中物种在各地块的生存适宜度",
    tip: "绿=适宜，黄=一般，红=不适宜，灰=未分布",
  },
};

export function MapModeToast({ viewMode, hasSelectedSpecies }: Props) {
  const [visible, setVisible] = useState(false);
  const [lastMode, setLastMode] = useState<ViewMode | null>(null);
  
  useEffect(() => {
    // 首次加载不显示提示
    if (lastMode === null) {
      setLastMode(viewMode);
      return;
    }
    
    // 模式改变时显示提示
    if (viewMode !== lastMode) {
      setLastMode(viewMode);
      setVisible(true);
      
      // 3秒后隐藏
      const timer = setTimeout(() => {
        setVisible(false);
      }, 3500);
      
      return () => clearTimeout(timer);
    }
  }, [viewMode, lastMode]);
  
  if (!visible) return null;
  
  const info = MODE_INFO[viewMode];
  const showWarning = viewMode === "suitability" && !hasSelectedSpecies;
  
  return (
    <div className={`map-mode-toast ${visible ? 'visible' : ''} ${showWarning ? 'warning' : ''}`}>
      <div className="toast-header">
        <span className="toast-icon">{info.icon}</span>
        <span className="toast-title">{info.title}</span>
      </div>
      <div className="toast-body">
        <p className="toast-desc">{info.description}</p>
        {info.tip && <p className="toast-tip">💡 {info.tip}</p>}
        {showWarning && (
          <p className="toast-warning">⚠️ 请先在物种列表中选择一个物种</p>
        )}
      </div>
      <div className="toast-progress" />
    </div>
  );
}



