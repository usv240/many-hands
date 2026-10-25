import { createContext, type ReactNode, useContext, useEffect, useMemo, useState } from "react";

export type ThemeMode = "system" | "light" | "dark";
export type Level = "simple" | "depth" | "tech";

interface Prefs {
  mode: ThemeMode;
  setMode: (m: ThemeMode) => void;
  dark: boolean;
  level: Level;
  setLevel: (l: Level) => void;
}

const Ctx = createContext<Prefs | null>(null);

const systemDark = () => window.matchMedia("(prefers-color-scheme: dark)").matches;

export function PrefsProvider({ children }: { children: ReactNode }) {
  const [mode, setModeState] = useState<ThemeMode>(
    () => (localStorage.getItem("mh-theme") as ThemeMode) || "system");
  const [level, setLevelState] = useState<Level>(
    () => (localStorage.getItem("mh-level") as Level) || "simple");
  const [sysDark, setSysDark] = useState(systemDark);

  useEffect(() => {
    const mq = window.matchMedia("(prefers-color-scheme: dark)");
    const on = () => setSysDark(mq.matches);
    mq.addEventListener("change", on);
    return () => mq.removeEventListener("change", on);
  }, []);

  const dark = mode === "dark" || (mode === "system" && sysDark);
  useEffect(() => { document.documentElement.dataset.theme = dark ? "dark" : "light"; }, [dark]);

  const value = useMemo<Prefs>(() => ({
    mode, dark, level,
    setMode: (m) => { localStorage.setItem("mh-theme", m); setModeState(m); },
    setLevel: (l) => { localStorage.setItem("mh-level", l); setLevelState(l); },
  }), [mode, dark, level]);
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function usePrefs(): Prefs {
  const v = useContext(Ctx);
  if (!v) throw new Error("usePrefs outside PrefsProvider");
  return v;
}

/** Text that changes with the reading level. Falls back to the simpler version. */
export function L({ s, d, t }: { s: ReactNode; d?: ReactNode; t?: ReactNode }) {
  const { level } = usePrefs();
  if (level === "tech") return <>{t ?? d ?? s}</>;
  if (level === "depth") return <>{d ?? s}</>;
  return <>{s}</>;
}
