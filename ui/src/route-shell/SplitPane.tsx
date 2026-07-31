"use client";
// 범용 드래그 스플릿 — worktree split-pane.tsx 포팅 일반화.
// 두 번째 패널을 % 로 크기 조절, storageKey 지정 시 비율을 localStorage 에 persist.
import React, { useRef, useCallback, useState, useEffect, type ReactNode } from "react";

interface SplitPaneProps {
  direction?: "horizontal" | "vertical";
  initial?: number; // 두 번째 패널 %
  min?: number;
  max?: number;
  storageKey?: string;
  children: [ReactNode, ReactNode];
}

export default function SplitPane({
  direction = "horizontal",
  initial = 50,
  min = 20,
  max = 80,
  storageKey,
  children,
}: SplitPaneProps) {
  const isVertical = direction === "vertical";
  const containerRef = useRef<HTMLDivElement>(null);
  const dragging = useRef(false);

  // SSR-safe 기본값, mount 후 저장값 hydrate.
  const [secondSize, setSecondSize] = useState(initial);

  useEffect(() => {
    if (!storageKey) return;
    const saved = localStorage.getItem(storageKey);
    if (saved) {
      const v = parseFloat(saved);
      if (!Number.isNaN(v)) setSecondSize(v);
    }
  }, [storageKey]);

  useEffect(() => {
    if (storageKey) localStorage.setItem(storageKey, String(secondSize));
  }, [storageKey, secondSize]);

  const clamp = useCallback((v: number) => Math.max(min, Math.min(max, v)), [min, max]);

  const computeRatio = useCallback(
    (clientX: number, clientY: number) => {
      const rect = containerRef.current!.getBoundingClientRect();
      if (isVertical) {
        const y = clientY - rect.top;
        return ((rect.height - y) / rect.height) * 100;
      }
      const x = clientX - rect.left;
      return ((rect.width - x) / rect.width) * 100;
    },
    [isVertical]
  );

  const handleMouseDown = useCallback(
    (e: React.MouseEvent) => {
      e.preventDefault();
      dragging.current = true;
      const onMove = (ev: MouseEvent) => {
        if (!dragging.current || !containerRef.current) return;
        setSecondSize(clamp(computeRatio(ev.clientX, ev.clientY)));
      };
      const onUp = () => {
        dragging.current = false;
        document.removeEventListener("mousemove", onMove);
        document.removeEventListener("mouseup", onUp);
      };
      document.addEventListener("mousemove", onMove);
      document.addEventListener("mouseup", onUp);
    },
    [clamp, computeRatio]
  );

  const handleTouchStart = useCallback(
    (e: React.TouchEvent) => {
      dragging.current = true;
      const onMove = (ev: TouchEvent) => {
        if (!dragging.current || !containerRef.current) return;
        const t = ev.touches[0];
        setSecondSize(clamp(computeRatio(t.clientX, t.clientY)));
      };
      const onEnd = () => {
        dragging.current = false;
        document.removeEventListener("touchmove", onMove);
        document.removeEventListener("touchend", onEnd);
      };
      document.addEventListener("touchmove", onMove);
      document.addEventListener("touchend", onEnd);
    },
    [clamp, computeRatio]
  );

  const firstStyle: React.CSSProperties = {
    flex: `1 1 ${100 - secondSize}%`,
    minWidth: 0,
    minHeight: 0,
    overflow: "hidden",
  };

  const secondStyle: React.CSSProperties = {
    ...(isVertical
      ? { height: `${secondSize}%`, minHeight: 50 }
      : { width: `${secondSize}%`, minWidth: 80 }),
    minWidth: 0,
    overflow: "hidden",
  };

  const [hover, setHover] = useState(false);
  const handleStyle: React.CSSProperties = {
    flexShrink: 0,
    background: hover ? "var(--accent)" : "var(--border)",
    transition: "background 0.12s",
    ...(isVertical
      ? { height: 6, width: "100%", cursor: "row-resize" }
      : { width: 6, height: "100%", cursor: "col-resize" }),
  };

  return (
    <div
      ref={containerRef}
      style={{
        height: "100%",
        width: "100%",
        display: "flex",
        flexDirection: isVertical ? "column" : "row",
        overflow: "hidden",
      }}
    >
      <div style={firstStyle}>{children[0]}</div>
      <div
        style={handleStyle}
        onMouseDown={handleMouseDown}
        onTouchStart={handleTouchStart}
        onMouseEnter={() => setHover(true)}
        onMouseLeave={() => setHover(false)}
      />
      <div style={secondStyle}>{children[1]}</div>
    </div>
  );
}
