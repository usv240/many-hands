import { type BrandVariants, createDarkTheme, createLightTheme, type Theme } from "@fluentui/react-components";

// Indigo brand ramp, used only for interactive elements (buttons, links, focus). Data colours are
// separate and validated (see docs/03-ux-design), so a brand colour never reads as a team.
const brand: BrandVariants = {
  10: "#04031a", 20: "#0d0b33", 30: "#16134c", 40: "#1f1a66", 50: "#282180", 60: "#312a9a",
  70: "#3a33b4", 80: "#4f46e5", 90: "#6159e8", 100: "#736ceb", 110: "#857fee", 120: "#9792f1",
  130: "#a9a5f4", 140: "#bbb8f7", 150: "#cdcbfa", 160: "#e0defc",
};

export const lightTheme: Theme = { ...createLightTheme(brand) };
export const darkTheme: Theme = {
  ...createDarkTheme(brand),
  colorBrandForeground1: brand[120],
  colorBrandForeground2: brand[130],
  colorBrandForegroundLink: brand[120],
};
