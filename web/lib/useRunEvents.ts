"use client";

import { useEffect, useRef, useState } from "react";

import { eventsUrl } from "@/lib/api";
import type { ProgressEvent } from "@/lib/types";

interface RunEventsState {
  events: ProgressEvent[];
  connected: boolean;
  finished: boolean;
}

const TERMINAL = new Set(["done:end", "error:error"]);

/**
 * Subscribe to a run's SSE stream. Returns accumulated events plus
 * connection/terminal state. The stream replays persisted events on connect,
 * so this works whether the run is live or already finished.
 */
export function useRunEvents(runId: string | null): RunEventsState {
  const [events, setEvents] = useState<ProgressEvent[]>([]);
  const [connected, setConnected] = useState(false);
  const [finished, setFinished] = useState(false);

  const sourceRef = useRef<EventSource | null>(null);
  const finishedRef = useRef(false);
  const seenSeq = useRef<Set<number>>(new Set());

  useEffect(() => {
    if (!runId) return;
    let cancelled = false;

    setEvents([]);
    setFinished(false);
    finishedRef.current = false;
    seenSeq.current = new Set();

    const close = () => {
      sourceRef.current?.close();
      sourceRef.current = null;
    };

    (async () => {
      const url = await eventsUrl(runId);
      // The component may have unmounted / runId changed during the await.
      if (cancelled) return;

      const source = new EventSource(url);
      sourceRef.current = source;

      source.addEventListener("open", () => setConnected(true));

      const finish = () => {
        finishedRef.current = true;
        setFinished(true);
        close();
      };

      source.addEventListener("progress", (e: MessageEvent) => {
        try {
          const ev = JSON.parse(e.data) as ProgressEvent;
          if (ev.seq >= 0 && seenSeq.current.has(ev.seq)) return;
          if (ev.seq >= 0) seenSeq.current.add(ev.seq);
          setEvents((prev) => [...prev, ev]);
          if (TERMINAL.has(`${ev.phase}:${ev.status}`)) finish();
        } catch {
          /* ignore malformed frame */
        }
      });

      source.addEventListener("done", finish);

      source.addEventListener("error", () => {
        // Programmatic close() fires an error in some browsers — ignore it once
        // the run is already finished so the UI doesn't flash "disconnected".
        if (!finishedRef.current) setConnected(false);
      });
    })();

    return () => {
      cancelled = true;
      close();
    };
  }, [runId]);

  return { events, connected, finished };
}
