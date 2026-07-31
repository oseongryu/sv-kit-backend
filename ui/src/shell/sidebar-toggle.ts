import { create } from "zustand";

interface SidebarToggleState {
  toggle: (() => void) | null;
  setToggle: (fn: (() => void) | null) => void;
}

export const useSidebarToggleStore = create<SidebarToggleState>((set) => ({
  toggle: null,
  setToggle: (fn) => set({ toggle: fn }),
}));
