/**
 * SettingsDrawer 模块导出
 */

// 新版设置面板
export { SettingsPanel } from "./SettingsPanel";
export { SettingsPanel as default } from "./SettingsPanel";

// 兼容旧的导入方式 - 现在指向新版
export { SettingsPanel as SettingsDrawer } from "./SettingsPanel";

// 类型导出
export * from "./types";
