import { Filter, Search, ChevronDown } from "lucide-react";
import { useState } from "react";

export interface FilterOptions {
  states: string[];
  ecologicalRoles: string[];
  tiers: string[];
  turnRange: [number, number];
  searchTerm: string;
}

interface Props {
  filters: FilterOptions;
  maxTurn: number;
  onChange: (filters: FilterOptions) => void;
}

export function GenealogyFilters({ filters, maxTurn, onChange }: Props) {
  const [showFilters, setShowFilters] = useState(false);

  const stateOptions = [
    { value: "alive", label: "存活" },
    { value: "extinct", label: "灭绝" },
  ];

  const roleOptions = [
    { value: "producer", label: "生产者" },
    { value: "herbivore", label: "食草" },
    { value: "carnivore", label: "食肉" },
    { value: "omnivore", label: "杂食" },
    { value: "unknown", label: "未知" },
  ];

  const tierOptions = [
    { value: "focus", label: "重点" },
    { value: "important", label: "重要" },
    { value: "background", label: "背景" },
  ];

  const toggleState = (state: string) => {
    const newStates = filters.states.includes(state)
      ? filters.states.filter(s => s !== state)
      : [...filters.states, state];
    onChange({ ...filters, states: newStates });
  };

  const toggleRole = (role: string) => {
    const newRoles = filters.ecologicalRoles.includes(role)
      ? filters.ecologicalRoles.filter(r => r !== role)
      : [...filters.ecologicalRoles, role];
    onChange({ ...filters, ecologicalRoles: newRoles });
  };

  const toggleTier = (tier: string) => {
    const newTiers = filters.tiers.includes(tier)
      ? filters.tiers.filter(t => t !== tier)
      : [...filters.tiers, tier];
    onChange({ ...filters, tiers: newTiers });
  };

  const resetFilters = () => {
    onChange({
      states: [],
      ecologicalRoles: [],
      tiers: [],
      turnRange: [0, maxTurn],
      searchTerm: "",
    });
  };

  return (
    <div className="genealogy-filters">
      <div className="filters-header">
        <button 
          className="filters-toggle"
          onClick={() => setShowFilters(!showFilters)}
        >
          <Filter size={16} />
          <span>筛选器</span>
          <ChevronDown 
            size={16} 
            style={{ 
              transform: showFilters ? "rotate(180deg)" : "rotate(0deg)",
              transition: "transform 0.2s"
            }}
          />
        </button>
        <div className="search-box">
          <Search size={16} />
          <input
            type="text"
            placeholder="搜索物种..."
            value={filters.searchTerm}
            onChange={(e) => onChange({ ...filters, searchTerm: e.target.value })}
          />
        </div>
      </div>

      {showFilters && (
        <div className="filters-body">
          <div className="filter-group">
            <label>状态</label>
            <div className="chip-rail">
              {stateOptions.map(opt => (
                <button
                  key={opt.value}
                  className={`chip-button ${filters.states.includes(opt.value) ? "active" : ""}`}
                  onClick={() => toggleState(opt.value)}
                >
                  {opt.label}
                </button>
              ))}
            </div>
          </div>

          <div className="filter-group">
            <label>生态角色</label>
            <div className="chip-rail">
              {roleOptions.map(opt => (
                <button
                  key={opt.value}
                  className={`chip-button ${filters.ecologicalRoles.includes(opt.value) ? "active" : ""}`}
                  onClick={() => toggleRole(opt.value)}
                >
                  {opt.label}
                </button>
              ))}
            </div>
          </div>

          <div className="filter-group">
            <label>层级</label>
            <div className="chip-rail">
              {tierOptions.map(opt => (
                <button
                  key={opt.value}
                  className={`chip-button ${filters.tiers.includes(opt.value) ? "active" : ""}`}
                  onClick={() => toggleTier(opt.value)}
                >
                  {opt.label}
                </button>
              ))}
            </div>
          </div>

          <div className="filter-group">
            <label>诞生回合: {filters.turnRange[0]} - {filters.turnRange[1]}</label>
            <input
              type="range"
              min={0}
              max={maxTurn}
              value={filters.turnRange[1]}
              onChange={(e) => onChange({ 
                ...filters, 
                turnRange: [filters.turnRange[0], parseInt(e.target.value)] 
              })}
              style={{ width: "100%" }}
            />
          </div>

          <button 
            className="ghost-button" 
            onClick={resetFilters}
            style={{ marginTop: "0.5rem" }}
          >
            重置筛选
          </button>
        </div>
      )}
    </div>
  );
}

