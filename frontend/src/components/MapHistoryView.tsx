import { useEffect, useState } from "react";
import type { TurnReport } from "../services/api.types";
import { fetchHistory } from "../services/api";
import { X } from "lucide-react";

interface Props {
  onClose: () => void;
}

export function MapHistoryView({ onClose }: Props) {
  const [reports, setReports] = useState<TurnReport[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedTurn, setSelectedTurn] = useState<number | null>(null);

  useEffect(() => {
    fetchHistory(50)
      .then((data) => {
        const sorted = data.slice().sort((a, b) => a.turn_index - b.turn_index);
        setReports(sorted);
        if (sorted.length > 0) {
          setSelectedTurn(sorted[sorted.length - 1].turn_index);
        }
      })
      .catch(console.error)
      .finally(() => setLoading(false));
  }, []);

  const selectedReport = selectedTurn !== null 
    ? reports.find(r => r.turn_index === selectedTurn) 
    : null;

  if (loading) {
    return (
      <div style={{
        position: "fixed",
        top: 0,
        left: 0,
        right: 0,
        bottom: 0,
        background: "rgba(0, 0, 0, 0.9)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        zIndex: 10000
      }}>
        <div style={{ color: "#fff", fontSize: "1.2rem" }}>加载地图历史...</div>
      </div>
    );
  }

  return (
    <div style={{
      position: "fixed",
      top: 0,
      left: 0,
      right: 0,
      bottom: 0,
      background: "rgba(0, 0, 0, 0.9)",
      zIndex: 10000,
      backdropFilter: "blur(8px)"
    }}>
      <div style={{
        height: "100%",
        display: "flex",
        flexDirection: "column",
        padding: "20px"
      }}>
        {/* Header */}
        <div style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          marginBottom: "24px"
        }}>
          <h1 style={{
            fontSize: "2rem",
            fontWeight: 700,
            color: "#fff",
            margin: 0
          }}>
            🌍 地图变迁历史
          </h1>
          <button
            onClick={onClose}
            style={{
              background: "rgba(255, 255, 255, 0.1)",
              border: "1px solid rgba(255, 255, 255, 0.2)",
              borderRadius: "12px",
              padding: "12px",
              cursor: "pointer",
              display: "flex",
              alignItems: "center",
              justifyContent: "center"
            }}
          >
            <X size={24} color="#fff" />
          </button>
        </div>

        {/* Content */}
        <div style={{
          flex: 1,
          display: "grid",
          gridTemplateColumns: "300px 1fr",
          gap: "24px",
          overflow: "hidden"
        }}>
          {/* Timeline Sidebar */}
          <div style={{
            background: "rgba(17, 24, 39, 0.8)",
            border: "1px solid rgba(255, 255, 255, 0.1)",
            borderRadius: "16px",
            padding: "20px",
            overflowY: "auto"
          }}>
            <h3 style={{
              fontSize: "1.2rem",
              fontWeight: 600,
              color: "#8b5cf6",
              marginBottom: "16px"
            }}>
              回合时间轴
            </h3>
            <div style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
              {reports.filter(r => r.map_changes.length > 0).reverse().map((report) => (
                <div
                  key={report.turn_index}
                  onClick={() => setSelectedTurn(report.turn_index)}
                  style={{
                    padding: "12px",
                    background: selectedTurn === report.turn_index 
                      ? "rgba(139, 92, 246, 0.2)" 
                      : "rgba(255, 255, 255, 0.03)",
                    border: `1px solid ${selectedTurn === report.turn_index ? 'rgba(139, 92, 246, 0.5)' : 'rgba(255, 255, 255, 0.1)'}`,
                    borderRadius: "8px",
                    cursor: "pointer",
                    transition: "all 0.2s"
                  }}
                  onMouseEnter={(e) => {
                    if (selectedTurn !== report.turn_index) {
                      e.currentTarget.style.background = "rgba(255, 255, 255, 0.05)";
                    }
                  }}
                  onMouseLeave={(e) => {
                    if (selectedTurn !== report.turn_index) {
                      e.currentTarget.style.background = "rgba(255, 255, 255, 0.03)";
                    }
                  }}
                >
                  <div style={{
                    fontSize: "1rem",
                    fontWeight: 600,
                    color: "#fff",
                    marginBottom: "4px"
                  }}>
                    回合 #{report.turn_index + 1}
                  </div>
                  <div style={{
                    fontSize: "0.85rem",
                    color: "rgba(255, 255, 255, 0.6)"
                  }}>
                    {report.map_changes.length} 个地质事件
                  </div>
                  <div style={{
                    fontSize: "0.75rem",
                    color: "rgba(255, 255, 255, 0.5)",
                    marginTop: "4px"
                  }}>
                    {report.tectonic_stage}
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Detail Panel */}
          <div style={{
            background: "rgba(17, 24, 39, 0.8)",
            border: "1px solid rgba(255, 255, 255, 0.1)",
            borderRadius: "16px",
            padding: "32px",
            overflowY: "auto"
          }}>
            {selectedReport ? (
              <>
                <div style={{ marginBottom: "32px" }}>
                  <h2 style={{
                    fontSize: "1.8rem",
                    fontWeight: 700,
                    color: "#fff",
                    marginBottom: "8px"
                  }}>
                    回合 #{selectedReport.turn_index + 1}
                  </h2>
                  <p style={{
                    fontSize: "1rem",
                    color: "rgba(255, 255, 255, 0.6)"
                  }}>
                    {selectedReport.tectonic_stage}
                  </p>
                </div>

                {/* Environment Stats */}
                <div style={{
                  display: "grid",
                  gridTemplateColumns: "repeat(3, 1fr)",
                  gap: "16px",
                  marginBottom: "32px"
                }}>
                  <StatBox
                    label="全球温度"
                    value={`${selectedReport.global_temperature.toFixed(1)}°C`}
                    icon="🌡️"
                    color="#f59e0b"
                  />
                  <StatBox
                    label="海平面"
                    value={`${selectedReport.sea_level.toFixed(0)}m`}
                    icon="🌊"
                    color="#06b6d4"
                  />
                  <StatBox
                    label="物种数量"
                    value={selectedReport.species.length}
                    icon="🧬"
                    color="#10b981"
                  />
                </div>

                {/* Map Changes */}
                <h3 style={{
                  fontSize: "1.3rem",
                  fontWeight: 600,
                  color: "#8b5cf6",
                  marginBottom: "16px"
                }}>
                  地质变化
                </h3>
                <div style={{
                  display: "flex",
                  flexDirection: "column",
                  gap: "16px"
                }}>
                  {selectedReport.map_changes.map((change, idx) => (
                    <div
                      key={idx}
                      style={{
                        background: "rgba(139, 92, 246, 0.05)",
                        border: "1px solid rgba(139, 92, 246, 0.3)",
                        borderRadius: "12px",
                        padding: "20px",
                        display: "flex",
                        gap: "16px"
                      }}
                    >
                      <div style={{
                        fontSize: "2.5rem",
                        flexShrink: 0
                      }}>
                        {getMapChangeIcon(change.change_type)}
                      </div>
                      <div style={{ flex: 1 }}>
                        <div style={{
                          fontSize: "1.1rem",
                          fontWeight: 600,
                          color: "#8b5cf6",
                          marginBottom: "8px"
                        }}>
                          {change.stage}
                        </div>
                        <div style={{
                          fontSize: "0.9rem",
                          color: "rgba(255, 255, 255, 0.7)",
                          marginBottom: "8px"
                        }}>
                          <strong style={{ color: "#fff" }}>影响区域：</strong>
                          {change.affected_region}
                        </div>
                        <div style={{
                          fontSize: "0.95rem",
                          color: "rgba(255, 255, 255, 0.9)",
                          lineHeight: "1.6"
                        }}>
                          {change.description}
                        </div>
                        <div style={{
                          display: "inline-block",
                          marginTop: "12px",
                          padding: "4px 12px",
                          background: "rgba(139, 92, 246, 0.2)",
                          border: "1px solid rgba(139, 92, 246, 0.4)",
                          borderRadius: "16px",
                          fontSize: "0.8rem",
                          color: "#c4b5fd"
                        }}>
                          {getChangeTypeName(change.change_type)}
                        </div>
                      </div>
                    </div>
                  ))}
                </div>

                {/* Major Events */}
                {selectedReport.major_events.length > 0 && (
                  <>
                    <h3 style={{
                      fontSize: "1.3rem",
                      fontWeight: 600,
                      color: "#f59e0b",
                      marginTop: "32px",
                      marginBottom: "16px"
                    }}>
                      重大环境事件
                    </h3>
                    <div style={{
                      display: "flex",
                      flexDirection: "column",
                      gap: "12px"
                    }}>
                      {selectedReport.major_events.map((event, idx) => (
                        <div
                          key={idx}
                          style={{
                            background: "rgba(245, 158, 11, 0.05)",
                            border: "1px solid rgba(245, 158, 11, 0.3)",
                            borderRadius: "12px",
                            padding: "16px",
                            display: "flex",
                            gap: "12px"
                          }}
                        >
                          <span style={{ fontSize: "1.5rem" }}>⚠️</span>
                          <div style={{ flex: 1 }}>
                            <div style={{
                              fontSize: "1rem",
                              fontWeight: 600,
                              color: "#f59e0b",
                              marginBottom: "4px"
                            }}>
                              {event.severity}
                            </div>
                            <div style={{
                              fontSize: "0.9rem",
                              color: "rgba(255, 255, 255, 0.8)"
                            }}>
                              {event.description}
                            </div>
                            <div style={{
                              fontSize: "0.8rem",
                              color: "rgba(255, 255, 255, 0.5)",
                              marginTop: "8px"
                            }}>
                              影响地块: {event.affected_tiles.length} 个
                            </div>
                          </div>
                        </div>
                      ))}
                    </div>
                  </>
                )}
              </>
            ) : (
              <div style={{
                height: "100%",
                display: "flex",
                flexDirection: "column",
                alignItems: "center",
                justifyContent: "center",
                color: "rgba(255, 255, 255, 0.4)"
              }}>
                <div style={{ fontSize: "4rem", marginBottom: "16px" }}>🌍</div>
                <div style={{ fontSize: "1.2rem" }}>
                  选择一个回合查看地图变化详情
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

function StatBox({ label, value, icon, color }: {
  label: string;
  value: string | number;
  icon: string;
  color: string;
}) {
  return (
    <div style={{
      background: "rgba(255, 255, 255, 0.03)",
      border: `1px solid ${color}40`,
      borderRadius: "12px",
      padding: "16px",
      display: "flex",
      flexDirection: "column",
      gap: "8px"
    }}>
      <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
        <span style={{ fontSize: "1.3rem" }}>{icon}</span>
        <span style={{ fontSize: "0.85rem", color: "rgba(255, 255, 255, 0.6)" }}>
          {label}
        </span>
      </div>
      <div style={{
        fontSize: "1.5rem",
        fontWeight: 700,
        color
      }}>
        {value}
      </div>
    </div>
  );
}

function getMapChangeIcon(changeType: string | undefined): string {
  if (!changeType) return "🌍";
  const icons: Record<string, string> = {
    uplift: "⛰️",
    erosion: "🌊",
    volcanic: "🌋",
    subsidence: "⬇️",
    glaciation: "❄️",
    warming: "🔥",
    cooling: "🧊",
    continental_drift: "🌏",
    earthquake: "💥",
    tsunami: "🌊",
    meteor: "☄️"
  };
  return icons[changeType] || "🌍";
}

function getChangeTypeName(changeType: string | undefined): string {
  if (!changeType) return "未知变化";
  const names: Record<string, string> = {
    uplift: "地壳隆起",
    erosion: "侵蚀作用",
    volcanic: "火山活动",
    subsidence: "地壳下沉",
    glaciation: "冰川运动",
    warming: "全球变暖",
    cooling: "全球变冷",
    continental_drift: "大陆漂移",
    earthquake: "地震",
    tsunami: "海啸",
    meteor: "陨石撞击"
  };
  return names[changeType] || changeType;
}

