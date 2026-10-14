import { useEffect } from "react";
import { BrowserRouter } from "react-router";

import { AppRoutes } from "@/app/routes";
import { Toaster } from "@/components/ui/sonner";
import { TooltipProvider } from "@/components/ui/tooltip";
import { useUiStore } from "@/stores/ui";

function useThemeClass(): void {
  const theme = useUiStore((s) => s.theme);
  useEffect(() => {
    document.documentElement.classList.toggle("dark", theme === "dark");
  }, [theme]);
}

export function App() {
  useThemeClass();
  return (
    <BrowserRouter>
      <TooltipProvider>
        <AppRoutes />
        <Toaster />
      </TooltipProvider>
    </BrowserRouter>
  );
}
