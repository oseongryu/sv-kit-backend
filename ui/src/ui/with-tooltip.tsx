import * as React from "react";
import { Tooltip, TooltipTrigger, TooltipContent, TooltipProvider } from "./tooltip";

export interface WithTooltipProps {
  title: React.ReactNode;
  children: React.ReactNode;
  side?: "top" | "right" | "bottom" | "left";
  sideOffset?: number;
  delay?: number;
}

export function WithTooltip({ title, children, side = "bottom", sideOffset = 4, delay = 200 }: WithTooltipProps) {
  if (!title) return <>{children}</>;
  
  return (
    <TooltipProvider delay={delay}>
      <Tooltip>
        <TooltipTrigger>
          {children}
        </TooltipTrigger>
        <TooltipContent side={side} sideOffset={sideOffset}>
          {title}
        </TooltipContent>
      </Tooltip>
    </TooltipProvider>
  );
}
