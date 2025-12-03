import React from "react";
import { SpeciesDetail } from "@/services/api.types";

interface Props {
  species: SpeciesDetail;
}

const organIcons: Record<string, string> = {
  // 动物器官
  metabolic: "⚡",
  locomotion: "🦶",
  sensory: "👁️",
  digestive: "🍽️",
  defense: "🛡️",
  respiratory: "🫁",
  nervous: "🧠",
  circulatory: "❤️",
  reproductive: "🥚",
  excretory: "🚽",
  // 植物器官
  photosynthetic: "🌿",
  root_system: "🌱",
  stem: "🌾",
  protection: "🛡️",
  vascular: "🔗",
  storage: "📦",
};

const organLabels: Record<string, string> = {
  // 动物器官
  metabolic: "代谢系统",
  locomotion: "运动系统",
  sensory: "感官系统",
  digestive: "消化系统",
  defense: "防御系统",
  respiratory: "呼吸系统",
  nervous: "神经系统",
  circulatory: "循环系统",
  reproductive: "繁殖系统",
  excretory: "排泄系统",
  // 植物器官
  photosynthetic: "光合器官",
  root_system: "根系",
  stem: "茎",
  protection: "保护结构",
  vascular: "维管系统",
  storage: "储存器官",
};

// 动物器官类别
const animalOrganKeys = ["metabolic", "locomotion", "sensory", "digestive", "defense", "respiratory", "nervous", "circulatory", "reproductive", "excretory"];
// 植物器官类别
const plantOrganKeys = ["photosynthetic", "root_system", "stem", "protection", "vascular", "storage", "reproductive"];

export function OrganismBlueprint({ species }: Props) {
  // 整理器官数据（过滤内部字段）
  const organs = species.organs || {};
  const filteredOrgans = Object.fromEntries(
    Object.entries(organs).filter(([k]) => !k.startsWith("_"))
  );

  // 判断是否为植物（生产者或营养级=1）
  const isPlant = species.ecological_role === "producer" || (species.trophic_level && species.trophic_level <= 1.0);
  
  // 选择对应的器官类别
  const relevantOrganKeys = isPlant ? plantOrganKeys : animalOrganKeys;

  // 整理能力标签
  const capabilities = species.capabilities || [];

  return (
    <div className="blueprint-container">
      {/* 顶部：核心画像与基础属性 */}
      <div className="blueprint-header">
        <div className="blueprint-avatar">
          <div className="avatar-placeholder">
            {species.latin_name.substring(0, 2).toUpperCase()}
          </div>
          <div className="trophic-badge" title="营养级">
            T{species.trophic_level?.toFixed(1) || "1.0"}
          </div>
        </div>
        <div className="blueprint-stats">
          <div className="stat-row">
            <span className="stat-label">体型 (Size)</span>
            <div className="stat-bar">
              <div 
                className="stat-fill" 
                style={{ width: `${Math.min((species.morphology_stats.size || 0) * 10, 100)}%` }} 
              />
            </div>
            <span className="stat-value">{species.morphology_stats.size?.toFixed(2) || "-"}</span>
          </div>
          <div className="stat-row">
            <span className="stat-label">代谢 (Metabolism)</span>
            <div className="stat-bar">
              <div 
                className="stat-fill" 
                style={{ width: `${Math.min((species.morphology_stats.metabolism || 0) * 10, 100)}%`, background: "#ff9800" }} 
              />
            </div>
            <span className="stat-value">{species.morphology_stats.metabolism?.toFixed(2) || "-"}</span>
          </div>
          <div className="stat-row">
            <span className="stat-label">适应性 (Adaptability)</span>
            <div className="stat-bar">
              <div 
                className="stat-fill" 
                style={{ width: `${Math.min(((species.abstract_traits.adaptability || 0) / 15) * 100, 100)}%`, background: "#2196f3" }} 
              />
            </div>
            <span className="stat-value">{species.abstract_traits.adaptability?.toFixed(1) || "-"}</span>
          </div>
        </div>
      </div>

      {/* 中部：解剖结构 (Organ Systems) */}
      <div className="blueprint-section">
        <h4 className="section-title">解剖结构 (Anatomy) {isPlant ? "🌿" : "🦴"}</h4>
        <div className="organs-grid-visual">
          {relevantOrganKeys.map((key) => {
            const organ = filteredOrgans[key];
            const label = organLabels[key] || key;
            const isActive = organ?.is_active !== false;
            
            return (
              <div key={key} className={`organ-slot ${organ ? "filled" : "empty"} ${!isActive ? "inactive" : ""}`}>
                <div className="organ-icon">{organIcons[key] || "📦"}</div>
                <div className="organ-info">
                  <div className="organ-name">{organ ? organ.type : "未演化"}</div>
                  <div className="organ-category">{label}</div>
                  {organ && organ.efficiency && (
                    <div className="organ-stat">效率: {organ.efficiency}</div>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* 底部：基因特性 (Traits & Capabilities) */}
      <div className="blueprint-section">
        <h4 className="section-title">基因特性 (Genome)</h4>
        <div className="traits-container">
          {capabilities.map((cap) => (
            <span key={cap} className="trait-tag capability">
              ★ {cap}
            </span>
          ))}
          {Object.entries(species.abstract_traits).map(([key, val]) => {
            if (key === "adaptability") return null; // 已在顶部显示
            return (
              <span key={key} className="trait-tag abstract">
                {key}: {val}
              </span>
            );
          })}
        </div>
      </div>
      
      <style>{`
        .blueprint-container {
          background: rgba(0, 0, 0, 0.2);
          border-radius: 8px;
          padding: 16px;
          margin-top: 16px;
          border: 1px solid rgba(255, 255, 255, 0.05);
        }
        
        .blueprint-header {
          display: flex;
          gap: 20px;
          margin-bottom: 24px;
        }
        
        .blueprint-avatar {
          width: 80px;
          height: 80px;
          background: linear-gradient(135deg, #334, #112);
          border-radius: 12px;
          display: flex;
          align-items: center;
          justify-content: center;
          position: relative;
          border: 2px solid rgba(255, 255, 255, 0.1);
        }
        
        .avatar-placeholder {
          font-size: 2rem;
          font-weight: bold;
          color: rgba(255, 255, 255, 0.2);
        }
        
        .trophic-badge {
          position: absolute;
          bottom: -8px;
          right: -8px;
          background: #445;
          color: #fff;
          font-size: 0.7rem;
          padding: 2px 6px;
          border-radius: 4px;
          border: 1px solid rgba(255, 255, 255, 0.2);
        }
        
        .blueprint-stats {
          flex: 1;
          display: flex;
          flex-direction: column;
          justify-content: center;
          gap: 8px;
        }
        
        .stat-row {
          display: flex;
          align-items: center;
          gap: 12px;
          font-size: 0.85rem;
        }
        
        .stat-label {
          width: 100px;
          color: #889;
        }
        
        .stat-bar {
          flex: 1;
          height: 6px;
          background: rgba(255, 255, 255, 0.1);
          border-radius: 3px;
          overflow: hidden;
        }
        
        .stat-fill {
          height: 100%;
          background: #4caf50;
          border-radius: 3px;
        }
        
        .stat-value {
          width: 40px;
          text-align: right;
          font-family: monospace;
          color: #ccc;
        }
        
        .section-title {
          margin: 0 0 12px 0;
          font-size: 0.9rem;
          color: #889;
          text-transform: uppercase;
          letter-spacing: 1px;
          border-bottom: 1px solid rgba(255, 255, 255, 0.1);
          padding-bottom: 4px;
        }
        
        .blueprint-section {
          margin-bottom: 24px;
        }
        
        .organs-grid-visual {
          display: grid;
          grid-template-columns: repeat(auto-fill, minmax(140px, 1fr));
          gap: 12px;
        }
        
        .organ-slot {
          background: rgba(255, 255, 255, 0.03);
          border: 1px solid rgba(255, 255, 255, 0.05);
          border-radius: 6px;
          padding: 10px;
          display: flex;
          align-items: center;
          gap: 10px;
          transition: all 0.2s;
        }
        
        .organ-slot.filled {
          background: rgba(255, 255, 255, 0.08);
          border-color: rgba(255, 255, 255, 0.15);
        }
        
        .organ-slot.filled:hover {
          background: rgba(255, 255, 255, 0.12);
          transform: translateY(-2px);
        }
        
        .organ-slot.inactive {
          opacity: 0.5;
          filter: grayscale(1);
        }
        
        .organ-icon {
          font-size: 1.5rem;
        }
        
        .organ-info {
          flex: 1;
          overflow: hidden;
        }
        
        .organ-name {
          font-size: 0.85rem;
          font-weight: 600;
          color: #eef;
          white-space: nowrap;
          overflow: hidden;
          text-overflow: ellipsis;
        }
        
        .organ-category {
          font-size: 0.7rem;
          color: #889;
        }
        
        .organ-stat {
          font-size: 0.7rem;
          color: #4caf50;
          margin-top: 2px;
        }
        
        .traits-container {
          display: flex;
          flex-wrap: wrap;
          gap: 8px;
        }
        
        .trait-tag {
          padding: 4px 10px;
          border-radius: 12px;
          font-size: 0.8rem;
          border: 1px solid transparent;
        }
        
        .trait-tag.capability {
          background: rgba(156, 39, 176, 0.15);
          color: #e1bee7;
          border-color: rgba(156, 39, 176, 0.3);
        }
        
        .trait-tag.abstract {
          background: rgba(33, 150, 243, 0.15);
          color: #bbdefb;
          border-color: rgba(33, 150, 243, 0.3);
        }
      `}</style>
    </div>
  );
}

