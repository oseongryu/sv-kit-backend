// 라우트 기반 탭 상태 팩토리 — 방문한 라우트가 탭으로 쌓이고, 탭 클릭 = router.push.
// (컴포넌트 마운트형 shell/tabs 와 다른 의미론 — 페이지가 Next 라우트인 앱용.)
// persist 키는 앱이 지정한다 (기존 localStorage 데이터 유지).
import { create } from "zustand";
import { persist } from "zustand/middleware";

export interface RouteTab {
  id: string; // 고유 키 (= route)
  path: string; // nav path
  label: string; // 탭 표시 라벨
}

export interface RouteTabsState {
  tabs: RouteTab[];
  activeId: string | null;
  /** 우측 스플릿 패널에 임베드할 경로. null 이면 스플릿 비활성. */
  splitPath: string | null;
  openTab: (tab: RouteTab) => void;
  /** 닫은 뒤 활성화되어야 할 다음 탭의 path 를 반환(활성탭을 닫은 경우), 아니면 null. */
  closeTab: (id: string) => string | null;
  setActive: (id: string) => void;
  setSplitPath: (path: string | null) => void;
  /** 모든 탭·활성탭·스플릿을 초기화. */
  closeAll: () => void;
}

export function createRouteTabsStore(persistName: string) {
  return create<RouteTabsState>()(
    persist(
      (set, get) => ({
        tabs: [],
        activeId: null,
        splitPath: null,

        openTab: (tab) => {
          const { tabs } = get();
          const exists = tabs.find((t) => t.id === tab.id);
          if (exists) {
            set({ activeId: tab.id });
          } else {
            set({ tabs: [...tabs, tab], activeId: tab.id });
          }
        },

        closeTab: (id) => {
          const { tabs, activeId } = get();
          const idx = tabs.findIndex((t) => t.id === id);
          const next = tabs.filter((t) => t.id !== id);
          let nextActive = activeId;
          let nextPath: string | null = null;
          if (activeId === id) {
            const na = next[Math.min(idx, next.length - 1)] ?? null;
            nextActive = na?.id ?? null;
            nextPath = na?.path ?? null;
          }
          set({ tabs: next, activeId: nextActive });
          return nextPath;
        },

        setActive: (id) => set({ activeId: id }),

        setSplitPath: (path) => set({ splitPath: path }),

        closeAll: () => set({ tabs: [], activeId: null, splitPath: null }),
      }),
      { name: persistName, skipHydration: true }
    )
  );
}

export type RouteTabsStore = ReturnType<typeof createRouteTabsStore>;
