import React, { useMemo, useState } from "react";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
  AreaChart,
  Area,
} from "recharts";
import { TurnReport } from "../services/api.types";
import { GamePanel } from "./common/GamePanel";

interface Props {
  reports: TurnReport[];
  onClose: () => void;
}

type Tab = "environment" | "biodiversity";

export function GlobalTrendsPanel({ reports, onClose }: Props) {
  const [activeTab, setActiveTab] = useState<Tab>("environment");

  // 预处理数据，提取图表所需的数值
  const chartData = useMemo(() => {
    return reports.map((r) => {
      // 计算总人口
      const totalPop = r.species.reduce((sum, s) => sum + s.population, 0);
      
      return {
        turn: r.turn_index,
        speciesCount: r.species.length,
        totalPop: totalPop,
        // 使用真实数据，如果后端暂未返回则回退到默认值
        temp: r.global_temperature ?? 15.0, 
        seaLevel: r.sea_level ?? 0.0,
      };
    });
  }, [reports]);

  return (
    <GamePanel
      title="全球趋势 (Global Trends)"
      onClose={onClose}
      variant="modal"
      width="900px"
    >
      {/* Tabs */}
      <div style={{ display: "flex", borderBottom: "1px solid rgba(255,255,255,0.1)", background: "rgba(0,0,0,0.2)" }}>
        <TabButton
          active={activeTab === "environment"}
          onClick={() => setActiveTab("environment")}
          label="环境气候"
        />
        <TabButton
          active={activeTab === "biodiversity"}
          onClick={() => setActiveTab("biodiversity")}
          label="生物多样性"
        />
      </div>

      {/* Content */}
      <div style={{ padding: "24px", height: "500px" }}>
        <ResponsiveContainer width="100%" height="100%">
          {activeTab === "environment" ? (
            <LineChart data={chartData}>
              <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.1)" />
              <XAxis dataKey="turn" stroke="#889" />
              <YAxis yAxisId="left" stroke="#889" label={{ value: '温度 (°C)', angle: -90, position: 'insideLeft', style: {fill: '#889'} }} />
              <YAxis yAxisId="right" orientation="right" stroke="#889" label={{ value: '海平面 (m)', angle: 90, position: 'insideRight', style: {fill: '#889'} }} />
              <Tooltip
                contentStyle={{ backgroundColor: "rgba(20, 25, 40, 0.9)", borderColor: "rgba(255,255,255,0.2)", color: "#eef" }}
                itemStyle={{ color: "#ccf" }}
              />
              <Legend />
              <Line
                yAxisId="left"
                type="monotone"
                dataKey="temp"
                name="全球均温"
                stroke="#ff7300"
                strokeWidth={2}
                dot={false}
              />
              <Line
                yAxisId="right"
                type="monotone"
                dataKey="seaLevel"
                name="海平面"
                stroke="#0088fe"
                strokeWidth={2}
                dot={false}
              />
            </LineChart>
          ) : (
            <AreaChart data={chartData}>
              <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.1)" />
              <XAxis dataKey="turn" stroke="#889" />
              <YAxis stroke="#889" />
              <Tooltip
                contentStyle={{ backgroundColor: "rgba(20, 25, 40, 0.9)", borderColor: "rgba(255,255,255,0.2)", color: "#eef" }}
              />
              <Legend />
              <Area
                type="monotone"
                dataKey="totalPop"
                name="总人口"
                stackId="1"
                stroke="#10b981"
                fill="#10b981"
                fillOpacity={0.3}
              />
              <Area
                type="monotone"
                dataKey="speciesCount"
                name="物种数量"
                stackId="2"
                stroke="#8b5cf6"
                fill="#8b5cf6"
                fillOpacity={0.3}
              />
            </AreaChart>
          )}
        </ResponsiveContainer>
      </div>
      
      <div style={{ 
        padding: "12px 24px", 
        fontSize: "0.85rem", 
        color: "rgba(255,255,255,0.4)", 
        borderTop: "1px solid rgba(255,255,255,0.1)",
        background: "rgba(0,0,0,0.2)"
      }}>
        数据来源: 历史回合报告 (History Reports)
      </div>
    </GamePanel>
  );
}

function TabButton({
  active,
  onClick,
  label,
}: {
  active: boolean;
  onClick: () => void;
  label: string;
}) {
  return (
    <button
      onClick={onClick}
      style={{
        flex: 1,
        padding: "16px",
        background: active ? "rgba(255,255,255,0.05)" : "transparent",
        border: "none",
        borderBottom: active ? "2px solid #3b82f6" : "2px solid transparent",
        color: active ? "#fff" : "rgba(255,255,255,0.5)",
        cursor: "pointer",
        transition: "all 0.2s",
        fontWeight: active ? 600 : 400,
        fontSize: "0.95rem"
      }}
    >
      {label}
    </button>
  );
}

