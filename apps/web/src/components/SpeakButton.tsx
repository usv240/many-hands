import { Button, Spinner } from "@fluentui/react-components";
import { Speaker220Regular, SpeakerOff20Regular } from "@fluentui/react-icons";
import { useEffect, useRef, useState } from "react";
import { Info } from "./Info";

type State = "idle" | "loading" | "playing" | "error";

/** Plays a line the way it would sound on air. The server reads only lines that passed the fairness check. */
export function SpeakButton({ text, lang = "en", label = "Hear it on air", withInfo = false }:
  { text: string; lang?: "en" | "es"; label?: string; withInfo?: boolean }) {
  const [state, setState] = useState<State>("idle");
  const [error, setError] = useState<string | null>(null);
  const audio = useRef<HTMLAudioElement | null>(null);
  const url = useRef<string | null>(null);

  useEffect(() => () => {
    audio.current?.pause();
    if (url.current) URL.revokeObjectURL(url.current);
  }, []);

  const stop = () => { audio.current?.pause(); setState("idle"); };

  const play = async () => {
    setError(null);
    if (!url.current) {
      setState("loading");
      try {
        const r = await fetch("/v1/speak", { method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ text, lang }), signal: AbortSignal.timeout(25000) });
        if (!r.ok) throw new Error((await r.json().catch(() => null))?.detail ?? `The voice is not available (${r.status}).`);
        url.current = URL.createObjectURL(await r.blob());
      } catch (e) {
        setError((e as Error).message); setState("error"); return;
      }
    }
    audio.current ??= new Audio();
    audio.current.src = url.current;
    audio.current.onended = () => setState("idle");
    try { await audio.current.play(); setState("playing"); } catch { setState("idle"); }
  };

  return (
    <span className="mh-speak">
      <Button size="small" appearance="subtle" onClick={state === "playing" ? stop : play} disabled={state === "loading"}
        icon={state === "loading" ? <Spinner size="tiny" /> : state === "playing" ? <SpeakerOff20Regular /> : <Speaker220Regular />}
        aria-label={state === "playing" ? "Stop the voice" : `${label}${lang === "es" ? " (Spanish voice)" : ""}`}>
        {state === "playing" ? "Stop" : label}
      </Button>
      {withInfo && <Info id="voice" />}
      {error && <span className="mh-small mh-bad" role="alert">{error}</span>}
    </span>
  );
}
