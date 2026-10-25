import { Popover, PopoverSurface } from "@fluentui/react-components";
import { Info16Regular } from "@fluentui/react-icons";
import { useEffect, useId, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { INFO, type InfoEntry, type InfoId } from "../content/info";
import { usePrefs } from "../state/prefs";

/**
 * The "i" button. Research-based behaviour (NN/g tooltip and info-tip guidelines, Pickering's
 * toggletip pattern, Fluent InfoButton):
 *  - Mouse: hovering shows a preview; moving into the panel keeps it open.
 *  - Click, tap, Enter or Space: pins it open, on any device.
 *  - Esc, a click outside, or clicking the "i" again: closes it.
 *  - Keyboard focus shows it; the text is linked to the button for screen readers.
 * Open and close are handled here, not by the Popover, so the pin is never lost.
 */
export function Info({ id, inverted }: { id: InfoId; inverted?: boolean }) {
  const entry: InfoEntry = INFO[id];
  const { level } = usePrefs();
  const [open, setOpen] = useState(false);
  const [pinned, setPinned] = useState(false);
  const btn = useRef<HTMLButtonElement>(null);
  const surface = useRef<HTMLDivElement>(null);
  const timer = useRef<number | undefined>(undefined);
  const surfaceId = useId();
  const canHover = typeof window !== "undefined" && window.matchMedia("(hover: hover) and (pointer: fine)").matches;

  const cancel = () => window.clearTimeout(timer.current);
  const close = () => { cancel(); setOpen(false); setPinned(false); };
  const closeSoon = () => { cancel(); if (!pinned) timer.current = window.setTimeout(() => setOpen(false), 160); };
  useEffect(() => cancel, []);

  useEffect(() => {
    if (!open) return;
    const inside = (t: EventTarget | null) =>
      !!t && (btn.current?.contains(t as Node) || surface.current?.contains(t as Node));
    const onDown = (e: PointerEvent) => { if (!inside(e.target)) close(); };
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") { close(); btn.current?.focus(); } };
    document.addEventListener("pointerdown", onDown, true);
    document.addEventListener("keydown", onKey);
    return () => { document.removeEventListener("pointerdown", onDown, true); document.removeEventListener("keydown", onKey); };
  }, [open]); // eslint-disable-line react-hooks/exhaustive-deps

  const extra = level === "tech" ? entry.tech ?? entry.deep : level === "depth" ? entry.deep : undefined;

  return (
    <>
      <button
        ref={btn}
        type="button"
        className={`mh-info${inverted ? " mh-info--inverted" : ""}${pinned ? " is-pinned" : ""}`}
        aria-label={`More information: ${entry.title}`}
        aria-expanded={open}
        aria-describedby={open ? surfaceId : undefined}
        data-pinned={pinned || undefined}
        onMouseEnter={() => { if (canHover) { cancel(); setOpen(true); } }}
        onMouseLeave={() => { if (canHover) closeSoon(); }}
        onFocus={() => { cancel(); setOpen(true); }}
        onBlur={(e) => { if (!pinned && !surface.current?.contains(e.relatedTarget as Node)) closeSoon(); }}
        onClick={(e) => {
          e.stopPropagation();
          if (pinned) close(); else { cancel(); setPinned(true); setOpen(true); }
        }}
      >
        <Info16Regular aria-hidden />
      </button>
      <Popover
        open={open}
        onOpenChange={() => { /* open state is owned by this component */ }}
        positioning={{ target: btn.current, position: "above", autoSize: true }}
        withArrow
        trapFocus={false}
        size="small"
      >
        <PopoverSurface
          ref={surface}
          id={surfaceId}
          role="note"
          className="mh-info-surface"
          onMouseEnter={cancel}
          onMouseLeave={closeSoon}
        >
          <div className="mh-info-title">{entry.title}</div>
          <p><span className="mh-info-label">What it is.</span> {entry.what}</p>
          <p><span className="mh-info-label">Why it matters.</span> {entry.why}</p>
          {extra && <p className="mh-info-extra">{extra}</p>}
          {entry.more && (
            <Link className="mh-info-more" to={entry.more.to} onClick={close}>{entry.more.label}</Link>
          )}
          <div className="mh-info-hint">{pinned ? "Press Esc or click outside to close." : canHover ? "Click the i to keep this open." : ""}</div>
        </PopoverSurface>
      </Popover>
    </>
  );
}

/** A label followed by its "i" button, kept together on one line. */
export function Term({ children, id }: { children: React.ReactNode; id: InfoId }) {
  return <span className="mh-term">{children}<Info id={id} /></span>;
}
