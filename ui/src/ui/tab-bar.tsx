"use client";

import { useRef, useState, useEffect, useCallback } from "react";
import { X, ChevronLeft, ChevronRight } from "lucide-react";
import { cn } from "./utils";

export interface TabItem {
  id: string;
  label: string;
  dirty?: boolean;
}

interface TabBarProps {
  tabs: TabItem[];
  activeId: string | null;
  onSelect: (id: string) => void;
  onClose?: (id: string) => void;
  onCloseAll?: () => void;
  onCloseOthers?: (id: string) => void;
  /** Active tab border+text color classes. Default: theme primary */
  activeColor?: string;
  actions?: React.ReactNode;
}

export function TabBar({ tabs, activeId, onSelect, onClose, onCloseAll, onCloseOthers, activeColor = "border-primary text-foreground", actions }: TabBarProps) {
  const scrollRef = useRef<HTMLDivElement>(null);
  const [canScrollLeft, setCanScrollLeft] = useState(false);
  const [canScrollRight, setCanScrollRight] = useState(false);
  const [contextMenu, setContextMenu] = useState<{ x: number; y: number; tabId: string } | null>(null);

  const updateScroll = useCallback(() => {
    const el = scrollRef.current;
    if (!el) return;
    setCanScrollLeft(el.scrollLeft > 0);
    setCanScrollRight(el.scrollLeft + el.clientWidth < el.scrollWidth - 1);
  }, []);

  useEffect(() => {
    const el = scrollRef.current;
    if (!el) return;
    updateScroll();
    el.addEventListener("scroll", updateScroll);
    const ro = new ResizeObserver(updateScroll);
    ro.observe(el);
    return () => { el.removeEventListener("scroll", updateScroll); ro.disconnect(); };
  }, [tabs, updateScroll]);

  // 외부 클릭으로 컨텍스트 메뉴 닫기
  useEffect(() => {
    if (!contextMenu) return;
    const handler = () => setContextMenu(null);
    document.addEventListener("click", handler);
    return () => document.removeEventListener("click", handler);
  }, [contextMenu]);

  const scroll = (dir: "left" | "right") => {
    const el = scrollRef.current;
    if (!el) return;
    el.scrollBy({ left: dir === "left" ? -120 : 120, behavior: "smooth" });
  };

  const handleContextMenu = (e: React.MouseEvent, tabId: string) => {
    e.preventDefault();
    setContextMenu({ x: e.clientX, y: e.clientY, tabId });
  };

  return (
    <div className="flex items-center border-b border-border shrink-0 bg-card/60 backdrop-blur-md relative z-30 supports-[backdrop-filter]:bg-card/40">
      <div ref={scrollRef} className="flex-1 flex items-center gap-0 overflow-x-auto" style={{ scrollbarWidth: "thin" }}>
        {tabs.map((tab) => (
          <div
            key={tab.id}
            className={cn(
              "flex items-center gap-1 px-3 py-1.5 text-xs cursor-pointer border-b-2 shrink-0 transition",
              activeId === tab.id
                ? `${activeColor} bg-accent`
                : "border-transparent text-muted-foreground hover:text-foreground"
            )}
            onClick={() => onSelect(tab.id)}
            onContextMenu={(e) => handleContextMenu(e, tab.id)}
          >
            <span>{tab.dirty ? `${tab.label} \u25CF` : tab.label}</span>
            {onClose && (
              <X
                className="h-3 w-3 opacity-40 hover:opacity-100 ml-1"
                onClick={(e) => { e.stopPropagation(); onClose(tab.id); }}
              />
            )}
          </div>
        ))}
      </div>
      <div className="flex items-center shrink-0 border-l border-border">
        <button
          className={cn("h-6 w-5 flex items-center justify-center transition", canScrollLeft ? "text-foreground hover:bg-accent" : "text-muted-foreground/30 cursor-default")}
          onClick={() => canScrollLeft && scroll("left")}
          tabIndex={-1}
        >
          <ChevronLeft className="h-3 w-3" />
        </button>
        <button
          className={cn("h-6 w-5 flex items-center justify-center transition", canScrollRight ? "text-foreground hover:bg-accent" : "text-muted-foreground/30 cursor-default")}
          onClick={() => canScrollRight && scroll("right")}
          tabIndex={-1}
        >
          <ChevronRight className="h-3 w-3" />
        </button>
        {actions && (
          <div className="flex items-center gap-1 px-1 border-l border-border">
            {actions}
          </div>
        )}
      </div>

      {/* 우클릭 컨텍스트 메뉴 */}
      {contextMenu && (
        <div
          className="fixed bg-popover border border-border rounded-lg shadow-lg z-[100] py-1 min-w-[140px]"
          style={{ left: contextMenu.x, top: contextMenu.y }}
        >
          {onClose && (
            <button
              className="w-full text-left px-3 py-1.5 text-xs hover:bg-accent transition"
              onClick={() => { onClose(contextMenu.tabId); setContextMenu(null); }}
            >
              탭 닫기
            </button>
          )}
          {onCloseOthers && tabs.length > 1 && (
            <button
              className="w-full text-left px-3 py-1.5 text-xs hover:bg-accent transition"
              onClick={() => { onCloseOthers(contextMenu.tabId); setContextMenu(null); }}
            >
              다른 탭 모두 닫기
            </button>
          )}
          {onCloseAll && tabs.length > 0 && (
            <button
              className="w-full text-left px-3 py-1.5 text-xs hover:bg-accent transition text-destructive"
              onClick={() => { onCloseAll(); setContextMenu(null); }}
            >
              모든 탭 닫기
            </button>
          )}
        </div>
      )}
    </div>
  );
}
