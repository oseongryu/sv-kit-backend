"use client";

// 전역 커맨드 팔레트 — ⌘K/Ctrl+K 로 열리는 범용 프레임. 커맨드 구성은 앱 주입.

import { useState, useEffect } from "react";
import { type LucideIcon } from "lucide-react";
import {
  Command,
  CommandDialog,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
  CommandSeparator,
} from "../ui/command";

export interface PaletteCommand {
  icon?: LucideIcon;
  label: string;
  onSelect: () => void;
}

export interface PaletteGroup {
  heading: string;
  commands: PaletteCommand[];
}

export interface CommandPaletteProps {
  groups: PaletteGroup[];
  title?: string;
  description?: string;
  placeholder?: string;
  emptyText?: string;
}

export function CommandPalette({
  groups,
  title = "명령어 검색",
  description = "빠른 액션을 검색하세요 (Cmd + K)",
  placeholder = "무엇을 찾고 계신가요?",
  emptyText = "결과를 찾을 수 없습니다.",
}: CommandPaletteProps) {
  const [open, setOpen] = useState(false);

  useEffect(() => {
    const down = (e: KeyboardEvent) => {
      if (e.key === "k" && (e.metaKey || e.ctrlKey)) {
        e.preventDefault();
        setOpen((open) => !open);
      }
    };
    document.addEventListener("keydown", down);
    return () => document.removeEventListener("keydown", down);
  }, []);

  const run = (command: () => void) => {
    setOpen(false);
    command();
  };

  return (
    <CommandDialog open={open} onOpenChange={setOpen} title={title} description={description}>
      <Command>
        <CommandInput placeholder={placeholder} />
        <CommandList>
          <CommandEmpty>{emptyText}</CommandEmpty>
          {groups.map((group, gi) => (
            <div key={group.heading}>
              {gi > 0 && <CommandSeparator />}
              <CommandGroup heading={group.heading}>
                {group.commands.map((cmd) => (
                  <CommandItem key={cmd.label} onSelect={() => run(cmd.onSelect)}>
                    {cmd.icon && <cmd.icon className="mr-2 h-4 w-4" />}
                    <span>{cmd.label}</span>
                  </CommandItem>
                ))}
              </CommandGroup>
            </div>
          ))}
        </CommandList>
      </Command>
    </CommandDialog>
  );
}
