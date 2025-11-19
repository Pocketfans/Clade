import React, { useMemo, useState } from "react";
import { SpeciesSnapshot } from "../services/api.types";
import { GamePanel } from "./common/GamePanel";

interface Props {
  speciesList: SpeciesSnapshot[];
  onClose: () => void;
  onSelectSpecies: (id: string) => void;
}

type SortField = "population" | "population_share" | "death_rate" | "latin_name" | "status" | "trophic_level";
type SortOrder = "asc" | "desc";

export function SpeciesLedger({ speciesList, onClose, onSelectSpecies }: Props) {
  const [sortField, setSortField] = useState<SortField>("trophic_level"); // Default to trophic level to show hierarchy
  const [sortOrder, setSortOrder] = useState<SortOrder>("desc");
  const [filterText, setFilterText] = useState("");
  const [statusFilter, setStatusFilter] = useState<string>("all");

  const sortedAndFilteredList = useMemo(() => {
    let list = [...speciesList];

    // Filter
    if (filterText) {
      const lower = filterText.toLowerCase();
      list = list.filter(
        (s) =>
          s.latin_name.toLowerCase().includes(lower) ||
          s.common_name.toLowerCase().includes(lower) ||
          s.lineage_code.toLowerCase().includes(lower)
      );
    }

    if (statusFilter !== "all") {
      list = list.filter((s) => s.status === statusFilter);
    }

    // Sort
    list.sort((a, b) => {
      let valA: any = a[sortField];
      let valB: any = b[sortField];

      // Handle special cases or defaults
      if (sortField === "status") {
        // Custom order for status if needed, or just string compare
      }

      if (valA < valB) return sortOrder === "asc" ? -1 : 1;
      if (valA > valB) return sortOrder === "asc" ? 1 : -1;
      return 0;
    });

    return list;
  }, [speciesList, sortField, sortOrder, filterText, statusFilter]);

  const handleSort = (field: SortField) => {
    if (sortField === field) {
      setSortOrder(sortOrder === "asc" ? "desc" : "asc");
    } else {
      setSortField(field);
      setSortOrder("desc");
    }
  };

  const SortIcon = ({ field }: { field: SortField }) => {
    if (sortField !== field) return <span style={{ opacity: 0.3 }}>↕</span>;
    return <span>{sortOrder === "asc" ? "↑" : "↓"}</span>;
  };

  return (
    <GamePanel
      title={
        <div style={{ display: "flex", alignItems: "center", gap: "12px" }}>
          <span>物种统计表 (Species Ledger)</span>
          <span style={{ 
            background: "rgba(255,255,255,0.1)", 
            padding: "2px 8px", 
            borderRadius: "12px", 
            fontSize: "0.8rem", 
            color: "rgba(255,255,255,0.7)" 
          }}>
            {sortedAndFilteredList.length} / {speciesList.length}
          </span>
        </div>
      }
      onClose={onClose}
      variant="modal"
      width="1000px"
      height="80vh"
    >
      {/* Toolbar */}
      <div style={{ padding: "16px 24px", display: "flex", gap: "12px", borderBottom: "1px solid rgba(255,255,255,0.1)" }}>
        <input
          type="text"
          placeholder="搜索名称或代号..."
          value={filterText}
          onChange={(e) => setFilterText(e.target.value)}
          className="field-input" // Reusing class from styles.css if available, otherwise style manually
          style={{
            background: "rgba(0,0,0,0.3)",
            border: "1px solid rgba(255,255,255,0.2)",
            color: "white",
            padding: "8px 12px",
            borderRadius: "4px",
            flex: 1,
          }}
        />
        <select
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value)}
          style={{
            background: "rgba(0,0,0,0.3)",
            border: "1px solid rgba(255,255,255,0.2)",
            color: "white",
            padding: "8px 12px",
            borderRadius: "4px",
            width: "140px",
          }}
        >
          <option value="all">所有状态</option>
          <option value="alive">存活 (Alive)</option>
          <option value="extinct">灭绝 (Extinct)</option>
          <option value="endangered">濒危 (Endangered)</option>
        </select>
      </div>

      {/* Table Header */}
      <div style={{ 
        display: "grid", 
        gridTemplateColumns: "80px 2fr 1fr 1fr 1fr 80px 100px", 
        padding: "12px 24px", 
        background: "rgba(0,0,0,0.2)",
        borderBottom: "1px solid rgba(255,255,255,0.1)",
        fontSize: "0.85rem",
        fontWeight: 600,
        color: "rgba(255,255,255,0.6)",
        userSelect: "none",
      }}>
        <div onClick={() => handleSort("latin_name")} style={{ cursor: "pointer" }}>代号 <SortIcon field="latin_name" /></div>
        <div onClick={() => handleSort("latin_name")} style={{ cursor: "pointer" }}>名称 (Name) <SortIcon field="latin_name" /></div>
        <div onClick={() => handleSort("population")} style={{ cursor: "pointer", textAlign: "right" }}>人口 (Pop) <SortIcon field="population" /></div>
        <div onClick={() => handleSort("population_share")} style={{ cursor: "pointer", textAlign: "right" }}>占比 (%) <SortIcon field="population_share" /></div>
        <div onClick={() => handleSort("death_rate")} style={{ cursor: "pointer", textAlign: "right" }}>死亡率 <SortIcon field="death_rate" /></div>
        <div onClick={() => handleSort("trophic_level")} style={{ cursor: "pointer", textAlign: "center" }}>营养级 <SortIcon field="trophic_level" /></div>
        <div onClick={() => handleSort("status")} style={{ cursor: "pointer", textAlign: "center" }}>状态 <SortIcon field="status" /></div>
      </div>

      {/* Table Body */}
      <div style={{ flex: 1, overflowY: "auto" }}>
        {sortedAndFilteredList.map((species) => (
          <div
            key={species.lineage_code}
            onClick={() => onSelectSpecies(species.lineage_code)}
            style={{
              display: "grid",
              gridTemplateColumns: "80px 2fr 1fr 1fr 1fr 80px 100px",
              padding: "12px 24px",
              borderBottom: "1px solid rgba(255,255,255,0.03)",
              fontSize: "0.9rem",
              color: "#ccc",
              cursor: "pointer",
              transition: "background 0.1s",
              alignItems: "center"
            }}
            onMouseEnter={(e) => (e.currentTarget.style.background = "rgba(255,255,255,0.05)")}
            onMouseLeave={(e) => (e.currentTarget.style.background = "transparent")}
          >
            <div style={{ fontFamily: "monospace", color: "rgba(255,255,255,0.5)" }}>{species.lineage_code}</div>
            <div>
              <div style={{ color: "#fff", fontWeight: 500 }}>{species.common_name}</div>
              <div style={{ fontSize: "0.75rem", color: "rgba(255,255,255,0.5)", fontStyle: "italic" }}>{species.latin_name}</div>
            </div>
            <div style={{ textAlign: "right", fontFamily: "monospace" }}>{species.population.toLocaleString()}</div>
            <div style={{ textAlign: "right", fontFamily: "monospace" }}>{(species.population_share * 100).toFixed(1)}%</div>
            <div style={{ textAlign: "right", fontFamily: "monospace", color: species.death_rate > 0.1 ? "#ff4444" : "rgba(255,255,255,0.6)" }}>
              {(species.death_rate * 100).toFixed(1)}%
            </div>
            <div style={{ textAlign: "center", fontFamily: "monospace", color: getTrophicColor(species.tier) }}>
              {species.tier || "T1.0"}
            </div>
            <div style={{ textAlign: "center" }}>
              <StatusBadge status={species.status} />
            </div>
          </div>
        ))}
        
        {sortedAndFilteredList.length === 0 && (
          <div style={{ padding: "40px", textAlign: "center", color: "rgba(255,255,255,0.5)" }}>
            没有找到匹配的物种
          </div>
        )}
      </div>
    </GamePanel>
  );
}

function getTrophicColor(tier?: string | null) {
  if (!tier) return "#889";
  // Simple heuristic: T1=Green, T2=Yellow, T3+=Red
  if (tier.startsWith("T1")) return "#4caf50";
  if (tier.startsWith("T2")) return "#ffeb3b";
  return "#f44336";
}

function StatusBadge({ status }: { status: string }) {
  let color = "#889";
  let bg = "rgba(136, 136, 153, 0.1)";
  
  switch (status.toLowerCase()) {
    case "alive":
      color = "#4caf50";
      bg = "rgba(76, 175, 80, 0.1)";
      break;
    case "extinct":
      color = "#f44336";
      bg = "rgba(244, 67, 54, 0.1)";
      break;
    case "endangered":
      color = "#ff9800";
      bg = "rgba(255, 152, 0, 0.1)";
      break;
  }

  return (
    <span style={{
      color,
      background: bg,
      padding: "2px 8px",
      borderRadius: "4px",
      fontSize: "0.75rem",
      textTransform: "uppercase",
      fontWeight: 600,
    }}>
      {status}
    </span>
  );
}

