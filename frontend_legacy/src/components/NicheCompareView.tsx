import { useEffect, useState } from "react";
import type { SpeciesListItem, NicheCompareResult } from "../services/api.types";
import { fetchSpeciesList, compareNiche } from "../services/api";

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
    <div className="niche-compare-container" style={{ padding: "2rem", maxWidth: "1400px", margin: "0 auto" }}>
      <div className="niche-header" style={{ marginBottom: "2rem" }}>
        <h2 style={{ fontSize: "1.75rem", fontWeight: "bold", marginBottom: "0.5rem" }}>生态位对比分析</h2>
        <p style={{ color: "#9ca3af", fontSize: "0.95rem" }}>选择两个物种，对比它们的生态位重叠度与竞争关系</p>
      </div>

      {error && (
        <div
          style={{
            backgroundColor: "#fee2e2",
            color: "#991b1b",
            padding: "1rem",
            borderRadius: "0.5rem",
            marginBottom: "1.5rem",
          }}
        >
          {error}
        </div>
      )}

      <div className="filter-bar" style={{ display: "flex", gap: "1rem", marginBottom: "1.5rem", alignItems: "center" }}>
        <div style={{ flex: 1 }}>
          <label style={{ fontSize: "0.85rem", color: "#9ca3af", marginRight: "0.5rem" }}>状态:</label>
          <select
            value={filterStatus}
            onChange={(e) => setFilterStatus(e.target.value)}
            style={{
              padding: "0.5rem",
              borderRadius: "0.375rem",
              backgroundColor: "#1f2937",
              border: "1px solid #374151",
              color: "white",
              fontSize: "0.9rem",
            }}
          >
            <option value="all">全部</option>
            <option value="alive">存活</option>
            <option value="extinct">灭绝</option>
          </select>
        </div>
        <div style={{ flex: 1 }}>
          <label style={{ fontSize: "0.85rem", color: "#9ca3af", marginRight: "0.5rem" }}>生态角色:</label>
          <select
            value={filterRole}
            onChange={(e) => setFilterRole(e.target.value)}
            style={{
              padding: "0.5rem",
              borderRadius: "0.375rem",
              backgroundColor: "#1f2937",
              border: "1px solid #374151",
              color: "white",
              fontSize: "0.9rem",
            }}
          >
            <option value="all">全部</option>
            <option value="生产者">生产者</option>
            <option value="草食者">草食者</option>
            <option value="肉食者">肉食者</option>
            <option value="杂食者">杂食者</option>
          </select>
        </div>
      </div>

      <div className="selector-grid" style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "2rem", marginBottom: "2rem" }}>
        <div className="species-selector">
          <h3 style={{ fontSize: "1.1rem", fontWeight: "600", marginBottom: "0.75rem", color: "#3b82f6" }}>
            物种 A
          </h3>
          <input
            type="text"
            placeholder="搜索物种名、学名或代码..."
            value={searchA}
            onChange={(e) => setSearchA(e.target.value)}
            style={{
              width: "100%",
              padding: "0.75rem",
              marginBottom: "0.75rem",
              borderRadius: "0.5rem",
              backgroundColor: "#1f2937",
              border: "1px solid #374151",
              color: "white",
              fontSize: "0.9rem",
            }}
          />
          <div
            className="species-list"
            style={{
              maxHeight: "450px",
              overflowY: "auto",
              border: "1px solid #374151",
              borderRadius: "0.5rem",
              backgroundColor: "#111827",
            }}
          >
            {filteredSpeciesA.length === 0 ? (
              <div style={{ padding: "2rem", textAlign: "center", color: "#6b7280" }}>
                未找到匹配的物种
              </div>
            ) : (
              filteredSpeciesA.map((species) => (
                <button
                  key={species.lineage_code}
                  onClick={() => setSelectedA(species.lineage_code)}
                  style={{
                    width: "100%",
                    padding: "0.75rem 1rem",
                    borderBottom: "1px solid #1f2937",
                    backgroundColor: selectedA === species.lineage_code ? "rgba(59, 130, 246, 0.15)" : "transparent",
                    borderLeft: selectedA === species.lineage_code ? "3px solid #3b82f6" : "3px solid transparent",
                    cursor: "pointer",
                    textAlign: "left",
                    transition: "all 0.15s",
                    display: "flex",
                    justifyContent: "space-between",
                    alignItems: "center",
                  }}
                  onMouseEnter={(e) => {
                    if (selectedA !== species.lineage_code) {
                      e.currentTarget.style.backgroundColor = "rgba(59, 130, 246, 0.05)";
                    }
                  }}
                  onMouseLeave={(e) => {
                    if (selectedA !== species.lineage_code) {
                      e.currentTarget.style.backgroundColor = "transparent";
                    }
                  }}
                >
                  <div style={{ flex: 1 }}>
                    <div style={{ fontWeight: "500", fontSize: "0.9rem", marginBottom: "0.25rem" }}>
                      {species.common_name}
                      <span style={{ marginLeft: "0.5rem", fontSize: "0.75rem", color: "#6b7280" }}>
                        [{species.lineage_code}]
                      </span>
                    </div>
                    <div style={{ fontSize: "0.8rem", color: "#9ca3af", fontStyle: "italic" }}>
                      {species.latin_name}
                    </div>
                  </div>
                  <div style={{ display: "flex", flexDirection: "column", alignItems: "flex-end", gap: "0.25rem" }}>
                    <span
                      style={{
                        fontSize: "0.7rem",
                        padding: "0.15rem 0.4rem",
                        borderRadius: "0.25rem",
                        backgroundColor: getRoleColor(species.ecological_role),
                        color: "white",
                      }}
                    >
                      {species.ecological_role}
                    </span>
                    <span style={{ fontSize: "0.75rem", color: "#9ca3af" }}>
                      {formatNumber(species.population)}
                    </span>
                  </div>
                </button>
              ))
            )}
          </div>
        </div>

        <div className="species-selector">
          <h3 style={{ fontSize: "1.1rem", fontWeight: "600", marginBottom: "0.75rem", color: "#10b981" }}>
            物种 B
          </h3>
          <input
            type="text"
            placeholder="搜索物种名、学名或代码..."
            value={searchB}
            onChange={(e) => setSearchB(e.target.value)}
            style={{
              width: "100%",
              padding: "0.75rem",
              marginBottom: "0.75rem",
              borderRadius: "0.5rem",
              backgroundColor: "#1f2937",
              border: "1px solid #374151",
              color: "white",
              fontSize: "0.9rem",
            }}
          />
          <div
            className="species-list"
            style={{
              maxHeight: "450px",
              overflowY: "auto",
              border: "1px solid #374151",
              borderRadius: "0.5rem",
              backgroundColor: "#111827",
            }}
          >
            {filteredSpeciesB.length === 0 ? (
              <div style={{ padding: "2rem", textAlign: "center", color: "#6b7280" }}>
                未找到匹配的物种
              </div>
            ) : (
              filteredSpeciesB.map((species) => (
                <button
                  key={species.lineage_code}
                  onClick={() => setSelectedB(species.lineage_code)}
                  style={{
                    width: "100%",
                    padding: "0.75rem 1rem",
                    borderBottom: "1px solid #1f2937",
                    backgroundColor: selectedB === species.lineage_code ? "rgba(16, 185, 129, 0.15)" : "transparent",
                    borderLeft: selectedB === species.lineage_code ? "3px solid #10b981" : "3px solid transparent",
                    cursor: "pointer",
                    textAlign: "left",
                    transition: "all 0.15s",
                    display: "flex",
                    justifyContent: "space-between",
                    alignItems: "center",
                  }}
                  onMouseEnter={(e) => {
                    if (selectedB !== species.lineage_code) {
                      e.currentTarget.style.backgroundColor = "rgba(16, 185, 129, 0.05)";
                    }
                  }}
                  onMouseLeave={(e) => {
                    if (selectedB !== species.lineage_code) {
                      e.currentTarget.style.backgroundColor = "transparent";
                    }
                  }}
                >
                  <div style={{ flex: 1 }}>
                    <div style={{ fontWeight: "500", fontSize: "0.9rem", marginBottom: "0.25rem" }}>
                      {species.common_name}
                      <span style={{ marginLeft: "0.5rem", fontSize: "0.75rem", color: "#6b7280" }}>
                        [{species.lineage_code}]
                      </span>
                    </div>
                    <div style={{ fontSize: "0.8rem", color: "#9ca3af", fontStyle: "italic" }}>
                      {species.latin_name}
                    </div>
                  </div>
                  <div style={{ display: "flex", flexDirection: "column", alignItems: "flex-end", gap: "0.25rem" }}>
                    <span
                      style={{
                        fontSize: "0.7rem",
                        padding: "0.15rem 0.4rem",
                        borderRadius: "0.25rem",
                        backgroundColor: getRoleColor(species.ecological_role),
                        color: "white",
                      }}
                    >
                      {species.ecological_role}
                    </span>
                    <span style={{ fontSize: "0.75rem", color: "#9ca3af" }}>
                      {formatNumber(species.population)}
                    </span>
                  </div>
                </button>
              ))
            )}
          </div>
        </div>
      </div>

      <div style={{ display: "flex", justifyContent: "center", gap: "1rem", marginBottom: "2rem" }}>
        <button
          onClick={handleCompare}
          disabled={!selectedA || !selectedB || loading}
          style={{
            padding: "0.75rem 2rem",
            fontSize: "1rem",
            fontWeight: "600",
            borderRadius: "0.5rem",
            backgroundColor: selectedA && selectedB ? "#3b82f6" : "#4b5563",
            color: "white",
            border: "none",
            cursor: selectedA && selectedB ? "pointer" : "not-allowed",
            opacity: selectedA && selectedB ? 1 : 0.5,
          }}
        >
          {loading ? "计算中..." : "开始对比"}
        </button>
      </div>

      {compareResult && (
        <div className="compare-result" style={{ marginTop: "2rem" }}>
          <div className="metrics-grid" style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: "1.5rem", marginBottom: "2rem" }}>
            <div className="metric-card" style={{ padding: "1.5rem", backgroundColor: "#1f2937", borderRadius: "0.75rem", textAlign: "center" }}>
              <div style={{ fontSize: "0.85rem", color: "#9ca3af", marginBottom: "0.5rem" }}>生态位相似度</div>
              <div style={{ fontSize: "2rem", fontWeight: "bold", color: "#3b82f6" }}>
                {(compareResult.similarity * 100).toFixed(1)}%
              </div>
              <div style={{ fontSize: "0.8rem", color: "#6b7280", marginTop: "0.5rem" }}>
                基于描述向量的余弦相似度
              </div>
            </div>

            <div className="metric-card" style={{ padding: "1.5rem", backgroundColor: "#1f2937", borderRadius: "0.75rem", textAlign: "center" }}>
              <div style={{ fontSize: "0.85rem", color: "#9ca3af", marginBottom: "0.5rem" }}>生态位重叠度</div>
              <div style={{ fontSize: "2rem", fontWeight: "bold", color: "#10b981" }}>
                {(compareResult.overlap * 100).toFixed(1)}%
              </div>
              <div style={{ fontSize: "0.8rem", color: "#6b7280", marginTop: "0.5rem" }}>
                资源利用的重叠程度
              </div>
            </div>

            <div className="metric-card" style={{ padding: "1.5rem", backgroundColor: "#1f2937", borderRadius: "0.75rem", textAlign: "center" }}>
              <div style={{ fontSize: "0.85rem", color: "#9ca3af", marginBottom: "0.5rem" }}>竞争强度</div>
              <div
                style={{
                  fontSize: "2rem",
                  fontWeight: "bold",
                  color: getIntensityColor(compareResult.competition_intensity),
                }}
              >
                {(compareResult.competition_intensity * 100).toFixed(1)}%
              </div>
              <div style={{ fontSize: "0.8rem", color: "#6b7280", marginTop: "0.5rem" }}>
                综合考虑种群规模的竞争压力
              </div>
            </div>
          </div>

          <div className="dimensions-comparison" style={{ backgroundColor: "#1f2937", borderRadius: "0.75rem", padding: "1.5rem" }}>
            <h3 style={{ fontSize: "1.25rem", fontWeight: "600", marginBottom: "1.5rem" }}>生态位维度对比</h3>
            <div style={{ display: "grid", gap: "1rem" }}>
              {Object.entries(compareResult.niche_dimensions).map(([dimension, values]) => {
                const valueA = values.species_a;
                const valueB = values.species_b;
                const maxValue = Math.max(valueA, valueB) || 1;
                const percentA = (valueA / maxValue) * 100;
                const percentB = (valueB / maxValue) * 100;

                return (
                  <div key={dimension} style={{ marginBottom: "0.5rem" }}>
                    <div style={{ fontSize: "0.9rem", fontWeight: "500", marginBottom: "0.75rem" }}>{dimension}</div>
                    <div style={{ display: "grid", gridTemplateColumns: "1fr auto 1fr", gap: "1rem", alignItems: "center" }}>
                      <div style={{ textAlign: "right" }}>
                        <div style={{ fontSize: "0.85rem", color: "#9ca3af", marginBottom: "0.25rem" }}>
                          {compareResult.species_a.common_name}
                        </div>
                        <div
                          style={{
                            height: "8px",
                            backgroundColor: "#3b82f6",
                            borderRadius: "4px",
                            width: `${percentA}%`,
                            marginLeft: "auto",
                          }}
                        />
                        <div style={{ fontSize: "0.8rem", color: "#6b7280", marginTop: "0.25rem" }}>
                          {formatNumber(valueA)}
                        </div>
                      </div>

                      <div style={{ fontSize: "1.25rem", fontWeight: "bold", color: "#4b5563" }}>VS</div>

                      <div style={{ textAlign: "left" }}>
                        <div style={{ fontSize: "0.85rem", color: "#9ca3af", marginBottom: "0.25rem" }}>
                          {compareResult.species_b.common_name}
                        </div>
                        <div
                          style={{
                            height: "8px",
                            backgroundColor: "#10b981",
                            borderRadius: "4px",
                            width: `${percentB}%`,
                          }}
                        />
                        <div style={{ fontSize: "0.8rem", color: "#6b7280", marginTop: "0.25rem" }}>
                          {formatNumber(valueB)}
                        </div>
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>

          <div className="species-details-grid" style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "1.5rem", marginTop: "2rem" }}>
            <div className="species-detail-card" style={{ backgroundColor: "#1f2937", borderRadius: "0.75rem", padding: "1.5rem" }}>
              <h4 style={{ fontSize: "1.1rem", fontWeight: "600", marginBottom: "1rem", color: "#3b82f6" }}>
                {compareResult.species_a.common_name}
              </h4>
              <div style={{ fontSize: "0.9rem", fontStyle: "italic", color: "#9ca3af", marginBottom: "1rem" }}>
                {compareResult.species_a.latin_name}
              </div>
              <p style={{ fontSize: "0.9rem", lineHeight: "1.6", color: "#d1d5db" }}>
                {compareResult.species_a.description}
              </p>
            </div>

            <div className="species-detail-card" style={{ backgroundColor: "#1f2937", borderRadius: "0.75rem", padding: "1.5rem" }}>
              <h4 style={{ fontSize: "1.1rem", fontWeight: "600", marginBottom: "1rem", color: "#10b981" }}>
                {compareResult.species_b.common_name}
              </h4>
              <div style={{ fontSize: "0.9rem", fontStyle: "italic", color: "#9ca3af", marginBottom: "1rem" }}>
                {compareResult.species_b.latin_name}
              </div>
              <p style={{ fontSize: "0.9rem", lineHeight: "1.6", color: "#d1d5db" }}>
                {compareResult.species_b.description}
              </p>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

