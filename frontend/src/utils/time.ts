/**
 * 动态时间流 (Chronos Flow) - 前端工具
 * 
 * 与后端 backend/app/simulation/constants.py 的 ERA_TIMELINE 保持同步
 */

// 起始年份：28亿年前
const START_YEAR = -2_800_000_000;

// 基准步长（用于计算倍率）
const BASE_YEARS_PER_TURN = 500_000;

// 时代配置表（与后端 backend/app/simulation/constants.py 同步）
// 设计目标：前期快进，阶梯式减速 100万→50万→25万年/回合，总计约920回合
const ERA_TIMELINE = [
  {
    end_year: -2_500_000_000,
    name: "太古宙",
    name_en: "Archean",
    years_per_turn: 20_000_000,  // 2000万年/回合，约15回合
  },
  {
    end_year: -541_000_000,
    name: "元古宙",
    name_en: "Proterozoic",
    years_per_turn: 50_000_000,  // 5000万年/回合，约39回合
  },
  {
    end_year: -252_000_000,
    name: "古生代",
    name_en: "Paleozoic",
    years_per_turn: 1_000_000,   // 100万年/回合，约289回合 ⭐重点
  },
  {
    end_year: -66_000_000,
    name: "中生代",
    name_en: "Mesozoic",
    years_per_turn: 500_000,     // 50万年/回合，约372回合
  },
  {
    end_year: 0,
    name: "新生代",
    name_en: "Cenozoic",
    years_per_turn: 250_000,     // 25万年/回合，约264回合
  },
];

export interface TimeConfig {
  currentYear: number;
  yearsPerTurn: number;
  eraName: string;
  eraNameEn: string;
  scalingFactor: number;
}

/**
 * 根据回合数计算当前时间配置
 */
export function getTimeConfig(turnIndex: number): TimeConfig {
  let currentYear = START_YEAR;
  let remainingTurns = turnIndex;
  
  let activeConfig = ERA_TIMELINE[ERA_TIMELINE.length - 1];
  
  for (const config of ERA_TIMELINE) {
    const eraDuration = config.end_year - currentYear;
    if (eraDuration <= 0) continue;
    
    const eraTurns = Math.floor(eraDuration / config.years_per_turn);
    
    if (remainingTurns < eraTurns) {
      currentYear += remainingTurns * config.years_per_turn;
      activeConfig = config;
      break;
    } else {
      currentYear = config.end_year;
      remainingTurns -= eraTurns;
      
      if (config === ERA_TIMELINE[ERA_TIMELINE.length - 1]) {
        currentYear += remainingTurns * config.years_per_turn;
        activeConfig = config;
      }
    }
  }
  
  return {
    currentYear,
    yearsPerTurn: activeConfig.years_per_turn,
    eraName: activeConfig.name,
    eraNameEn: activeConfig.name_en,
    scalingFactor: activeConfig.years_per_turn / BASE_YEARS_PER_TURN,
  };
}

/**
 * 格式化年份显示
 */
export function formatYear(year: number): string {
  const absYear = Math.abs(year);
  
  if (absYear >= 1_000_000_000) {
    // 亿年 - 使用2位小数以显示百万年级别的变化
    const billions = absYear / 100_000_000;
    // 如果是整数或接近整数，显示1位小数；否则显示2位
    const formatted = billions % 1 < 0.01 ? billions.toFixed(1) : billions.toFixed(2);
    return `${formatted} 亿年前`;
  } else if (absYear >= 10_000_000) {
    // 千万年
    return `${(absYear / 10_000_000).toFixed(1)} 千万年前`;
  } else if (absYear >= 1_000_000) {
    // 百万年
    return `${(absYear / 1_000_000).toFixed(1)} 百万年前`;
  } else if (absYear >= 10_000) {
    // 万年
    return `${(absYear / 10_000).toFixed(1)} 万年前`;
  } else if (year < 0) {
    return `${absYear} 年前`;
  } else {
    return `公元 ${year} 年`;
  }
}

/**
 * 格式化每回合年数
 */
export function formatYearsPerTurn(years: number): string {
  if (years >= 1_000_000) {
    return `${(years / 1_000_000).toFixed(0)} 百万年/回合`;
  } else if (years >= 10_000) {
    return `${(years / 10_000).toFixed(0)} 万年/回合`;
  } else {
    return `${years} 年/回合`;
  }
}

