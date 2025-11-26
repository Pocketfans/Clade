import { ReactNode } from "react";

interface Props {
  mapLayer: ReactNode;
  topBar: ReactNode;
  outliner: ReactNode;
  lensBar: ReactNode;
  drawer: ReactNode; // This is now the Right Sidebar
  modals?: ReactNode; // Fullscreen modals like genealogy
  alerts?: ReactNode; // Floating alerts
  outlinerCollapsed?: boolean; // 新增 prop
}

export function GameLayout({ 
  mapLayer, 
  topBar, 
  outliner, 
  lensBar, 
  drawer, 
  modals,
  alerts,
  outlinerCollapsed = false
}: Props) {
  return (
    <div className="game-layout">
      {/* 底层：地图 */}
      <div className="world-layer">{mapLayer}</div>
      
      {/* 交互层：HUD */}
      <div className="hud-layer">
        
        {/* 顶部栏：资源与时间 */}
        <div className="hud-top">{topBar}</div>
        
        {/* 中间区域：分为左、中、右 */}
        <div className="hud-middle">
          {/* 左侧大纲：物种列表等 */}
          <div className={`hud-left ${outlinerCollapsed ? 'collapsed' : ''}`}>
            {outliner && <div className="outliner-container">{outliner}</div>}
          </div>
          
          {/* 中央：地图交互区，顶部可能有警报 */}
          <div className="hud-center">
             {alerts && <div className="alerts-container">{alerts}</div>}
          </div>
          
          {/* 右侧详情抽屉：替代原来的漂浮窗 */}
          <div className="hud-right">
            {drawer && <div className="drawer-content">{drawer}</div>}
          </div>
        </div>
        
        {/* 底部透镜栏：视图切换与主要操作 */}
        <div className="hud-bottom">{lensBar}</div>
      </div>
      
      {/* 顶层模态窗 */}
      {modals && <div className="modal-layer">{modals}</div>}
    </div>
  );
}


