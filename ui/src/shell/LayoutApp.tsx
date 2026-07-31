"use client";

// 탭 셸 본체 — 모든 탭을 동시에 mount 하고 CSS 로 전환한다 (상태 보존).
// 앱 결합(테마 store·i18n·서버 컨텍스트)은 전부 props 주입:
//   header  — 상단 네비 헤더 (앱 컴포넌트)
//   onBoot  — 최초 mount 훅 (persist rehydrate·i18n hydrate 등)
//   wrapTab — 탭 콘텐츠 래핑 (멀티서버 앱의 ServerProvider 등)

import dynamic from "next/dynamic";
import { useEffect, useRef, useState, type ReactNode } from "react";
import { X } from "lucide-react";
import { useTabStore, type Tab } from "./tabs";
import { TabProvider } from "./tab-context";
import { cn } from "../ui/utils";
import { ConfirmDialog } from "../ui/ConfirmDialog";

const Toaster = dynamic(() => import("sonner").then((m) => ({ default: m.Toaster })), { ssr: false });

export interface LeaveGuardText {
  title: string;
  message: string;
  confirmLabel: string;
  cancelLabel: string;
}

const DEFAULT_LEAVE_GUARD: LeaveGuardText = {
  title: "페이지 이탈",
  message: "화면에서 나가시겠습니까? 작업 중이던 내용이 사라질 수 있습니다.",
  confirmLabel: "나가기",
  cancelLabel: "머물기",
};

export interface LayoutAppProps {
  /** 라우트 경로 → 탭에 렌더할 컴포넌트 매핑 */
  tabComponents: Record<string, React.ComponentType>;
  /** 최초 진입 시 탭이 비어 있으면 자동으로 열 탭 */
  initialTab?: Pick<Tab, "id" | "path" | "label">;
  /** 뒤로가기 가드 활성화 (SPA 이탈 방지) */
  backGuard?: boolean;
  /** 상단 네비 헤더 (앱 주입) */
  header?: ReactNode;
  /** Toaster 테마 (앱 store 주입) */
  theme?: "dark" | "light";
  /** 최초 mount 훅 — persist rehydrate·i18n hydrate 등 앱 초기화 */
  onBoot?: () => void;
  /** 탭 콘텐츠 래핑 — 멀티서버 앱의 ServerProvider 주입 지점 */
  wrapTab?: (tab: Tab, node: ReactNode) => ReactNode;
  /** 이탈 가드 문구 (기본 한국어) */
  leaveGuard?: LeaveGuardText;
}

function getTabComponent(
  tab: Tab,
  tabComponents: Record<string, React.ComponentType>,
  wrapTab?: (tab: Tab, node: ReactNode) => ReactNode,
): ReactNode {
  const Component = tabComponents[tab.path];
  if (!Component) {
    return (
      <div className="h-full flex items-center justify-center text-muted-foreground text-sm">
        {tab.label} — 준비 중
      </div>
    );
  }
  const node = <Component />;
  return wrapTab ? wrapTab(tab, node) : node;
}

export function LayoutApp({
  tabComponents, initialTab, backGuard, header, theme, onBoot, wrapTab,
  leaveGuard = DEFAULT_LEAVE_GUARD,
}: LayoutAppProps) {
  const { tabs, activeTabId, setActiveTab, closeTab, openTab } = useTabStore();
  const [showLeaveGuard, setShowLeaveGuard] = useState(false);
  const pendingLeaveRef = useRef(false);
  const bootRef = useRef(onBoot);
  bootRef.current = onBoot;

  useEffect(() => {
    bootRef.current?.();
  }, []);

  useEffect(() => {
    if (!initialTab) return;
    if (tabs.length === 0) openTab(initialTab);
  }, [initialTab, tabs.length, openTab]);

  useEffect(() => {
    if (!backGuard) return;
    pendingLeaveRef.current = false;
    window.history.pushState({ wmGuard: true }, "", window.location.href);

    const onPop = () => {
      if (pendingLeaveRef.current) return;
      // 탐색 차단을 위해 state를 다시 push
      window.history.pushState({ wmGuard: true }, "", window.location.href);
      setShowLeaveGuard(true);
    };

    window.addEventListener("popstate", onPop);
    return () => window.removeEventListener("popstate", onPop);
  }, [backGuard]);

  const activeTab = tabs.find((t) => t.id === activeTabId);

  return (
    <>
      <Toaster position="bottom-right" richColors theme={theme} duration={2000} />
      <ConfirmDialog
        open={showLeaveGuard}
        title={leaveGuard.title}
        message={leaveGuard.message}
        confirmLabel={leaveGuard.confirmLabel}
        cancelLabel={leaveGuard.cancelLabel}
        variant="default"
        onConfirm={() => {
          pendingLeaveRef.current = true;
          setShowLeaveGuard(false);
          window.history.go(-2);
        }}
        onClose={() => setShowLeaveGuard(false)}
      />
      <div className="h-dvh flex flex-col overflow-hidden bg-background text-foreground">
        {header}

        {tabs.length > 0 && (
          <div className="shrink-0 border-b border-border bg-card flex items-center overflow-x-auto">
            {tabs.map((tab) => (
              <div
                key={tab.id}
                className={cn(
                  "flex items-center gap-1 px-3 h-8 text-xs cursor-pointer border-b-2 transition-colors shrink-0",
                  tab.id === activeTabId
                    ? "border-primary text-foreground font-medium bg-background"
                    : "border-transparent text-muted-foreground hover:text-foreground hover:bg-accent/50",
                )}
              >
                <span onClick={() => setActiveTab(tab.id)}>{tab.label}</span>
                <button
                  onClick={(e) => { e.stopPropagation(); closeTab(tab.id); }}
                  className="ml-1 rounded hover:bg-accent p-0.5"
                >
                  <X className="h-3 w-3" />
                </button>
              </div>
            ))}
          </div>
        )}

        <main className="flex-1 min-h-0 overflow-hidden">
          {activeTab ? (
            <div className="h-full">
              {tabs.map((tab) => (
                <div key={tab.id} className={cn("h-full", tab.id === activeTabId ? "block" : "hidden")}>
                  <TabProvider tabId={tab.id}>
                    {getTabComponent(tab, tabComponents, wrapTab)}
                  </TabProvider>
                </div>
              ))}
            </div>
          ) : (
            <div className="h-full flex items-center justify-center text-muted-foreground text-sm" />
          )}
        </main>
      </div>
    </>
  );
}
