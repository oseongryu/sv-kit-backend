"use client";
// 라우트 탭 셸 프레임 — 헤더 슬롯/탭바/본문(+iframe 스플릿)/푸터 슬롯 + 라우트→탭 누적.
// embed=1 쿼리 시 크롬 없이 본문만 렌더(iframe 임베드용).
// 앱 결합(테마·모달·메뉴 해석)은 전부 주입: header/modals 노드, resolveLabel, onBoot.
import React, { useEffect, useState, type ReactNode } from "react";
import { usePathname, useRouter } from "next/navigation";
import { ExternalLink, X } from "lucide-react";
import { RouteTabBar } from "./RouteTabBar";
import SplitPane from "./SplitPane";
import type { RouteTabsStore } from "./route-tabs";

export interface RouteAppShellProps {
  store: RouteTabsStore;
  /** 경로 → 탭/스플릿 라벨 해석 (앱 메뉴 데이터 기반) */
  resolveLabel: (path: string) => string;
  /** 상단 헤더 (앱 주입 — 모달 열기 핸들러는 앱 wrapper 가 소유) */
  header?: ReactNode;
  /** 본문 하단 푸터 */
  footer?: ReactNode;
  /** 프레임 뒤에 렌더할 모달들 (메뉴/팔레트/설정 — 앱 소유) */
  modals?: ReactNode;
  /** 최초 mount 훅 — persist rehydrate 등. 실행 완료 후 탭 누적이 시작된다. */
  onBoot?: () => void;
  /** 스플릿 비율 persist 키 */
  splitStorageKey?: string;
  children: ReactNode;
}

export function RouteAppShell({
  store, resolveLabel, header, footer, modals, onBoot,
  splitStorageKey = "route-shell-split", children,
}: RouteAppShellProps) {
  const pathname = usePathname();
  const router = useRouter();
  const [hydrated, setHydrated] = useState(false);
  const [embed, setEmbed] = useState(false);

  const openTab = store((s) => s.openTab);
  const splitPath = store((s) => s.splitPath);
  const setSplitPath = store((s) => s.setSplitPath);

  // embed 판정 (useSearchParams 금지 — Suspense 이슈). mount 후 1회.
  useEffect(() => {
    setEmbed(new URLSearchParams(window.location.search).get("embed") === "1");
  }, []);

  // persist rehydrate (skipHydration 패턴) — 앱 스토어 rehydrate 는 onBoot 로 주입
  const bootRef = React.useRef(onBoot);
  bootRef.current = onBoot;
  useEffect(() => {
    store.persist.rehydrate();
    bootRef.current?.();
    setHydrated(true);
  }, [store]);

  // 라우트 변화 → 탭 누적 ("/" 는 제외). embed 모드에서는 실행하지 않음.
  useEffect(() => {
    if (!hydrated || embed) return;
    if (!pathname || pathname === "/") return;
    openTab({ id: pathname, path: pathname, label: resolveLabel(pathname) });
  }, [pathname, hydrated, embed, openTab, resolveLabel]);

  // embed 모드: 크롬 없이 본문만.
  if (embed) {
    return <main style={{ minHeight: "100vh", padding: 24 }}>{children}</main>;
  }

  const mainPane = <main style={{ flex: 1, padding: 24, minWidth: 0, overflow: "auto" }}>{children}</main>;

  const splitRightPane = splitPath ? (
    <div style={{ display: "flex", flexDirection: "column", height: "100%", minWidth: 0, borderLeft: "1px solid var(--border)" }}>
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: 6,
          height: 28,
          flexShrink: 0,
          padding: "0 8px",
          background: "var(--panel)",
          borderBottom: "1px solid var(--border)",
          fontSize: 12,
        }}
      >
        <span style={{ flex: 1, minWidth: 0, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis", color: "var(--text)" }}>
          {resolveLabel(splitPath)}
        </span>
        <button
          type="button"
          title="새 탭으로 열기"
          aria-label="새 탭으로 열기"
          onClick={() => router.push(splitPath)}
          style={{ border: "none", background: "transparent", color: "var(--muted)", cursor: "pointer", display: "inline-flex", padding: 2 }}
        >
          <ExternalLink size={14} />
        </button>
        <button
          type="button"
          title="스플릿 닫기"
          aria-label="스플릿 닫기"
          onClick={() => setSplitPath(null)}
          style={{ border: "none", background: "transparent", color: "var(--muted)", cursor: "pointer", display: "inline-flex", padding: 2 }}
        >
          <X size={14} />
        </button>
      </div>
      <iframe
        src={splitPath + "?embed=1"}
        title={resolveLabel(splitPath)}
        style={{ border: 0, width: "100%", height: "100%", flex: 1, background: "var(--bg)" }}
      />
    </div>
  ) : null;

  return (
    <>
      <div style={{ display: "flex", flexDirection: "column", minHeight: "100vh", height: "100vh" }}>
        {header}
        <RouteTabBar store={store} />
        <div style={{ display: "flex", flex: 1, minHeight: 0 }}>
          <div style={{ flex: 1, display: "flex", flexDirection: "column", minWidth: 0 }}>
            {splitPath ? (
              <div style={{ flex: 1, minHeight: 0 }}>
                <SplitPane storageKey={splitStorageKey} initial={50}>
                  {mainPane}
                  {splitRightPane}
                </SplitPane>
              </div>
            ) : (
              mainPane
            )}
            {footer}
          </div>
        </div>
      </div>
      {modals}
    </>
  );
}
