"use client";
// 방문 라우트 탭바 (h=32, 가로 스크롤). active 판정은 store 의 activeId 기준.
// 탭 클릭 → setActive + router.push(path). X → closeTab + (활성탭이었으면) 다음 path 로 이동.
// 탭은 고정폭(160)으로 일관 — 라벨은 말줄임, X 는 상시 노출. 스플릿 활성 시 우측 끝에 해제 버튼.
// 스타일은 CSS 변수(--panel/--border/--text/--muted/--accent/--bg) — 앱 테마를 그대로 따른다.
import React from "react";
import { useRouter } from "next/navigation";
import { X, Columns2 } from "lucide-react";
import type { RouteTabsStore } from "./route-tabs";

export function RouteTabBar({ store }: { store: RouteTabsStore }) {
  const router = useRouter();
  const tabs = store((s) => s.tabs);
  const activeId = store((s) => s.activeId);
  const setActive = store((s) => s.setActive);
  const closeTab = store((s) => s.closeTab);
  const splitPath = store((s) => s.splitPath);
  const setSplitPath = store((s) => s.setSplitPath);

  if (tabs.length === 0) return null;

  const onSelect = (id: string, path: string) => {
    setActive(id);
    router.push(path);
  };

  const onClose = (id: string, wasActive: boolean) => {
    const nextPath = closeTab(id);
    if (wasActive) router.push(nextPath ?? "/");
  };

  return (
    <div
      style={{
        display: "flex",
        alignItems: "stretch",
        height: 32,
        flexShrink: 0,
        background: "var(--panel)",
        borderBottom: "1px solid var(--border)",
        overflowX: "auto",
      }}
    >
      {tabs.map((tab) => {
        const active = tab.id === activeId;
        return (
          <div
            key={tab.id}
            onClick={() => onSelect(tab.id, tab.path)}
            title={tab.label}
            style={{
              display: "inline-flex",
              alignItems: "center",
              gap: 6,
              padding: "0 10px",
              width: 160,
              flexShrink: 0,
              cursor: "pointer",
              fontSize: 12,
              whiteSpace: "nowrap",
              color: active ? "var(--text)" : "var(--muted)",
              borderBottom: active ? "2px solid var(--accent)" : "2px solid transparent",
              borderRight: "1px solid var(--border)",
              background: active ? "var(--bg)" : "transparent",
            }}
          >
            <span style={{ flex: 1, minWidth: 0, overflow: "hidden", textOverflow: "ellipsis" }}>{tab.label}</span>
            <X
              size={13}
              style={{ opacity: 0.5, flexShrink: 0 }}
              onClick={(e) => {
                e.stopPropagation();
                onClose(tab.id, active);
              }}
              onMouseEnter={(e) => (e.currentTarget.style.opacity = "1")}
              onMouseLeave={(e) => (e.currentTarget.style.opacity = "0.5")}
            />
          </div>
        );
      })}

      <div style={{ flex: 1 }} />

      {splitPath && (
        <button
          type="button"
          title="스플릿 해제"
          aria-label="스플릿 해제"
          onClick={() => setSplitPath(null)}
          style={{
            display: "inline-flex",
            alignItems: "center",
            gap: 4,
            flexShrink: 0,
            padding: "0 10px",
            border: "none",
            borderLeft: "1px solid var(--border)",
            background: "transparent",
            color: "var(--accent)",
            cursor: "pointer",
            fontSize: 12,
          }}
        >
          <Columns2 size={13} />
          <X size={12} />
        </button>
      )}
    </div>
  );
}
