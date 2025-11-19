import { useState } from "react";
import type { SpeciesDetail, SpeciesSnapshot } from "../services/api.types";
import { editSpecies } from "../services/api";

type SpeciesInfo = SpeciesSnapshot | SpeciesDetail;

interface Props {
  species?: SpeciesInfo | null;
  variant?: "panel" | "floating";
  onUpdate?: (updated: SpeciesDetail) => void;
}

function isSnapshot(species: SpeciesInfo): species is SpeciesSnapshot {
  return "population" in species;
}

const organCategoryMap: Record<string, string> = {
  metabolic: "代谢系统",
  locomotion: "运动系统",
  sensory: "感觉系统",
  digestive: "消化系统",
  defense: "防御系统",
  respiratory: "呼吸系统",
  nervous: "神经系统",
  circulatory: "循环系统",
  reproductive: "繁殖系统",
  excretory: "排泄系统",
};

const statusMap: Record<string, string> = {
  alive: "存活",
  extinct: "灭绝",
};

export function SpeciesDetailPanel({ species, variant = "panel", onUpdate }: Props) {
  const [isEditing, setIsEditing] = useState(false);
  const [editForm, setEditForm] = useState({
    description: "",
    morphology: "",
    traits: "",
  });
  const [isSaving, setIsSaving] = useState(false);

  if (!species) {
    return (
      <div className={variant === "panel" ? "species-detail panel" : "species-detail"}>
        选择一个物种查看详细信息。
      </div>
    );
  }

  const className = variant === "panel" ? "species-detail panel" : "species-detail";

  if (isSnapshot(species)) {
    return (
      <div className={className}>
        <h2>
          {species.latin_name} / {species.common_name}
        </h2>
        <div className="species-meta">
          <span>谱系：{species.lineage_code}</span>
          <span>数量：{species.population}</span>
          <span>死亡：{species.deaths}（{(species.death_rate * 100).toFixed(1)}%）</span>
        </div>
        <p>{species.ecological_role}</p>
      </div>
    );
  }

  function handleEdit() {
    if (!species || isSnapshot(species)) return;
    setEditForm({
      description: species.description || "",
      morphology: JSON.stringify(species.morphology_stats, null, 2),
      traits: JSON.stringify(species.abstract_traits, null, 2),
    });
    setIsEditing(true);
  }

  async function handleSave() {
    if (!species || isSnapshot(species)) return;
    setIsSaving(true);
    try {
      const updated = await editSpecies(species.lineage_code, {
        description: editForm.description,
        morphology: editForm.morphology,
        traits: editForm.traits,
      });
      if (onUpdate) {
        onUpdate(updated);
      }
      setIsEditing(false);
    } catch (error) {
      console.error("保存失败:", error);
      alert("保存物种信息失败");
    } finally {
      setIsSaving(false);
    }
  }

  function handleCancel() {
    setIsEditing(false);
  }

  if (isEditing) {
    return (
      <div className={className}>
        <h2>
          编辑：{species.latin_name} / {species.common_name}
        </h2>
        <div className="edit-form">
          <label>
            描述
            <textarea
              rows={4}
              value={editForm.description}
              onChange={(e) => setEditForm({ ...editForm, description: e.target.value })}
              placeholder="物种的详细描述..."
            />
          </label>
          <label>
            形态统计（JSON）
            <textarea
              rows={6}
              value={editForm.morphology}
              onChange={(e) => setEditForm({ ...editForm, morphology: e.target.value })}
              placeholder='{"size": 1.2, "speed": 0.8}'
            />
          </label>
          <label>
            抽象特征（JSON）
            <textarea
              rows={6}
              value={editForm.traits}
              onChange={(e) => setEditForm({ ...editForm, traits: e.target.value })}
              placeholder='{"aggression": 0.5}'
            />
          </label>
          <div className="edit-buttons">
            <button onClick={handleSave} disabled={isSaving} className="btn btn-primary">
              {isSaving ? "保存中..." : "保存"}
            </button>
            <button onClick={handleCancel} disabled={isSaving} className="btn btn-secondary">
              取消
            </button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className={className}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "start" }}>
        <h2>
          {species.latin_name} / {species.common_name}
        </h2>
        <button onClick={handleEdit} className="btn btn-secondary btn-sm">
          编辑
        </button>
      </div>
      <p>{species.description}</p>
      <div className="species-meta">
        <span>谱系：{species.lineage_code}</span>
        <span>状态：{statusMap[species.status] || species.status}</span>
        {species.genus_code && <span>属：{species.genus_code}</span>}
        {species.taxonomic_rank && species.taxonomic_rank !== "species" && (
          <span>分类等级：{species.taxonomic_rank === "subspecies" ? "亚种" : species.taxonomic_rank === "hybrid" ? "杂交种" : species.taxonomic_rank}</span>
        )}
        {species.trophic_level && <span>营养级：{species.trophic_level.toFixed(2)}</span>}
      </div>
      
      {/* 显示器官系统 */}
      {species.organs && Object.keys(species.organs).length > 0 && (
        <div className="species-section">
          <h3>器官系统</h3>
          <div className="organs-grid">
            {Object.entries(species.organs).map(([category, organ]: [string, any]) => (
              <div key={category} className="organ-card">
                <label>{organCategoryMap[category] || category}</label>
                <strong>{organ.type || "未知"}</strong>
                {organ.is_active === false && <span className="badge badge-inactive">未激活</span>}
                {organ.acquired_turn && <small>获得于回合{organ.acquired_turn}</small>}
              </div>
            ))}
          </div>
        </div>
      )}
      
      {/* 显示能力标签 */}
      {species.capabilities && species.capabilities.length > 0 && (
        <div className="species-section">
          <h3>能力</h3>
          <div className="capabilities-list">
            {species.capabilities.map((cap) => (
              <span key={cap} className="badge badge-capability">{cap}</span>
            ))}
          </div>
        </div>
      )}
      
      {/* 显示形态统计 */}
      <div className="species-section">
        <h3>形态统计</h3>
        <div className="species-stats-grid">
          {Object.entries(species.morphology_stats).map(([key, value]) => (
            <div key={key}>
              <label>{key}</label>
              <strong>{typeof value === 'number' ? value.toFixed(2) : value}</strong>
            </div>
          ))}
        </div>
      </div>
      
      {/* 显示环境适应属性 */}
      <div className="species-section">
        <h3>环境适应属性</h3>
        <div className="species-stats-grid">
          {Object.entries(species.abstract_traits).map(([key, value]) => (
            <div key={key}>
              <label>{key}</label>
              <strong>{typeof value === 'number' ? value.toFixed(1) : value}</strong>
            </div>
          ))}
        </div>
      </div>
      
      {/* 显示杂交信息 */}
      {species.hybrid_parent_codes && species.hybrid_parent_codes.length > 0 && (
        <div className="species-section">
          <h3>杂交信息</h3>
          <div className="hybrid-info">
            <div>
              <label>亲本物种</label>
              <span>{species.hybrid_parent_codes.join(", ")}</span>
            </div>
            <div>
              <label>可育性</label>
              <span>{species.hybrid_fertility != null ? (species.hybrid_fertility * 100).toFixed(0) : 0}%</span>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
