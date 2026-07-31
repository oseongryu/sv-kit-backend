"use client";

import type { ReactNode } from "react";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "./dialog";
import { cn } from "./utils";

// 사이즈 프리셋 — 모바일은 항상 풀폭(Dialog 기본 max-w-[calc(100%-2rem)])이고
// `sm:` (≥640px) 이상에서만 max-width 적용. 모든 프리셋이 동일한 모바일 거동을 갖는다.
const SIZE = {
  sm: "sm:max-w-sm",
  md: "sm:max-w-md",
  lg: "sm:max-w-lg",
  xl: "sm:max-w-xl",
  "2xl": "sm:max-w-2xl",
  "3xl": "sm:max-w-3xl",
  "4xl": "sm:max-w-4xl",
  "5xl": "sm:max-w-5xl",
  "6xl": "sm:max-w-6xl",
  full: "sm:max-w-7xl",
} as const;

type SizeKey = keyof typeof SIZE;

// 위치 프리셋 (PC 모드 기준, 모바일은 항상 센터)
const POSITION_CLASS: Record<string, string> = {
  center: "",
  "top-left": "!top-10 !left-2 !translate-x-0 !translate-y-0",
};

interface CommonModalProps {
  open: boolean;
  onClose: () => void;
  title: string;
  /** 사이즈 프리셋 또는 커스텀 className */
  size?: SizeKey | string;
  /** 모달 위치 (PC 모드): 'center'(기본) | 'top-left' */
  position?: keyof typeof POSITION_CLASS;
  /** 헤더 우측 액션 영역 */
  headerActions?: ReactNode;
  /** DialogContent에 추가할 className */
  className?: string;
  /** 닫기 중 방지 (loading 등) */
  preventClose?: boolean;
  /** 열릴 때 콜백 */
  onOpen?: () => void;
  children: ReactNode;
}

export function CommonModal({
  open, onClose, title, size = "md",
  position = "center",
  headerActions, className, preventClose, onOpen, children,
}: CommonModalProps) {
  const sizeClass = SIZE[size as SizeKey] || size;
  const positionClass = POSITION_CLASS[position] ?? "";
  const isCustom = !!headerActions;

  return (
    <Dialog open={open} onOpenChange={(v) => { if (v && onOpen) onOpen(); if (!v && !preventClose) onClose(); }}>
      <DialogContent
        className={cn(
          sizeClass,
          positionClass,
          // headerActions 모드: 헤더가 sticky 처럼 고정되어야 하므로 모달 자체는 스크롤 X.
          // 내부 패널이 자기 영역 안에서 스크롤 처리한다.
          isCustom && "flex flex-col p-0 gap-0 overflow-hidden",
          className,
        )}
        showCloseButton={!isCustom}
      >
        {isCustom ? (
          <>
            <DialogHeader className="flex-row items-center justify-between border-b border-border px-4 py-2.5 shrink-0">
              <DialogTitle className="text-sm">{title}</DialogTitle>
              <div className="flex items-center gap-2">
                {headerActions}
              </div>
            </DialogHeader>
            {children}
          </>
        ) : (
          <>
            <DialogHeader>
              <DialogTitle>{title}</DialogTitle>
            </DialogHeader>
            {children}
          </>
        )}
      </DialogContent>
    </Dialog>
  );
}