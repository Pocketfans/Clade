import { useEffect, useState } from "react";
import type { SpeciesListItem, NicheCompareResult } from "../services/api.types";
import { fetchSpeciesList, compareNiche } from "../services/api";
import { GamePanel } from "./common/GamePanel";

interface NicheCompareViewProps {
  onClose?: () => void;
}

export function NicheCompareView({ onClose }: NicheCompareViewProps) {
  const [speciesList, setSpeciesList] = useState<SpeciesListItem[]>([]);
  const [selectedA, setSelectedA] = useState<string | null>(null);
  const [selectedB, setSelectedB] = useState<string | null>(null);
  const [compareResult, setCompareResult] = useState<NicheCompareResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [searchA, setSearchA] = useState("");
  const [searchB, setSearchB] = useState("");
  const [filterStatus, setFilterStatus] = useState<string>("all");
  const [filterRole, setFilterRole] = useState<string>("all");

  useEffect(() => {
    fetchSpeciesList()
      .then(setSpeciesList)
      .catch((err) => {
        console.error("加载物种列表失败:", err);
        setError("加载物种列表失败");
      });
  }, []);

  const filterSpecies = (species: SpeciesListItem[], search: string) => {
    let filtered = species;

    // 状态筛选
    if (filterStatus !== "all") {
      filtered = filtered.filter((s) => s.status === filterStatus);
    }

    // 生态角色筛选
    if (filterRole !== "all") {
      filtered = filtered.filter((s) => s.ecological_role === filterRole);
    }

    // 搜索筛选
    if (search) {
      const searchLower = search.toLowerCase();
      filtered = filtered.filter(
        (s) =>
          s.common_name.toLowerCase().includes(searchLower) ||
          s.latin_name.toLowerCase().includes(searchLower) ||
          s.lineage_code.toLowerCase().includes(searchLower)
      );
    }

    return filtered;
  };

  const filteredSpeciesA = filterSpecies(speciesList, searchA);
  const filteredSpeciesB = filterSpecies(speciesList, searchB);

  const handleCompare = async () => {
    if (!selectedA || !selectedB) {
      setError("请选择两个物种");
      return;
    }

    if (selectedA === selectedB) {
      setError("请选择不同的物种");
      return;
    }

    setLoading(true);
    setError(null);
    try {
      const result = await compareNiche(selectedA, selectedB);
      setCompareResult(result);
    } catch (err: any) {
      console.error("对比失败:", err);
      setError(err.message || "对比失败");
    } finally {
      setLoading(false);
    }
  };

  const getStatusColor = (status: string) => {
    switch (status) {
      case "alive":
        return "#4ade80";
      case "extinct":
        return "#ef4444";
      case "critical":
        return "#f59e0b";
      default:
        return "#9ca3af";
    }
  };

  const getRoleColor = (role: string) => {
    switch (role) {
      case "生产者":
        return "#10b981";
      case "草食者":
        return "#3b82f6";
      case "肉食者":
        return "#ef4444";
      case "杂食者":
        return "#f59e0b";
      default:
        return "#6b7280";
    }
  };

  const formatNumber = (num: number) => {
    if (num >= 1000000) return `${(num / 1000000).toFixed(1)}M`;
    if (num >= 1000) return `${(num / 1000).toFixed(1)}K`;
    return num.toFixed(0);
  };

  const getIntensityColor = (value: number) => {
    if (value < 0.3) return "#10b981";
    if (value < 0.6) return "#f59e0b";
    return "#ef4444";
  };

  return (
    <GamePanel
      title="生态位对比分析 (Niche Comparison)"
      onClose={onClose}
      variant="modal"
      width="1000px"
      height="85vh"
    >
      <div style={{ padding: "24px" }}>
        {error && (
          <div
            style={{
              backgroundColor: "rgba(239, 68, 68, 0.1)",
              color: "#fca5a5",
              padding: "12px 16px",
              borderRadius: "8px",
              marginBottom: "24px",
              border: "1px solid rgba(239, 68, 68, 0.2)"
            }}
          >
            {error}
          </div>
        )}

        <div className="filter-bar" style={{ display: "flex", gap: "16px", marginBottom: "24px", alignItems: "center", background: "rgba(255,255,255,0.03)", padding: "12px", borderRadius: "8px" }}>
          <div style={{ flex: 1 }}>
            <label style={{ fontSize: "0.85rem", color: "rgba(255,255,255,0.6)", marginRight: "8px" }}>状态筛选:</label>
            <select
              value={filterStatus}
              onChange={(e) => setFilterStatus(e.target.value)}
              className="field-input"
              style={{ padding: "6px 12px", fontSize: "0.9rem" }}
            >
              <option value="all">全部</option>
              <option value="alive">存活</option>
              <option value="extinct">灭绝</option>
            </select>
          </div>
          <div style={{ flex: 1 }}>
            <label style={{ fontSize: "0.85rem", color: "rgba(255,255,255,0.6)", marginRight: "8px" }}>生态角色筛选:</label>
            <select
              value={filterRole}
              onChange={(e) => setFilterRole(e.target.value)}
              className="field-input"
              style={{ padding: "6px 12px", fontSize: "0.9rem" }}
            >
              <option value="all">全部</option>
              <option value="生产者">生产者</option>
              <option value="草食者">草食者</option>
              <option value="肉食者">肉食者</option>
              <option value="杂食者">杂食者</option>
            </select>
          </div>
        </div>

        <div className="selector-grid" style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "24px", marginBottom: "24px" }}>
          <div className="species-selector">
            <h3 style={{ fontSize: "1.1rem", fontWeight: "600", marginBottom: "12px", color: "#3b82f6" }}>
              物种 A (基准)
            </h3>
            <input
              type="text"
              placeholder="搜索物种名、学名或代码..."
              value={searchA}
              onChange={(e) => setSearchA(e.target.value)}
              className="field-input"
              style={{ width: "100%", marginBottom: "12px" }}
            />
            <div
              className="custom-scrollbar"
              style={{
                maxHeight: "300px",
                overflowY: "auto",
                border: "1px solid rgba(255,255,255,0.1)",
                borderRadius: "8px",
                backgroundColor: "rgba(0,0,0,0.2)",
              }}
            >
              {filteredSpeciesA.length === 0 ? (
                <div style={{ padding: "24px", textAlign: "center", color: "rgba(255,255,255,0.4)" }}>
                  未找到匹配的物种
                </div>
              ) : (
                filteredSpeciesA.map((species) => (
                  <button
                    key={species.lineage_code}
                    onClick={() => setSelectedA(species.lineage_code)}
                    style={{
                      width: "100%",
                      padding: "10px 16px",
                      borderBottom: "1px solid rgba(255,255,255,0.05)",
                      backgroundColor: selectedA === species.lineage_code ? "rgba(59, 130, 246, 0.15)" : "transparent",
                      borderLeft: selectedA === species.lineage_code ? "3px solid #3b82f6" : "3px solid transparent",
                      borderTop: "none",
                      borderRight: "none",
                      cursor: "pointer",
                      textAlign: "left",
                      transition: "all 0.15s",
                      display: "flex",
                      justifyContent: "space-between",
                      alignItems: "center",
                      color: "#e2ecff"
                    }}
                    onMouseEnter={(e) => {
                      if (selectedA !== species.lineage_code) {
                        e.currentTarget.style.backgroundColor = "rgba(255,255,255,0.05)";
                      }
                    }}
                    onMouseLeave={(e) => {
                      if (selectedA !== species.lineage_code) {
                        e.currentTarget.style.backgroundColor = "transparent";
                      }
                    }}
                  >
                    <div style={{ flex: 1 }}>
                      <div style={{ fontWeight: "500", fontSize: "0.9rem", marginBottom: "2px" }}>
                        {species.common_name}
                        <span style={{ marginLeft: "6px", fontSize: "0.75rem", color: "rgba(255,255,255,0.5)" }}>
                          [{species.lineage_code}]
                        </span>
                      </div>
                      <div style={{ fontSize: "0.8rem", color: "rgba(255,255,255,0.5)", fontStyle: "italic" }}>
                        {species.latin_name}
                      </div>
                    </div>
                    <div style={{ display: "flex", flexDirection: "column", alignItems: "flex-end", gap: "2px" }}>
                      <span
                        style={{
                          fontSize: "0.7rem",
                          padding: "2px 6px",
                          borderRadius: "4px",
                          backgroundColor: getRoleColor(species.ecological_role),
                          color: "white",
                        }}
                      >
                        {species.ecological_role}
                      </span>
                      <span style={{ fontSize: "0.75rem", color: "rgba(255,255,255,0.4)" }}>
                        {formatNumber(species.population)}
                      </span>
                    </div>
                  </button>
                ))
              )}
            </div>
          </div>

          <div className="species-selector">
            <h3 style={{ fontSize: "1.1rem", fontWeight: "600", marginBottom: "12px", color: "#10b981" }}>
              物种 B (对比)
            </h3>
            <input
              type="text"
              placeholder="搜索物种名、学名或代码..."
              value={searchB}
              onChange={(e) => setSearchB(e.target.value)}
              className="field-input"
              style={{ width: "100%", marginBottom: "12px" }}
            />
            <div
              className="custom-scrollbar"
              style={{
                maxHeight: "300px",
                overflowY: "auto",
                border: "1px solid rgba(255,255,255,0.1)",
                borderRadius: "8px",
                backgroundColor: "rgba(0,0,0,0.2)",
              }}
            >
              {filteredSpeciesB.length === 0 ? (
                <div style={{ padding: "24px", textAlign: "center", color: "rgba(255,255,255,0.4)" }}>
                  未找到匹配的物种
                </div>
              ) : (
                filteredSpeciesB.map((species) => (
                  <button
                    key={species.lineage_code}
                    onClick={() => setSelectedB(species.lineage_code)}
                    style={{
                      width: "100%",
                      padding: "10px 16px",
                      borderBottom: "1px solid rgba(255,255,255,0.05)",
                      backgroundColor: selectedB === species.lineage_code ? "rgba(16, 185, 129, 0.15)" : "transparent",
                      borderLeft: selectedB === species.lineage_code ? "3px solid #10b981" : "3px solid transparent",
                      borderTop: "none",
                      borderRight: "none",
                      cursor: "pointer",
                      textAlign: "left",
                      transition: "all 0.15s",
                      display: "flex",
                      justifyContent: "space-between",
                      alignItems: "center",
                      color: "#e2ecff"
                    }}
                    onMouseEnter={(e) => {
                      if (selectedB !== species.lineage_code) {
                        e.currentTarget.style.backgroundColor = "rgba(255,255,255,0.05)";
                      }
                    }}
                    onMouseLeave={(e) => {
                      if (selectedB !== species.lineage_code) {
                        e.currentTarget.style.backgroundColor = "transparent";
                      }
                    }}
                  >
                    <div style={{ flex: 1 }}>
                      <div style={{ fontWeight: "500", fontSize: "0.9rem", marginBottom: "2px" }}>
                        {species.common_name}
                        <span style={{ marginLeft: "6px", fontSize: "0.75rem", color: "rgba(255,255,255,0.5)" }}>
                          [{species.lineage_code}]
                        </span>
                      </div>
                      <div style={{ fontSize: "0.8rem", color: "rgba(255,255,255,0.5)", fontStyle: "italic" }}>
                        {species.latin_name}
                      </div>
                    </div>
                    <div style={{ display: "flex", flexDirection: "column", alignItems: "flex-end", gap: "2px" }}>
                      <span
                        style={{
                          fontSize: "0.7rem",
                          padding: "2px 6px",
                          borderRadius: "4px",
                          backgroundColor: getRoleColor(species.ecological_role),
                          color: "white",
                        }}
                      >
                        {species.ecological_role}
                      </span>
                      <span style={{ fontSize: "0.75rem", color: "rgba(255,255,255,0.4)" }}>
                        {formatNumber(species.population)}
                      </span>
                    </div>
                  </button>
                ))
              )}
            </div>
          </div>
        </div>

        <div style={{ display: "flex", justifyContent: "center", gap: "1rem", marginBottom: "32px" }}>
          <button
            onClick={handleCompare}
            disabled={!selectedA || !selectedB || loading}
            className="btn-primary btn-lg"
            style={{
              opacity: selectedA && selectedB ? 1 : 0.5,
              cursor: selectedA && selectedB ? "pointer" : "not-allowed",
            }}
          >
            {loading ? "计算中..." : "⚔️ 开始对比分析"}
          </button>
        </div>

        {compareResult && (
          <div className="compare-result fade-in">
            <div className="metrics-grid" style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: "24px", marginBottom: "32px" }}>
              <div className="metric-card" style={{ padding: "24px", backgroundColor: "rgba(255,255,255,0.03)", borderRadius: "12px", textAlign: "center", border: "1px solid rgba(255,255,255,0.1)" }}>
                <div style={{ fontSize: "0.85rem", color: "rgba(255,255,255,0.5)", marginBottom: "8px", textTransform: "uppercase", letterSpacing: "1px" }}>生态位相似度</div>
                <div style={{ fontSize: "2.5rem", fontWeight: "bold", color: "#3b82f6", fontFamily: "var(--font-mono)" }}>
                  {(compareResult.similarity * 100).toFixed(1)}%
                </div>
                <div style={{ fontSize: "0.8rem", color: "rgba(255,255,255,0.4)", marginTop: "8px" }}>
                  基于描述向量的余弦相似度
                </div>
              </div>

              <div className="metric-card" style={{ padding: "24px", backgroundColor: "rgba(255,255,255,0.03)", borderRadius: "12px", textAlign: "center", border: "1px solid rgba(255,255,255,0.1)" }}>
                <div style={{ fontSize: "0.85rem", color: "rgba(255,255,255,0.5)", marginBottom: "8px", textTransform: "uppercase", letterSpacing: "1px" }}>生态位重叠度</div>
                <div style={{ fontSize: "2.5rem", fontWeight: "bold", color: "#10b981", fontFamily: "var(--font-mono)" }}>
                  {(compareResult.overlap * 100).toFixed(1)}%
                </div>
                <div style={{ fontSize: "0.8rem", color: "rgba(255,255,255,0.4)", marginTop: "8px" }}>
                  资源利用的重叠程度
                </div>
              </div>

              <div className="metric-card" style={{ padding: "24px", backgroundColor: "rgba(255,255,255,0.03)", borderRadius: "12px", textAlign: "center", border: "1px solid rgba(255,255,255,0.1)" }}>
                <div style={{ fontSize: "0.85rem", color: "rgba(255,255,255,0.5)", marginBottom: "8px", textTransform: "uppercase", letterSpacing: "1px" }}>竞争强度</div>
                <div
                  style={{
                    fontSize: "2.5rem",
                    fontWeight: "bold",
                    color: getIntensityColor(compareResult.competition_intensity),
                    fontFamily: "var(--font-mono)"
                  }}
                >
                  {(compareResult.competition_intensity * 100).toFixed(1)}%
                </div>
                <div style={{ fontSize: "0.8rem", color: "rgba(255,255,255,0.4)", marginTop: "8px" }}>
                  综合考虑种群规模的竞争压力
                </div>
              </div>
            </div>

            <div className="dimensions-comparison" style={{ backgroundColor: "rgba(255,255,255,0.03)", borderRadius: "12px", padding: "24px", border: "1px solid rgba(255,255,255,0.1)" }}>
              <h3 style={{ fontSize: "1.25rem", fontWeight: "600", marginBottom: "24px", color: "#e2ecff" }}>生态位维度对比</h3>
              <div style={{ display: "grid", gap: "16px" }}>
                {Object.entries(compareResult.niche_dimensions).map(([dimension, values]) => {
                  const valueA = values.species_a;
                  const valueB = values.species_b;
                  const maxValue = Math.max(valueA, valueB) || 1;
                  const percentA = (valueA / maxValue) * 100;
                  const percentB = (valueB / maxValue) * 100;

                  return (
                    <div key={dimension} style={{ marginBottom: "8px" }}>
                      <div style={{ fontSize: "0.9rem", fontWeight: "500", marginBottom: "8px", color: "rgba(255,255,255,0.8)" }}>{dimension}</div>
                      <div style={{ display: "grid", gridTemplateColumns: "1fr auto 1fr", gap: "16px", alignItems: "center" }}>
                        <div style={{ textAlign: "right" }}>
                          <div style={{ fontSize: "0.85rem", color: "rgba(255,255,255,0.5)", marginBottom: "4px" }}>
                            {compareResult.species_a.common_name}
                          </div>
                          <div style={{ display: "flex", justifyContent: "flex-end", alignItems: "center", gap: "8px" }}>
                            <div style={{ fontSize: "0.85rem", color: "rgba(255,255,255,0.7)", fontFamily: "var(--font-mono)" }}>{formatNumber(valueA)}</div>
                            <div
                              style={{
                                height: "8px",
                                backgroundColor: "#3b82f6",
                                borderRadius: "4px",
                                width: `${percentA}%`,
                                minWidth: "4px"
                              }}
                            />
                          </div>
                        </div>

                        <div style={{ fontSize: "0.9rem", fontWeight: "bold", color: "rgba(255,255,255,0.3)" }}>VS</div>

                        <div style={{ textAlign: "left" }}>
                          <div style={{ fontSize: "0.85rem", color: "rgba(255,255,255,0.5)", marginBottom: "4px" }}>
                            {compareResult.species_b.common_name}
                          </div>
                          <div style={{ display: "flex", justifyContent: "flex-start", alignItems: "center", gap: "8px" }}>
                            <div
                              style={{
                                height: "8px",
                                backgroundColor: "#10b981",
                                borderRadius: "4px",
                                width: `${percentB}%`,
                                minWidth: "4px"
                              }}
                            />
                            <div style={{ fontSize: "0.85rem", color: "rgba(255,255,255,0.7)", fontFamily: "var(--font-mono)" }}>{formatNumber(valueB)}</div>
                          </div>
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>

            <div className="species-details-grid" style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "24px", marginTop: "32px" }}>
              <div className="species-detail-card" style={{ backgroundColor: "rgba(59, 130, 246, 0.05)", borderRadius: "12px", padding: "24px", border: "1px solid rgba(59, 130, 246, 0.2)" }}>
                <h4 style={{ fontSize: "1.1rem", fontWeight: "600", marginBottom: "12px", color: "#3b82f6" }}>
                  {compareResult.species_a.common_name}
                </h4>
                <div style={{ fontSize: "0.9rem", fontStyle: "italic", color: "rgba(255,255,255,0.5)", marginBottom: "16px" }}>
                  {compareResult.species_a.latin_name}
                </div>
                <p style={{ fontSize: "0.9rem", lineHeight: "1.6", color: "rgba(255,255,255,0.8)" }}>
                  {compareResult.species_a.description}
                </p>
              </div>

              <div className="species-detail-card" style={{ backgroundColor: "rgba(16, 185, 129, 0.05)", borderRadius: "12px", padding: "24px", border: "1px solid rgba(16, 185, 129, 0.2)" }}>
                <h4 style={{ fontSize: "1.1rem", fontWeight: "600", marginBottom: "12px", color: "#10b981" }}>
                  {compareResult.species_b.common_name}
                </h4>
                <div style={{ fontSize: "0.9rem", fontStyle: "italic", color: "rgba(255,255,255,0.5)", marginBottom: "16px" }}>
                  {compareResult.species_b.latin_name}
                </div>
                <p style={{ fontSize: "0.9rem", lineHeight: "1.6", color: "rgba(255,255,255,0.8)" }}>
                  {compareResult.species_b.description}
                </p>
              </div>
            </div>
          </div>
        )}
      </div>
    </GamePanel>
  );
}

