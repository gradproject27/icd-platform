import { useEffect, useReducer } from "react";
import {
  getResponseWindow,
  parseResponseWindowEvent,
  responseWindowSocketUrl,
  type ResponseWindow,
  type ResponseWindowEvent,
} from "../api/responseWindows";
import { offsetFromPush, offsetFromRequest, remainingMs } from "../countdown/clock";

export const RENDER_INTERVAL_MS = 250;
export const REMINDER_AT_MS = 30_000;
const RECONNECT_DELAYS_MS = [1_000, 2_000, 4_000];
const RECONNECT_MAX_MS = 10_000;

export interface ResponseWindowView {
  state: "loading" | "none" | "open" | "decided" | "expired" | "error";
  window: ResponseWindow | null;
  /** Remaining time computed from the server's deadline_at; null without a window. */
  remainingMs: number | null;
  /** True in the last 30 seconds of an open window. */
  reminder: boolean;
  connection: "live" | "reconnecting";
  error: string | null;
}

interface State {
  load: "loading" | "ready" | "error";
  window: ResponseWindow | null;
  /** Estimated server clock − client clock, from the latest server_time. */
  offsetMs: number;
  /** Client clock at the latest update; only ever set from callbacks, never during render. */
  clientNowMs: number;
  connection: "live" | "reconnecting";
  error: string | null;
}

type Action =
  | { type: "read"; window: ResponseWindow | null; offsetMs: number; clientNowMs: number }
  | { type: "readFailed"; message: string; clientNowMs: number }
  | { type: "event"; event: ResponseWindowEvent; offsetMs: number; clientNowMs: number }
  | { type: "connection"; connection: State["connection"] }
  | { type: "tick"; clientNowMs: number };

function reducer(state: State, action: Action): State {
  switch (action.type) {
    case "read":
      return { ...state, load: "ready", window: action.window, offsetMs: action.offsetMs, clientNowMs: action.clientNowMs, error: null };
    case "readFailed":
      // Keep a window that is already shown: the countdown goes on from its deadline_at.
      return state.window
        ? { ...state, clientNowMs: action.clientNowMs }
        : { ...state, load: "error", error: action.message, clientNowMs: action.clientNowMs };
    case "event":
      return { ...state, window: applyEvent(state.window, action.event), offsetMs: action.offsetMs, clientNowMs: action.clientNowMs };
    case "connection":
      return { ...state, connection: action.connection };
    case "tick":
      return { ...state, clientNowMs: action.clientNowMs };
  }
}

function applyEvent(current: ResponseWindow | null, event: ResponseWindowEvent): ResponseWindow | null {
  if (event.type === "response_window.opened") {
    return {
      incident_id: event.incident_id,
      window_id: event.window_id,
      status: "open",
      started_at: event.started_at,
      deadline_at: event.deadline_at,
      server_time: event.server_time,
      recommended_scenario_id: event.recommended_scenario_id,
    };
  }
  if (!current || current.window_id !== event.window_id) return current;
  switch (event.type) {
    case "response_window.reminder":
      return { ...current, deadline_at: event.deadline_at };
    case "response_window.decided":
      return { ...current, status: "decided" };
    case "response_window.expired":
      return { ...current, status: "expired" };
  }
}

/**
 * The response window of one incident, read over REST and kept current over the WebSocket.
 * The server owns the deadline: nothing here can create, restart or extend a window. Remount the
 * caller (key={incidentId}) to follow another incident.
 */
export function useResponseWindow(incidentId: string): ResponseWindowView {
  const [state, dispatch] = useReducer(reducer, {
    load: "loading",
    window: null,
    offsetMs: 0,
    clientNowMs: 0,
    connection: "live",
    error: null,
  });

  useEffect(() => {
    let disposed = false;
    let socket: WebSocket | null = null;
    let retryTimer: ReturnType<typeof setTimeout> | undefined;
    let failedAttempts = 0;
    let readController: AbortController | null = null;
    let knownWindowId: string | null = null;

    const read = async () => {
      readController?.abort();
      const controller = new AbortController();
      readController = controller;
      try {
        const result = await getResponseWindow(incidentId, controller.signal);
        if (disposed || controller.signal.aborted) return;
        knownWindowId = result.window?.window_id ?? null;
        dispatch({
          type: "read",
          window: result.window,
          offsetMs: result.window ? offsetFromRequest(result.window.server_time, result.sentAtMs, result.receivedAtMs) : 0,
          clientNowMs: Date.now(),
        });
      } catch (error) {
        if (disposed || controller.signal.aborted) return;
        const message = error instanceof Error ? error.message : "Could not read the response window.";
        dispatch({ type: "readFailed", message, clientNowMs: Date.now() });
      }
    };

    const connect = () => {
      if (disposed) return;
      const ws = new WebSocket(responseWindowSocketUrl(incidentId));
      socket = ws;
      ws.onopen = () => {
        const reconnected = failedAttempts > 0;
        failedAttempts = 0;
        dispatch({ type: "connection", connection: "live" });
        // Events may have been missed while disconnected: read the current state again.
        if (reconnected) void read();
      };
      ws.onmessage = (message: MessageEvent) => {
        const receivedAtMs = Date.now();
        let event: ResponseWindowEvent | null;
        let offsetMs: number;
        try {
          event = parseResponseWindowEvent(JSON.parse(String(message.data)));
          if (!event || event.incident_id !== incidentId) return;
          offsetMs = offsetFromPush(event.server_time, receivedAtMs);
        } catch {
          return; // A malformed event changes nothing.
        }
        dispatch({ type: "event", event, offsetMs, clientNowMs: receivedAtMs });
        if (event.type === "response_window.opened" && event.window_id !== knownWindowId) {
          knownWindowId = event.window_id;
          void read();
        }
      };
      ws.onclose = () => {
        if (disposed) return;
        dispatch({ type: "connection", connection: "reconnecting" });
        const delay = RECONNECT_DELAYS_MS[failedAttempts] ?? RECONNECT_MAX_MS;
        failedAttempts += 1;
        retryTimer = setTimeout(connect, delay);
      };
      // An error is always followed by close, which schedules the retry.
      ws.onerror = () => undefined;
    };

    void read();
    connect();

    return () => {
      disposed = true;
      clearTimeout(retryTimer);
      readController?.abort();
      if (socket) {
        socket.onopen = socket.onmessage = socket.onclose = socket.onerror = null;
        socket.close();
      }
    };
  }, [incidentId]);

  const isOpen = state.window?.status === "open";
  useEffect(() => {
    if (!isOpen) return;
    // This interval only triggers a re-render. It holds no time state: every tick recomputes the
    // remaining time from the server's deadline_at and the measured offset.
    const interval = setInterval(() => dispatch({ type: "tick", clientNowMs: Date.now() }), RENDER_INTERVAL_MS);
    return () => clearInterval(interval);
  }, [isOpen]);

  const remaining = state.window ? remainingMs(state.window.deadline_at, state.offsetMs, state.clientNowMs) : null;
  return {
    state:
      state.load === "loading" ? "loading" : state.load === "error" ? "error" : (state.window?.status ?? "none"),
    window: state.window,
    remainingMs: remaining,
    reminder: isOpen && remaining !== null && remaining > 0 && remaining <= REMINDER_AT_MS,
    connection: state.connection,
    error: state.error,
  };
}
