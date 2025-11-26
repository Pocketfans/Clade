import { useState } from "react";
import { 
  ResponsiveContainer, RadarChart, PolarGrid, 
  PolarAngleAxis, PolarRadiusAxis, Radar, Tooltip
} from "recharts";
import { 
  Activity, 
  Dna, 
  Edit2, 
  Save, 
  X, 
  GitMerge, 
  GitBranch, 
  Info, 
  Eye,
  Zap,
  Crosshair
} from "lucide-react";

import type { SpeciesDetail, SpeciesSnapshot } from "../services/api.types";
import { editSpecies } from "../services/api";
import { OrganismBlueprint } from "./OrganismBlueprint";

type SpeciesInfo = SpeciesSnapshot | SpeciesDetail;

interface Props {
  species?: SpeciesInfo | null;
  variant?: "panel" | "floating";
  onUpdate?: (updated: SpeciesDetail) => void;
}

function isSnapshot(species: SpeciesInfo): species is SpeciesSnapshot {
  return "population" in species;
}

const statusMap: Record<string, string> = {
  alive: "存活",
  extinct: "灭绝",
};

export function SpeciesDetailPanel({ species, variant = "panel", onUpdate }: Props) {
  const [isEditing, setIsEditing] = useState(false);
  const [activeTab, setActiveTab] = useState<"overview" | "traits" | "organs" | "lineage">("overview");
  const [editForm, setEditForm] = useState({
    description: "",
    morphology: "",
    traits: "",
  });
  const [isSaving, setIsSaving] = useState(false);

  if (!species) {
    return (
      <div className="h-full flex flex-col items-center justify-center text-muted p-xl text-center">
        <Info size={48} className="mb-md opacity-20" />
        <p>选择一个物种查看详细信息</p>
      </div>
    );
  }

  const className = `h-full flex flex-col ${variant === "panel" ? "bg-transparent" : "glass-card"}`;

  // 简略视图 (Snapshot)
  if (isSnapshot(species)) {
    return (
      <div className={className}>
        <header className="mb-lg border-b border-white/10 pb-md">
          <h2 className="text-xl font-display mb-1">{species.common_name}</h2>
          <div className="text-sm text-muted font-mono mb-2">{species.latin_name}</div>
          <div className="flex gap-2 flex-wrap">
            <span className="badge badge-primary">{species.ecological_role}</span>
            <span className={`badge ${species.status === 'alive' ? 'badge-success' : 'badge-danger'}`}>
              {statusMap[species.status] || species.status}
            </span>
          </div>
        </header>

        <div className="grid grid-cols-2 gap-4 mb-lg">
          <div className="p-md rounded bg-white/5">
            <div className="text-xs text-muted uppercase tracking-wider mb-1">种群规模</div>
            <div className="text-xl font-mono font-bold">{species.population.toLocaleString()}</div>
          </div>
          <div className="p-md rounded bg-white/5">
            <div className="text-xs text-muted uppercase tracking-wider mb-1">死亡率</div>
            <div className="text-xl font-mono font-bold">{(species.death_rate * 100).toFixed(1)}%</div>
          </div>
        </div>

        <div className="bg-white/5 rounded p-md mb-lg">
           <div className="text-xs text-muted uppercase tracking-wider mb-2">近期动态</div>
           <ul className="text-sm space-y-1 pl-4 list-disc opacity-80">
             {species.notes.map((note, i) => (
               <li key={i}>{note}</li>
             ))}
           </ul>
        </div>
      </div>
    );
  }

  // 详细视图 (Detail)

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

  // 准备雷达图数据（形态数据用1作为满值，抽象特质用15作为满值）
  const chartData = [
    ...Object.entries(species.morphology_stats || {}).map(([k, v]) => ({ subject: k, A: v, fullMark: 1 })),
    ...Object.entries(species.abstract_traits || {}).map(([k, v]) => ({ subject: k, A: v, fullMark: 15 }))
  ].slice(0, 6); // 限制显示数量防止拥挤

  if (isEditing) {
    return (
      <div className={className}>
        <header className="flex justify-between items-center mb-lg border-b border-white/10 pb-md">
          <h2 className="text-lg font-bold">编辑物种数据</h2>
          <button onClick={() => setIsEditing(false)} className="btn-icon-sm rounded-full hover:bg-white/10">
            <X size={16} />
          </button>
        </header>
        
        <div className="flex-1 overflow-y-auto space-y-4 pr-2 custom-scrollbar">
          <div className="form-field">
            <label className="field-label">物种描述</label>
            <textarea
              rows={5}
              value={editForm.description}
              onChange={(e) => setEditForm({ ...editForm, description: e.target.value })}
              className="input-visual resize-y text-sm"
            />
          </div>
          <div className="form-field">
            <label className="field-label flex justify-between">
              <span>形态参数 (JSON)</span>
              <span className="text-xs text-warning">高级</span>
            </label>
            <textarea
              rows={6}
              value={editForm.morphology}
              onChange={(e) => setEditForm({ ...editForm, morphology: e.target.value })}
              className="input-visual font-mono text-xs"
            />
          </div>
          <div className="form-field">
            <label className="field-label flex justify-between">
              <span>抽象特征 (JSON)</span>
              <span className="text-xs text-warning">高级</span>
            </label>
            <textarea
              rows={6}
              value={editForm.traits}
              onChange={(e) => setEditForm({ ...editForm, traits: e.target.value })}
              className="input-visual font-mono text-xs"
            />
          </div>
        </div>

        <div className="mt-lg pt-md border-t border-white/10 flex gap-2 justify-end">
          <button onClick={() => setIsEditing(false)} className="btn btn-ghost text-sm">取消</button>
          <button onClick={handleSave} disabled={isSaving} className="btn btn-primary text-sm">
            {isSaving ? <span className="spinner mr-1" /> : <Save size={14} className="mr-1" />}
            保存更改
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className={className}>
      {/* 头部信息 */}
      <header className="mb-lg relative">
        <div className="absolute top-0 right-0">
          <button onClick={handleEdit} className="btn-icon-sm hover:bg-white/10 rounded text-muted hover:text-white" title="编辑数据">
            <Edit2 size={14} />
          </button>
        </div>
        <h2 className="text-2xl font-display font-bold mb-1 bg-clip-text text-transparent bg-gradient-to-r from-white to-white/70">
          {species.common_name}
        </h2>
        <div className="flex items-center gap-2 text-sm text-muted font-mono mb-3">
          <span>{species.latin_name}</span>
          <span className="w-1 h-1 rounded-full bg-white/20"></span>
          <span>{species.lineage_code}</span>
        </div>
        
        <div className="flex gap-2 flex-wrap">
          <span className={`badge ${species.status === 'alive' ? 'badge-success' : 'badge-danger'}`}>
            {statusMap[species.status] || species.status}
          </span>
          {species.genus_code && <span className="badge badge-secondary font-mono">{species.genus_code}</span>}
          {species.taxonomic_rank && species.taxonomic_rank !== "species" && (
            <span className="badge badge-info">
              {species.taxonomic_rank === "subspecies" ? "亚种" : species.taxonomic_rank === "hybrid" ? "杂交种" : species.taxonomic_rank}
            </span>
          )}
        </div>
      </header>

      {/* 标签页导航 */}
      <div className="flex gap-1 border-b border-white/10 mb-4 overflow-x-auto no-scrollbar">
        <button 
          className={`px-4 py-2 text-sm font-medium border-b-2 transition-colors whitespace-nowrap ${activeTab === 'overview' ? 'border-primary text-white' : 'border-transparent text-muted hover:text-white/80'}`}
          onClick={() => setActiveTab('overview')}
        >
          总览
        </button>
        <button 
          className={`px-4 py-2 text-sm font-medium border-b-2 transition-colors whitespace-nowrap ${activeTab === 'traits' ? 'border-primary text-white' : 'border-transparent text-muted hover:text-white/80'}`}
          onClick={() => setActiveTab('traits')}
        >
          特征分析
        </button>
        <button 
          className={`px-4 py-2 text-sm font-medium border-b-2 transition-colors whitespace-nowrap ${activeTab === 'organs' ? 'border-primary text-white' : 'border-transparent text-muted hover:text-white/80'}`}
          onClick={() => setActiveTab('organs')}
        >
          生理蓝图
        </button>
        {(species.hybrid_parent_codes?.length || species.parent_code) && (
          <button 
            className={`px-4 py-2 text-sm font-medium border-b-2 transition-colors whitespace-nowrap ${activeTab === 'lineage' ? 'border-primary text-white' : 'border-transparent text-muted hover:text-white/80'}`}
            onClick={() => setActiveTab('lineage')}
          >
            血统
          </button>
        )}
      </div>

      {/* 内容区域 */}
      <div className="flex-1 overflow-y-auto pr-2 custom-scrollbar">
        
        {/* 1. 总览标签 */}
        {activeTab === 'overview' && (
          <div className="space-y-6 fade-in">
            <div className="text-sm leading-relaxed text-white/80 bg-white/5 p-4 rounded-lg border border-white/5">
              {species.description || "暂无详细描述。"}
            </div>

            <div className="grid grid-cols-2 gap-3">
              {Object.entries(species.morphology_stats || {}).slice(0, 4).map(([key, value]) => (
                <div key={key} className="bg-white/5 p-3 rounded border border-white/5 flex flex-col">
                   <span className="text-xs text-muted uppercase mb-1">{key}</span>
                   <div className="flex items-end gap-2">
                     <span className="text-lg font-mono font-bold">{typeof value === 'number' ? value.toFixed(2) : value}</span>
                     <div className="flex-1 h-1 bg-white/10 rounded-full mb-1.5 overflow-hidden">
                       <div className="h-full bg-primary" style={{ width: `${Math.min(Math.max((value as number) * 100, 0), 100)}%` }}></div>
                     </div>
                   </div>
                </div>
              ))}
            </div>

            {species.capabilities && species.capabilities.length > 0 && (
              <div>
                <h3 className="text-sm font-medium text-muted mb-3 flex items-center gap-2">
                  <Zap size={14} /> 特殊能力
                </h3>
                <div className="flex flex-wrap gap-2">
                  {species.capabilities.map(cap => (
                    <span key={cap} className="badge badge-capability text-xs flex items-center gap-1">
                      <Zap size={10} fill="currentColor" /> {cap}
                    </span>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}

        {/* 2. 特征分析标签 */}
        {activeTab === 'traits' && (
          <div className="fade-in h-full flex flex-col">
             <div className="flex-shrink-0 h-[250px] w-full mb-6 -ml-4">
               <ResponsiveContainer width="100%" height="100%">
                 <RadarChart cx="50%" cy="50%" outerRadius="70%" data={chartData}>
                   <PolarGrid stroke="rgba(255,255,255,0.1)" />
                   <PolarAngleAxis dataKey="subject" tick={{ fill: 'rgba(255,255,255,0.5)', fontSize: 10 }} />
                   <PolarRadiusAxis angle={30} domain={[0, 1]} tick={false} axisLine={false} />
                   <Radar
                     name="Stats"
                     dataKey="A"
                     stroke="#3b82f6"
                     fill="#3b82f6"
                     fillOpacity={0.3}
                   />
                   <Tooltip 
                     contentStyle={{ backgroundColor: '#0f1329', borderColor: 'rgba(255,255,255,0.1)', color: '#fff' }}
                     itemStyle={{ color: '#3b82f6' }}
                   />
                 </RadarChart>
               </ResponsiveContainer>
             </div>

             <div className="space-y-4">
               <h3 className="text-sm font-medium text-muted border-b border-white/10 pb-2">抽象特质 <span className="text-xs opacity-60">(最高15)</span></h3>
               <div className="grid grid-cols-1 gap-3">
                 {Object.entries(species.abstract_traits || {}).map(([key, value]) => {
                   const percent = Math.min((value / 15) * 100, 100);
                   // 颜色：>10 高(警告色), <5 低(信息色), 5-10 中等(成功色)
                   const colorClass = value > 10 ? 'bg-warning' : value < 5 ? 'bg-info' : 'bg-success';
                   return (
                     <div key={key} className="flex items-center gap-3 text-sm">
                       <span className="w-24 text-muted truncate" title={key}>{key}</span>
                       <div className="flex-1 h-2 bg-white/10 rounded-full overflow-hidden">
                         <div 
                           className={`h-full rounded-full ${colorClass}`} 
                           style={{ width: `${percent}%` }} 
                         />
                       </div>
                       <span className="w-8 text-right font-mono text-xs">{value.toFixed(2)}</span>
                     </div>
                   );
                 })}
               </div>
             </div>
          </div>
        )}

        {/* 3. 生理蓝图标签 */}
        {activeTab === 'organs' && (
          <div className="fade-in">
            <div className="mb-4 text-sm text-muted flex items-center gap-2 bg-blue-500/10 p-3 rounded border border-blue-500/20">
              <Eye size={16} className="text-blue-400" />
              <span>可视化的器官系统与生理结构</span>
            </div>
            <OrganismBlueprint species={species} />
          </div>
        )}

        {/* 4. 血统标签 */}
        {activeTab === 'lineage' && (
          <div className="fade-in space-y-6">
            {species.parent_code && (
              <div className="bg-white/5 p-4 rounded-lg border border-white/5">
                <h3 className="text-sm font-medium text-muted mb-2 flex items-center gap-2">
                  <GitBranch size={14} /> 直系祖先
                </h3>
                <div className="text-lg font-mono">{species.parent_code}</div>
                <div className="text-xs text-muted mt-1">诞生于第 {species.created_turn != null ? species.created_turn + 1 : '?'} 回合</div>
              </div>
            )}

            {species.hybrid_parent_codes && species.hybrid_parent_codes.length > 0 && (
              <div className="bg-purple-500/10 p-4 rounded-lg border border-purple-500/20">
                 <h3 className="text-sm font-medium text-purple-300 mb-3 flex items-center gap-2">
                   <GitMerge size={14} /> 杂交起源
                 </h3>
                 <div className="space-y-3">
                   <div>
                     <div className="text-xs text-purple-300/60 mb-1">亲本物种</div>
                     <div className="flex flex-wrap gap-2">
                       {species.hybrid_parent_codes.map(code => (
                         <span key={code} className="bg-purple-500/20 text-purple-200 px-2 py-1 rounded text-xs font-mono border border-purple-500/30">
                           {code}
                         </span>
                       ))}
                     </div>
                   </div>
                   <div>
                     <div className="text-xs text-purple-300/60 mb-1">后代可育性</div>
                     <div className="flex items-center gap-2">
                       <div className="flex-1 h-1.5 bg-purple-900/50 rounded-full overflow-hidden">
                         <div 
                           className="h-full bg-purple-400" 
                           style={{ width: `${(species.hybrid_fertility || 0) * 100}%` }}
                         />
                       </div>
                       <span className="text-sm font-bold text-purple-300">{((species.hybrid_fertility || 0) * 100).toFixed(0)}%</span>
                     </div>
                   </div>
                 </div>
              </div>
            )}
          </div>
        )}

      </div>
    </div>
  );
}
