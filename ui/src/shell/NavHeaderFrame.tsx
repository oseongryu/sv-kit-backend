"use client";

// 상단 네비 헤더의 표현 프레임 — 메뉴/사이드바토글/언어/테마/설정 버튼 바.
// 상태와 핸들러는 전부 앱 주입. 모달(메뉴·설정·로그인)은 앱이 프레임 밖에 렌더.

import { useEffect } from "react";
import { Settings, Sun, Moon, Globe, Menu, PanelLeft } from "lucide-react";
import { Button } from "../ui/button";
import { WithTooltip } from "../ui/with-tooltip";

export interface NavHeaderFrameProps {
  /** 브랜드 — name 은 document.title 로도 반영 */
  brandName: string;
  brandShort?: string;
  onMenuClick: () => void;
  /** 현재 화면이 등록한 사이드바 토글 — null 이면 버튼 미노출 */
  sidebarToggle?: (() => void) | null;
  locale?: string;
  onToggleLocale?: () => void;
  theme?: "dark" | "light";
  onToggleTheme?: () => void;
  onSettingsClick?: () => void;
  /** 툴팁 문구 (기본 한국어) */
  labels?: {
    menu?: string;
    sidebar?: string;
    locale?: string;
    theme?: string;
    settings?: string;
  };
}

export function NavHeaderFrame({
  brandName, brandShort, onMenuClick, sidebarToggle,
  locale, onToggleLocale, theme, onToggleTheme, onSettingsClick,
  labels = {},
}: NavHeaderFrameProps) {
  useEffect(() => {
    document.title = brandName;
  }, [brandName]);

  const iconBtn = "h-7 w-7 shrink-0 text-muted-foreground hover:text-foreground";

  return (
    <header className="bg-card/80 backdrop-blur-md border-b border-border shrink-0 px-4 flex items-center h-10 gap-1 relative z-50">
      {/* 메뉴 버튼 — 클릭 시 메뉴 팝업 */}
      <WithTooltip title={labels.menu ?? "메뉴"}>
        <Button
          variant="ghost"
          size="icon"
          className={iconBtn}
          onClick={onMenuClick}
          aria-label={brandShort ?? brandName}
        >
          <Menu className="h-4 w-4" />
        </Button>
      </WithTooltip>

      {/* 사이드바 목록 토글 — 현재 화면이 등록한 콜백이 있을 때만 노출 */}
      {sidebarToggle && (
        <WithTooltip title={labels.sidebar ?? "목록 표시/숨김"}>
          <Button variant="ghost" size="icon" className={iconBtn} onClick={() => sidebarToggle()}>
            <PanelLeft className="h-4 w-4" />
          </Button>
        </WithTooltip>
      )}

      <div className="flex-1" />

      {/* 언어 전환 */}
      {onToggleLocale && (
        <WithTooltip title={labels.locale ?? (locale === "ko" ? "English" : "한국어")}>
          <Button variant="ghost" size="icon" className={iconBtn} onClick={onToggleLocale}>
            <Globe className="h-3.5 w-3.5" />
          </Button>
        </WithTooltip>
      )}

      {/* 테마 전환 */}
      {onToggleTheme && (
        <WithTooltip title={labels.theme ?? "테마 전환"}>
          <Button variant="ghost" size="icon" className={iconBtn} onClick={onToggleTheme}>
            {theme === "dark" ? <Sun className="h-3.5 w-3.5" /> : <Moon className="h-3.5 w-3.5" />}
          </Button>
        </WithTooltip>
      )}

      {/* 설정 */}
      {onSettingsClick && (
        <WithTooltip title={labels.settings ?? "설정"}>
          <button
            onClick={onSettingsClick}
            className="flex items-center justify-center h-7 w-7 rounded transition-colors shrink-0 text-muted-foreground hover:text-foreground hover:bg-accent"
          >
            <Settings className="h-3.5 w-3.5" />
          </button>
        </WithTooltip>
      )}
    </header>
  );
}
