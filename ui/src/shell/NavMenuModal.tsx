"use client";

// 네비 메뉴 모달 — 항목·아이콘 해석을 주입받는 범용 목록.
// NavItemLike 는 구조 타입 — 앱의 NavPage 등이 그대로 만족하면 된다.

import { useMemo } from "react";
import { Globe, ExternalLink, type LucideIcon } from "lucide-react";
import { CommonModal } from "../ui/CommonModal";

export interface NavItemLike {
  id: number;
  path: string;
  label: string;
  service_url?: string | null;
  sort_order: number;
}

interface NavMenuModalProps<T extends NavItemLike> {
  open: boolean;
  onClose: () => void;
  navItems: T[];
  onSelect: (item: T) => void;
  /** 항목 아이콘 해석 (기본: 외부 서비스 ExternalLink, 그 외 Globe) */
  resolveIcon?: (item: T) => LucideIcon;
  title?: string;
}

function defaultIcon(item: NavItemLike): LucideIcon {
  return item.service_url ? ExternalLink : Globe;
}

export function NavMenuModal<T extends NavItemLike>({
  open, onClose, navItems, onSelect, resolveIcon = defaultIcon, title = "메뉴",
}: NavMenuModalProps<T>) {
  const sorted = useMemo(
    () => [...navItems].sort((a, b) => a.sort_order - b.sort_order || a.id - b.id),
    [navItems],
  );

  return (
    <CommonModal open={open} onClose={onClose} title={title} size="sm" position="top-left">
      <div className="space-y-0.5 max-h-[60dvh] overflow-y-auto">
        {sorted.map((item) => {
          const Icon = resolveIcon(item);
          return (
            <button
              key={item.id}
              onClick={() => onSelect(item)}
              className="flex items-center gap-2.5 w-full text-left px-3 py-2.5 text-sm rounded transition-colors text-foreground hover:bg-accent/70"
            >
              <Icon className="h-4 w-4 shrink-0 text-muted-foreground" />
              {item.label}
            </button>
          );
        })}
      </div>
    </CommonModal>
  );
}
