import { ReactNode, useEffect } from "react";
import { cn } from "../ui/utils";
import { useSidebarToggleStore } from "./sidebar-toggle";
import { useTabId } from "./tab-context";
import { useTabStore } from "./tabs";

interface LayoutContentHeaderProps {
  onToggleSidebar?: () => void;
  children?: ReactNode;
  className?: string;
}

export function LayoutContentHeader({ onToggleSidebar, children, className }: LayoutContentHeaderProps) {
  const setToggle = useSidebarToggleStore((s) => s.setToggle);
  // 모든 탭이 동시에 mount + CSS 로 숨겨지므로, 자기 탭이 활성일 때만
  // 글로벌 헤더에 toggle 을 등록한다. tab 컨텍스트 밖에서 쓰일 때는 무조건 활성.
  const myTabId = useTabId();
  const activeTabId = useTabStore((s) => s.activeTabId);
  const isActiveTab = myTabId === null || myTabId === activeTabId;

  useEffect(() => {
    if (!onToggleSidebar) return;
    if (!isActiveTab) return;
    setToggle(onToggleSidebar);
    return () => setToggle(null);
  }, [onToggleSidebar, isActiveTab, setToggle]);

  return (
    <div className={cn("bg-card/80 backdrop-blur-md shrink-0 border-b border-border px-4 min-h-10 sm:h-10 py-1 sm:py-0 flex flex-wrap sm:flex-nowrap items-center gap-2 relative z-40", className)}>
      {children}
    </div>
  );
}

LayoutContentHeader.Left = function LayoutContentHeaderLeft({ children, className }: { children?: ReactNode; className?: string }) {
  return <div className={cn("flex items-center gap-1 shrink-0", className)}>{children}</div>;
};

LayoutContentHeader.Main = function LayoutContentHeaderMain({ children, className }: { children?: ReactNode; className?: string }) {
  return <div className={cn("flex items-center gap-1 flex-1 overflow-x-auto", className)}>{children}</div>;
};

LayoutContentHeader.Right = function LayoutContentHeaderRight({ children, className }: { children?: ReactNode; className?: string }) {
  return <div className={cn("ml-auto shrink-0 flex items-center gap-1", className)}>{children}</div>;
};
