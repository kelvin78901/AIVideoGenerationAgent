import type * as React from "react";
import { Toaster as Sonner, type ToasterProps } from "sonner";

import { useUiStore } from "@/stores/ui";

function Toaster(props: ToasterProps) {
  const theme = useUiStore((s) => s.theme);
  return (
    <Sonner
      theme={theme}
      position="bottom-right"
      toastOptions={{ classNames: { toast: "font-sans text-sm" } }}
      style={
        {
          "--normal-bg": "var(--popover)",
          "--normal-text": "var(--popover-foreground)",
          "--normal-border": "var(--border)",
        } as React.CSSProperties
      }
      {...props}
    />
  );
}

export { Toaster };
