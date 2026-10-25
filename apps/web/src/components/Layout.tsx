import {
  Button, Drawer, DrawerBody, DrawerHeader, DrawerHeaderTitle, Menu, MenuItemRadio, MenuList,
  MenuPopover, MenuTrigger,
} from "@fluentui/react-components";
import {
  Desktop20Regular, Dismiss24Regular, Gavel20Regular, Navigation24Regular, WeatherMoon20Regular,
  WeatherSunny20Regular,
} from "@fluentui/react-icons";
import { type ReactNode, useEffect, useState } from "react";
import { Link, NavLink, useLocation } from "react-router-dom";
import type { InfoId } from "../content/info";
import { type Level, type ThemeMode, usePrefs } from "../state/prefs";
import { Info } from "./Info";

const NAV = [
  { to: "/how-it-works", label: "How it works" },
  { to: "/check", label: "Check a line" },
  { to: "/studio", label: "Studio" },
  { to: "/results", label: "Results" },
  { to: "/developers", label: "Developers" },
  { to: "/learn", label: "Learn" },
];

const LEVELS: { value: Level; label: string }[] = [
  { value: "simple", label: "Simply" },
  { value: "depth", label: "In depth" },
  { value: "tech", label: "Technically" },
];

function Logo() {
  return (
    <Link to="/" className="mh-logo" aria-label="Many Hands, home">
      <svg viewBox="0 0 32 32" width="28" height="28" aria-hidden>
        <path d="M5 22 12 12 19 19 27 9" fill="none" stroke="currentColor" strokeWidth="2" />
        <circle cx="5" cy="22" r="3" fill="currentColor" /><circle cx="12" cy="12" r="3" fill="currentColor" />
        <circle cx="19" cy="19" r="3" fill="currentColor" /><circle cx="27" cy="9" r="4.5" fill="currentColor" />
      </svg>
      <span>Many Hands</span>
    </Link>
  );
}

function LevelSwitch() {
  const { level, setLevel } = usePrefs();
  return (
    <div className="mh-level" role="radiogroup" aria-label="Reading level">
      <span className="mh-term mh-level-label">Explain<Info id="readingLevel" /></span>
      <div className="mh-seg">
        {LEVELS.map((l) => (
          <label key={l.value}>
            <input type="radio" name="mh-level" value={l.value} checked={level === l.value}
                   onChange={() => setLevel(l.value)} />
            <span>{l.label}</span>
          </label>
        ))}
      </div>
    </div>
  );
}

function ThemeSwitch() {
  const { mode, setMode, dark } = usePrefs();
  const icon = mode === "system" ? <Desktop20Regular /> : dark ? <WeatherMoon20Regular /> : <WeatherSunny20Regular />;
  return (
    <Menu checkedValues={{ theme: [mode] }} onCheckedValueChange={(_, d) => setMode(d.checkedItems[0] as ThemeMode)}>
      <MenuTrigger disableButtonEnhancement>
        <Button appearance="subtle" icon={icon} aria-label={`Theme: ${mode}`} />
      </MenuTrigger>
      <MenuPopover>
        <MenuList>
          <MenuItemRadio name="theme" value="system" icon={<Desktop20Regular />}>Match my device</MenuItemRadio>
          <MenuItemRadio name="theme" value="light" icon={<WeatherSunny20Regular />}>Light</MenuItemRadio>
          <MenuItemRadio name="theme" value="dark" icon={<WeatherMoon20Regular />}>Dark</MenuItemRadio>
        </MenuList>
      </MenuPopover>
    </Menu>
  );
}

export function Layout({ children }: { children: ReactNode }) {
  const [menu, setMenu] = useState(false);
  const loc = useLocation();
  useEffect(() => { setMenu(false); window.scrollTo(0, 0); }, [loc.pathname]);
  useEffect(() => {
    if (!loc.hash) return;
    const el = document.getElementById(loc.hash.slice(1));
    if (el) window.setTimeout(() => el.scrollIntoView({ behavior: "smooth", block: "start" }), 60);
  }, [loc]);

  return (
    <div className="mh-app">
      <a href="#main" className="mh-skip">Skip to content</a>
      <header className="mh-header">
        <div className="mh-header-inner">
          <Logo />
          <nav className="mh-nav" aria-label="Main">
            {NAV.map((n) => (
              <NavLink key={n.to} to={n.to} className={({ isActive }) => `mh-nav-link${isActive ? " is-active" : ""}`}>
                {n.label}
              </NavLink>
            ))}
          </nav>
          <div className="mh-header-tools">
            <LevelSwitch />
            <ThemeSwitch />
            <span className="mh-judges-btn">
              <Link to="/judges" className="mh-btn-judges"><Gavel20Regular aria-hidden /> Judges start here</Link>
              <Info id="judges" />
            </span>
            <Button className="mh-menu-btn" appearance="subtle" icon={<Navigation24Regular />} aria-label="Open menu"
                    onClick={() => setMenu(true)} />
          </div>
        </div>
      </header>

      <Drawer type="overlay" position="end" open={menu} onOpenChange={(_, d) => setMenu(d.open)}>
        <DrawerHeader>
          <DrawerHeaderTitle action={<Button appearance="subtle" aria-label="Close menu" icon={<Dismiss24Regular />} onClick={() => setMenu(false)} />}>
            Menu
          </DrawerHeaderTitle>
        </DrawerHeader>
        <DrawerBody>
          <nav className="mh-drawer-nav" aria-label="Main">
            <Link to="/judges" className="mh-btn-judges"><Gavel20Regular aria-hidden /> Judges start here</Link>
            <Link to="/">Home</Link>
            {NAV.map((n) => <Link key={n.to} to={n.to}>{n.label}</Link>)}
            <Link to="/trust">Trust and safety</Link>
          </nav>
          <div className="mh-drawer-level"><LevelSwitch /></div>
        </DrawerBody>
      </Drawer>

      <main id="main" tabIndex={-1}>{children}</main>

      <footer className="mh-footer">
        <div className="mh-footer-inner">
          <div>
            <Logo />
            <p className="mh-muted">Nobody concedes alone.</p>
          </div>
          <div className="mh-footer-cols">
            <div>
              <h2>Product</h2>
              <Link to="/check">Check a sentence</Link><Link to="/studio">Studio</Link>
              <Link to="/developers">Developers and API</Link><Link to="/byo">Bring your own</Link>
            </div>
            <div>
              <h2>Proof</h2>
              <Link to="/results">Results</Link><Link to="/trust">Trust and safety</Link><Link to="/judges">Judges start here</Link>
            </div>
            <div>
              <h2>Learn</h2>
              <Link to="/how-it-works">How it works</Link><Link to="/learn">Glossary and basics</Link>
              <Link to="/learn#references">Research and references</Link>
            </div>
          </div>
        </div>
        <p className="mh-footer-note">
          All matches, clubs and players on this site are fictional, generated by our simulator.
          External validation uses StatsBomb Open Data (data provided by StatsBomb), excluding Premier League competitions.
          Built for the Inside the Game Developer Hackathon. MIT licence.
        </p>
      </footer>
    </div>
  );
}

/** Every page starts with a title and one plain sentence saying what the page is for. */
export function PageHeader({ title, purpose, info, children }:
  { title: string; purpose: string; info?: InfoId; children?: ReactNode }) {
  return (
    <div className="mh-page-header">
      <h1>{title}{info && <Info id={info} />}</h1>
      <p className="mh-purpose">{purpose}</p>
      {children}
    </div>
  );
}
