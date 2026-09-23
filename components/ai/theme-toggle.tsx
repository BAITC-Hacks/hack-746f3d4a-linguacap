"use client";

import { SunMoon } from "lucide-react";
import { useEffect } from "react";

import { Button } from "@/components/ui/button";

function getInitialTheme() {
  const saved = window.localStorage.getItem("launchpad-theme");
  if (saved === "light" || saved === "dark") return saved;
  return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

export function ThemeToggle() {
  useEffect(() => {
    const theme = getInitialTheme();
    document.documentElement.classList.toggle("dark", theme === "dark");
    window.localStorage.setItem("launchpad-theme", theme);
  }, []);

  const toggleTheme = () => {
    const nextTheme = document.documentElement.classList.contains("dark") ? "light" : "dark";
    document.documentElement.classList.toggle("dark", nextTheme === "dark");
    window.localStorage.setItem("launchpad-theme", nextTheme);
  };

  return (
    <Button
      aria-label="Toggle color theme"
      onClick={toggleTheme}
      size="icon"
      variant="ghost"
    >
      <SunMoon aria-hidden="true" className="h-4 w-4" />
    </Button>
  );
}
