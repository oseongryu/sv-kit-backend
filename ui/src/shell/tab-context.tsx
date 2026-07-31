"use client";

import { createContext, useContext, type ReactNode } from "react";

// 탭 컨텐츠 트리에 자기 tabId 를 주입한다. 모든 탭이 동시에 mount + CSS 로
// 숨겨지는 구조라 (LayoutApp), 화면 안의 hook 들이 "내가 어느 탭에 속한
// 컴포넌트인지" 알아야 활성 탭에서만 동작하게 만들 수 있다.
//
// 예: LayoutContentHeader 가 sidebar toggle 을 글로벌 헤더에 등록할 때,
//     자기 탭이 active 일 때만 등록해야 다른 탭이 덮어쓰지 않는다.

const TabContext = createContext<string | null>(null);

export function TabProvider({ tabId, children }: { tabId: string; children: ReactNode }) {
  return <TabContext.Provider value={tabId}>{children}</TabContext.Provider>;
}

/** 현재 컴포넌트가 속한 탭 id. 탭 컨텍스트 밖에서 호출되면 null. */
export function useTabId(): string | null {
  return useContext(TabContext);
}
