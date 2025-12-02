/**
 * useTrendsData Hook 测试
 */

import { describe, it, expect, vi } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { useTrendsData } from '@/components/GlobalTrendsPanel/hooks/useTrendsData';
import type { TurnReport } from '@/services/api.types';

// Mock 报告数据
const mockReports: TurnReport[] = [
  {
    turn_index: 1,
    global_temperature: 20.0,
    global_humidity: 50,
    sea_level: 0,
    species: [
      {
        lineage_code: 'A',
        common_name: 'Species A',
        status: 'alive',
        population: 1000,
        ecological_role: 'producer',
      },
    ],
    branching_events: [],
  },
  {
    turn_index: 2,
    global_temperature: 21.0,
    global_humidity: 52,
    sea_level: 1,
    species: [
      {
        lineage_code: 'A',
        common_name: 'Species A',
        status: 'alive',
        population: 1200,
        ecological_role: 'producer',
      },
      {
        lineage_code: 'B',
        common_name: 'Species B',
        status: 'alive',
        population: 500,
        ecological_role: 'herbivore',
      },
    ],
    branching_events: [{ parent: 'A', child: 'B' }],
  },
];

describe('useTrendsData', () => {
  it('初始化时 activeTab 应为 environment', () => {
    const { result } = renderHook(() => useTrendsData({ reports: mockReports }));
    
    expect(result.current.activeTab).toBe('environment');
  });

  it('应正确计算统计摘要', () => {
    const { result } = renderHook(() => useTrendsData({ reports: mockReports }));
    
    const stats = result.current.summaryStats;
    expect(stats.temp).toBe(21.0);
    expect(stats.tempDelta).toBe(1.0);
    expect(stats.species).toBe(2);
    expect(stats.speciesDelta).toBe(1);
  });

  it('切换标签页应更新 activeTab', () => {
    const { result } = renderHook(() => useTrendsData({ reports: mockReports }));
    
    act(() => {
      result.current.setActiveTab('biodiversity');
    });
    
    expect(result.current.activeTab).toBe('biodiversity');
  });

  it('切换时间范围应筛选报告', () => {
    const manyReports = Array.from({ length: 30 }, (_, i) => ({
      turn_index: i + 1,
      global_temperature: 20 + i * 0.1,
      species: [],
    })) as TurnReport[];

    const { result } = renderHook(() => useTrendsData({ reports: manyReports }));
    
    // 默认显示全部
    expect(result.current.filteredReports.length).toBe(30);
    
    // 切换到最近10回合
    act(() => {
      result.current.setTimeRange('10');
    });
    
    expect(result.current.filteredReports.length).toBe(10);
  });

  it('getTrendDirection 应正确判断趋势', () => {
    const { result } = renderHook(() => useTrendsData({ reports: mockReports }));
    
    expect(result.current.getTrendDirection(10, 5)).toBe('up');
    expect(result.current.getTrendDirection(5, 10)).toBe('down');
    expect(result.current.getTrendDirection(10, 10)).toBe('neutral');
  });

  it('空报告应返回默认统计', () => {
    const { result } = renderHook(() => useTrendsData({ reports: [] }));
    
    const stats = result.current.summaryStats;
    expect(stats.temp).toBe(0);
    expect(stats.species).toBe(0);
    expect(stats.population).toBe(0);
  });

  it('环境数据应包含正确的字段', () => {
    const { result } = renderHook(() => useTrendsData({ reports: mockReports }));
    
    const envData = result.current.environmentData;
    expect(envData.length).toBe(2);
    expect(envData[0]).toHaveProperty('turn');
    expect(envData[0]).toHaveProperty('temperature');
    expect(envData[0]).toHaveProperty('humidity');
    expect(envData[0]).toHaveProperty('sea_level');
  });

  it('角色分布应正确聚合', () => {
    const { result } = renderHook(() => useTrendsData({ reports: mockReports }));
    
    const roles = result.current.roleDistribution;
    expect(roles.length).toBe(2);
    expect(roles.find(r => r.name === 'producer')?.value).toBe(1);
    expect(roles.find(r => r.name === 'herbivore')?.value).toBe(1);
  });
});

