import { useEffect, useState } from "react";
import { useMediaQuery } from "../lib/useMediaQuery";

export type ThemeChoice = "system" | "light" | "dark" | "sepia";
export type Theme = Exclude<ThemeChoice, "system">;

export const THEME_LABELS: Record<ThemeChoice, string> = {
  system: "System",
  light: "Light",
  dark: "Dark",
  sepia: "Sepia",
};

const STORAGE_KEY = "famtree-theme"; // also read by public/theme-init.js

function storedChoice(): ThemeChoice {
  try {
    const value = localStorage.getItem(STORAGE_KEY);
    return value && value in THEME_LABELS ? (value as ThemeChoice) : "system";
  } catch {
    return "system";
  }
}

export function resolveTheme(choice: ThemeChoice, prefersDark: boolean): Theme {
  return choice === "system" ? (prefersDark ? "dark" : "light") : choice;
}

/** The chosen theme, remembered per browser; "system" follows the OS setting. */
export function useTheme(): [ThemeChoice, (choice: ThemeChoice) => void] {
  const [choice, setChoice] = useState<ThemeChoice>(storedChoice);
  const prefersDark = useMediaQuery("(prefers-color-scheme: dark)");

  useEffect(() => {
    document.documentElement.dataset.theme = resolveTheme(choice, prefersDark);
  }, [choice, prefersDark]);

  const update = (next: ThemeChoice) => {
    setChoice(next);
    try {
      localStorage.setItem(STORAGE_KEY, next);
    } catch {
      // Storage may be unavailable (private mode); the choice still applies now.
    }
  };
  return [choice, update];
}
