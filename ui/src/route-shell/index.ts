// @sv/kit-ui/route-shell — 라우트 기반 탭 셸 (페이지가 Next 라우트인 앱용).
// 컴포넌트 마운트형 ./shell 과 별개 의미론 — 방문 라우트가 탭으로 쌓인다.
// 스타일은 CSS 변수(--bg/--panel/--border/--text/--muted/--accent/--hover) 기반.
export {
  createRouteTabsStore,
  type RouteTab,
  type RouteTabsState,
  type RouteTabsStore,
} from "./route-tabs";
export { createUiStore, type Theme, type UiState, type UiStore } from "./ui-store";
export { RouteTabBar } from "./RouteTabBar";
export { RouteAppShell, type RouteAppShellProps } from "./RouteAppShell";
export { default as SplitPane } from "./SplitPane";
