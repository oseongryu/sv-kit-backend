import { create } from "zustand";

export interface Tab {
  id: string;          // 고유 키 (path 기반: "/at/jobs", "/test/1")
  path: string;        // nav path
  label: string;       // 탭 표시 라벨
  serviceUrl?: string | null; // 해당 탭의 백엔드 service URL
  // 서버 탭용 (path="/worktree" 일 때)
  serverId?: string;
  serverName?: string;
  wsUrl?: string;
}

interface TabState {
  tabs: Tab[];
  activeTabId: string | null;
  openTab: (tab: Tab) => void;
  closeTab: (id: string) => void;
  setActiveTab: (id: string) => void;
}

// 탭별 API는 ServerProvider + createScopedApi 로 각 탭 콘텐츠에 직접 주입된다.
// 전역 백엔드 URL(로그인 서버)을 탭 전환에 따라 바꿔서는 안 된다.
// 되돌려서 setCurrentPageServiceUrl 같은 전역 훅을 다시 심지 말 것.
export const useTabStore = create<TabState>((set, get) => ({
  tabs: [],
  activeTabId: null,

  openTab: (tab) => {
    const { tabs } = get();
    const exists = tabs.find((t) => t.id === tab.id);
    if (!exists) {
      set({ tabs: [...tabs, tab], activeTabId: tab.id });
    } else {
      set({ activeTabId: tab.id });
    }
  },

  closeTab: (id) => {
    const { tabs, activeTabId } = get();
    const next = tabs.filter((t) => t.id !== id);
    let nextActive = activeTabId;
    if (activeTabId === id) {
      const idx = tabs.findIndex((t) => t.id === id);
      nextActive = next[Math.min(idx, next.length - 1)]?.id ?? null;
    }
    set({ tabs: next, activeTabId: nextActive });
  },

  setActiveTab: (id) => {
    set({ activeTabId: id });
  },
}));
