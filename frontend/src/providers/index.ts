/**
 * Providers 统一导出
 * 
 * 使用方式：
 * 
 * ```tsx
 * import { SessionProvider, GameProvider, UIProvider, useSession, useGame, useUI } from './providers';
 * 
 * function App() {
 *   return (
 *     <SessionProvider>
 *       <UIProvider>
 *         <GameProviderWrapper>
 *           <AppContent />
 *         </GameProviderWrapper>
 *       </UIProvider>
 *     </SessionProvider>
 *   );
 * }
 * ```
 */

// Providers
export { SessionProvider, useSession, SessionContext } from "./SessionProvider";
export { GameProvider, useGame, GameContext } from "./GameProvider";
export { UIProvider, useUI, UIContext } from "./UIProvider";
export { QueryProvider, queryClient, queryKeys } from "./QueryProvider";

// Types
export type {
  Scene,
  SessionState,
  SessionActions,
  GameDataState,
  GameDataActions,
  OverlayView,
  DrawerMode,
  UIState,
  UIActions,
  AppState,
  AppActions,
} from "./types";

