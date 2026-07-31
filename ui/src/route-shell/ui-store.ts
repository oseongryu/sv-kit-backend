// 전역 UI 상태 팩토리 (테마/사이드바) — persist 키는 앱이 지정.
// SSG 안전을 위해 skipHydration:true; 셸 mount 시 rehydrate() 호출 전제.
import { create } from "zustand";
import { persist } from "zustand/middleware";

export type Theme = "dark" | "light";

export interface UiState {
  theme: Theme;
  sidebarCollapsed: boolean;
  toggleTheme: () => void;
  setTheme: (t: Theme) => void;
  toggleSidebar: () => void;
}

export function createUiStore(persistName: string) {
  return create<UiState>()(
    persist(
      (set) => ({
        theme: "dark",
        sidebarCollapsed: false,
        toggleTheme: () => set((s) => ({ theme: s.theme === "dark" ? "light" : "dark" })),
        setTheme: (t) => set({ theme: t }),
        toggleSidebar: () => set((s) => ({ sidebarCollapsed: !s.sidebarCollapsed })),
      }),
      { name: persistName, skipHydration: true }
    )
  );
}

export type UiStore = ReturnType<typeof createUiStore>;
