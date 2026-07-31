"use client";

import { useRef, useCallback, useState, useEffect, type ReactNode } from "react";

interface SplitPaneProps {
  layout: "lr" | "rl" | "tb" | "bt";
  terminalOpen: boolean;
  children: [ReactNode, ReactNode]; // [mainContent, terminalPanel]
}

const STORAGE_KEY = "wm-split-size";

export function SplitPane({ layout, terminalOpen, children }: SplitPaneProps) {
  const isVertical = layout === "tb" || layout === "bt";
  const reversed = layout === "rl" || layout === "bt";
  const containerRef = useRef<HTMLDivElement>(null);
  const dragging = useRef(false);

  // Terminal size as percentage — SSR-safe default, hydrate on mount
  const [termSize, setTermSize] = useState(40);

  useEffect(() => {
    const saved = localStorage.getItem(STORAGE_KEY);
    if (saved) setTermSize(parseFloat(saved));
  }, []);

  // Save to localStorage on change
  useEffect(() => {
    localStorage.setItem(STORAGE_KEY, String(termSize));
  }, [termSize]);

  const handleMouseDown = useCallback((e: React.MouseEvent) => {
    e.preventDefault();
    dragging.current = true;

    const onMove = (ev: MouseEvent) => {
      if (!dragging.current || !containerRef.current) return;
      const rect = containerRef.current.getBoundingClientRect();
      let ratio: number;

      if (isVertical) {
        const y = ev.clientY - rect.top;
        ratio = reversed ? (y / rect.height) * 100 : ((rect.height - y) / rect.height) * 100;
      } else {
        const x = ev.clientX - rect.left;
        ratio = reversed ? (x / rect.width) * 100 : ((rect.width - x) / rect.width) * 100;
      }

      setTermSize(Math.max(10, Math.min(80, ratio)));
    };

    const onUp = () => {
      dragging.current = false;
      document.removeEventListener("mousemove", onMove);
      document.removeEventListener("mouseup", onUp);
    };

    document.addEventListener("mousemove", onMove);
    document.addEventListener("mouseup", onUp);
  }, [isVertical, reversed]);

  const handleTouchStart = useCallback((e: React.TouchEvent) => {
    dragging.current = true;

    const onMove = (ev: TouchEvent) => {
      if (!dragging.current || !containerRef.current) return;
      const touch = ev.touches[0];
      const rect = containerRef.current.getBoundingClientRect();
      let ratio: number;

      if (isVertical) {
        const y = touch.clientY - rect.top;
        ratio = reversed ? (y / rect.height) * 100 : ((rect.height - y) / rect.height) * 100;
      } else {
        const x = touch.clientX - rect.left;
        ratio = reversed ? (x / rect.width) * 100 : ((rect.width - x) / rect.width) * 100;
      }

      setTermSize(Math.max(10, Math.min(80, ratio)));
    };

    const onEnd = () => {
      dragging.current = false;
      document.removeEventListener("touchmove", onMove);
      document.removeEventListener("touchend", onEnd);
    };

    document.addEventListener("touchmove", onMove);
    document.addEventListener("touchend", onEnd);
  }, [isVertical, reversed]);

  const mainStyle: React.CSSProperties = {
    order: reversed ? 2 : 1,
    flex: terminalOpen ? `1 1 ${100 - termSize}%` : "1 1 100%",
    minWidth: 0,
    minHeight: 0,
    overflow: "hidden",
  };

  const termStyle: React.CSSProperties = {
    order: reversed ? 1 : 2,
    ...(isVertical
      ? { height: `${termSize}%`, minHeight: 50 }
      : { width: `${termSize}%`, minWidth: 80 }),
    overflow: "hidden",
  };

  const handleStyle: React.CSSProperties = {
    order: reversed ? (isVertical ? 3 : 3) : (isVertical ? 2 : 2),
    // fix: handle always between the two panels
  };
  // Recalculate order: main=1or3, handle=2, term=3or1
  const mainOrder = reversed ? 3 : 1;
  const handleOrder = 2;
  const termOrder = reversed ? 1 : 3;

  return (
    <div
      ref={containerRef}
      className="h-full flex overflow-hidden"
      style={{ flexDirection: isVertical ? "column" : "row" }}
    >
      {/* Main content */}
      <div style={{ ...mainStyle, order: mainOrder }}>
        {children[0]}
      </div>

      {/* Drag handle */}
      {terminalOpen && (
        <div
          style={{ order: handleOrder }}
          className={`shrink-0 bg-border hover:bg-primary transition-colors ${
            isVertical
              ? "h-[3px] cursor-row-resize w-full"
              : "w-[3px] cursor-col-resize h-full"
          }`}
          onMouseDown={handleMouseDown}
          onTouchStart={handleTouchStart}
        />
      )}

      {/* Terminal - always mounted */}
      <div
        className={terminalOpen ? "" : "hidden"}
        style={{ ...termStyle, order: termOrder }}
      >
        {children[1]}
      </div>
    </div>
  );
}
