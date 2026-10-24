# Server-driven countdown prototype

| | |
|---|---|
| **Project** | ICD (Intelligent Cyber Defense) |
| **Owner** | C4, Frontend & Security Dashboard |
| **Task** | T1-11 (Week 1) |
| **Status** | Prototype. It runs against a local test server, because the real backend has no response window yet |
| **Sources** | [response-workflow-spec.md](response-workflow-spec.md) sections 5 to 8 and 10 (C5); [auth-and-threat-model.md](auth-and-threat-model.md) A2.8 and A2.14; NFR-P-09, FR-43 |

## 1. Purpose

When a freeze starts, the analyst has 60 seconds to decide (FR-43). The dashboard must show how much of that time is left. NFR-P-09 and spec section 7 require the deadline to belong to the server: the displayed countdown must be within **1 second** of the server's true remaining time, even if the browser's clock is wrong.

This prototype shows that the dashboard can meet that target. It contains:

- the clock maths;
- a React hook and component that display the server's deadline;
- a test server that plays the backend's role;
- the tests and measurements below.

## 2. The rule

- **The server owns the deadline.** The server creates the window and sets `deadline_at` from the database clock (spec section 7, rule 1). The browser never starts its own 60-second timer and never computes a deadline.
- **The browser only computes the remaining time:** `remaining = deadline_at − server_now`, where `server_now` is estimated as the client clock plus an offset measured from the server's `server_time`.
- **Re-rendering holds no time state.** The component re-renders every 250 ms while the window is open, but each tick recomputes the value from `deadline_at`. Nothing counts down on the client.
- **Refreshing, reconnecting or opening a second tab reads the same window.** The client only ever sends GET requests for the window. Nothing on the client can create, restart or extend one.
- **The server decides when the window has expired.** At the deadline the client shows `0:00`, and it shows the expired text only when the server says `expired`, either through the `response_window.expired` event or a REST read.

## 3. How the offset works

The browser's clock and the server's clock can differ by seconds or minutes. The offset is the estimated difference, `server clock − client clock`. Both formulas are in `frontend/src/countdown/clock.ts`.

| Source | Formula | Why |
|---|---|---|
| WebSocket event (spec section 7) | `offset = server_time − received_at` | The event carries the server's clock at send time. Network delay makes the offset slightly too small, by about one-way latency |
| REST read | `offset = server_time − (sent_at + received_at) / 2` | The server read its clock somewhere between sending and receiving. The midpoint halves the error of a slow request |

Then `remaining = deadline_at − (client_now + offset)`, never below 0, and it's shown as `m:ss` rounded **up** to the next whole second. So `0:00` appears only when the time is really up: 59 001 ms shows `1:00` and 1 ms shows `0:01`.

The offset is refreshed on every REST read and every WebSocket event. A time string without a time zone, or one that can't be parsed, is rejected with an error. It never produces `NaN`.

## 4. Code

| File | What it does |
|---|---|
| `frontend/src/countdown/clock.ts` | Pure functions: `offsetFromPush`, `offsetFromRequest`, `remainingMs`, `formatRemaining` |
| `frontend/src/api/responseWindows.ts` | The hand-written `ResponseWindow` type and `ResponseWindowEvent` union (proposed shape from spec section 7), `getResponseWindow()` (404 → no window), and the WebSocket URL on the page's own origin |
| `frontend/src/hooks/useResponseWindow.ts` | REST read on mount, then the WebSocket. Reconnects with backoff 1 s, 2 s, 4 s, then every 10 s, and reads the window again after a reconnect |
| `frontend/src/components/Countdown.tsx` | The display. The number has `role="timer"` and `aria-live="off"`, so a screen reader doesn't read every second; state changes and the 30-second reminder go to a separate polite live region |
| `frontend/src/pages/PendingDecisionPage.tsx` | Uses `<Countdown>` in place of the T1-11 placeholder |

The browser calls only its own origin (A2.14). REST goes through `request()` to `/api/response-windows/{incident_id}`, and the WebSocket goes to `/ws/response-windows?incident_id=...`, with `ws:` or `wss:` to match the page. `src/` contains no host or port.

## 5. The test server

`frontend/dev/countdown-server.mjs` plays the backend's role. It is for **development and tests only**. No `src/` application code imports it, and it isn't part of the production build or the Docker image (the image contains only `dist/`).

- **Server clock:** `serverNow() = Date.now() + skewMs`. Every time it sends comes from this clock, so a skew of, for example, +90 s simulates a browser whose clock is 90 s behind the server.
- **REST** (paths as the backend would see them after the `/api` prefix is stripped):

| Request | Answer |
|---|---|
| `GET /response-windows/{incident_id}` | 200 with `incident_id`, `window_id`, `status` (`open`, `decided` or `expired`), `started_at`, `deadline_at`, `server_time`, `recommended_scenario_id`. 404 `{"detail": "no response window"}` if there is none. Reading never creates anything |
| `POST /dev/response-windows/{incident_id}` | Test only. Opens a window with `deadline_at = started_at + 60 s` and `recommended_scenario_id = "S2"`. 409 if a window is already open, and nothing changes (spec section 5, rule 4) |
| `POST /dev/response-windows/{incident_id}/decide` | Test only. Sets `decided` only while `serverNow() < deadline_at`, otherwise 409 `"window expired"` (spec section 10, case 4) |

- **WebSocket** at `/ws/response-windows?incident_id=...` pushes `response_window.opened`, `.reminder` (30 s left), `.decided` and `.expired` (once, at or after `deadline_at`). Each event is `{"type": "...", ...fields}` with the fields from spec section 7, and `server_time` is set when the event is sent. On connect it sends nothing extra; the client reads the current state over REST.
- **Logging:** one line per request and per event, stamped with the server's clock, with the remaining time while a window is open.
- **No authentication.** The real channel checks the `icd_session` cookie and the `Origin` header at the handshake, and closes the socket when the session ends (A2.8). The test server does neither.

### How to run it

```powershell
cd frontend
npm run countdown:server                         # terminal 1: test server on port 8001
npm run countdown:server -- --skew-ms 90000      #   or with the server clock 90 s ahead
npm run dev:countdown                            # terminal 2: dashboard, /api and /ws -> 8001
curl.exe -X POST http://localhost:8001/dev/response-windows/inc-demo   # open a window
# then open http://localhost:5173/incidents/inc-demo/decision
npm run countdown:measure                        # accuracy table (about 30 s)
```

`npm run dev:countdown` is the normal dev server with `ICD_API_TARGET=http://localhost:8001`. `vite.config.ts` reads `ICD_API_TARGET` for both the `/api` and `/ws` proxies (default `http://localhost:8000`, the real API).

## 6. Results

Measured on **25 October 2026**, Windows 11 Pro, Node.js 24.15.0, test server and client on the same machine.

### `npm run countdown:measure` (10 samples per skew, 1 s apart)

| Server clock skew | Max abs. difference | Mean abs. difference | Naive client (no offset) |
|---|---|---|---|
| 0 s | 4.5 ms | 4.5 ms | 0.0 s |
| +90 s | 1.5 ms | 1.5 ms | 90.0 s |
| -90 s | 1.5 ms | 1.5 ms | 49.9 s |

Worst case 4.5 ms: within the 1-second target.

The "naive client" column shows what a client that ignores the offset would display. With +90 s skew it is 90 s wrong. With −90 s it believes the deadline has already passed, so it shows `0:00` (clamped) while about 50 s are really left: an error of 49.9 s.

### Accuracy test (`frontend/src/countdown/accuracy.test.ts`, part of `npm test`)

It runs against the real test server in-process, using the dashboard's own REST client and a real WebSocket, with 5 samples over about 2 seconds per skew.

| Check | Result |
|---|---|
| Skew 0 ms: max \|shown − server\| | 2.5 ms (< 1000 ms) |
| Skew +90 000 ms: max \|shown − server\| | 5.5 ms (< 1000 ms) |
| Skew −90 000 ms: max \|shown − server\| | 2.0 ms (< 1000 ms) |
| Naive client with skew +90 s is more than 80 s wrong | Pass |
| Refresh: two reads return the same `window_id` and `deadline_at`; a second open while open returns 409 and the deadline is unchanged | Pass |
| `response_window.expired` arrives exactly once, with `server_time` at or after `deadline_at` (2-second window) | Pass |

These numbers are for a local connection. Over a real network the REST offset error is at most half the round trip, so a round trip under about 2 seconds still meets the target.

### Component tests (`frontend/src/components/Countdown.test.tsx`, fake clock and fake WebSocket)

| Check | Result |
|---|---|
| Shows `1:00`, then `0:30` after 30 s, with the "30 seconds left" reminder | Pass |
| A server clock 90 s ahead still shows `1:00`, not `2:30` | Pass |
| Socket URL is on the page's own origin; REST goes to `/api/response-windows/{id}` | Pass |
| At the deadline it shows `0:00`; the `expired` event shows the expired text | Pass |
| The `decided` event shows "Decision recorded." | Pass |
| 404 shows "No response window. No automatic action will run." | Pass |
| Connection lost: "Reconnecting…" is shown and the countdown keeps going (`0:50` after 10 s); after reconnecting it reads the window again | Pass |
| Mounting again (a page refresh) continues at `0:40`, not `1:00`; the client sends only GET requests | Pass |

### Dev setup check (automated, no browser)

With `npm run countdown:server -- --skew-ms 90000` and `npm run dev:countdown` running:

- `GET http://localhost:5173/api/response-windows/inc-demo` reached the test server with `/api` stripped;
- `/incidents/inc-demo/decision` was served (HTTP 200);
- a WebSocket through `ws://localhost:5173/ws/response-windows?incident_id=inc-demo` received the `response_window.decided` event.

### Browser checks (manual)

**Not run yet.** There was no browser in the environment where the prototype was built. The automated tests above cover the same behaviour. Run these steps with the commands in section 5 and record the results here.

| # | Check | Result |
|---|---|---|
| a | The countdown matches the remaining time in the test server's log within 1 s | NOT VERIFIED |
| a′ | Same with `--skew-ms 90000` | NOT VERIFIED |
| b | After F5 the countdown continues from the same value; it does not restart at 1:00 | NOT VERIFIED |
| c | A second tab shows the same value | NOT VERIFIED |
| d | Stopping the test server shows "Reconnecting…" while the countdown keeps going; restarting it recovers | NOT VERIFIED |
| e | At 0 it shows "Window expired at … The system selects a scenario (SIMULATED)." | NOT VERIFIED |

For check (d), restart the server with the same skew. A restarted test server has no windows in memory: after reconnecting, the REST read returns 404 and the page shows "No response window". That is the correct behaviour for a server that lost its state. Open a new window with the `curl.exe` command to continue. The real backend keeps windows in PostgreSQL, so a restart doesn't lose them.

## 7. What the real backend must provide

1. **REST read** of an incident's window, with the fields of the `response_window.opened` event plus `status` (`open`, `decided` or `expired`). 404 when there is none. A read never creates or extends a window.
2. **The four WebSocket events** from spec section 7, with these fields:
   - `response_window.opened`: `incident_id`, `window_id`, `started_at`, `deadline_at`, `server_time`, `recommended_scenario_id`;
   - `response_window.reminder`: `incident_id`, `window_id`, `deadline_at`, `server_time`;
   - `response_window.decided`: `incident_id`, `window_id`, `server_time`;
   - `response_window.expired`: `incident_id`, `window_id`, `server_time`.
3. **`server_time` from the database clock**, the same clock as `deadline_at` (spec section 7, rule 1). It must be set when the response or event is sent, not when the window was created.
4. **Times in ISO 8601 UTC with milliseconds**, for example `2026-11-02T09:15:30.250Z`.
5. **Authentication on the socket:** check the `icd_session` cookie and the `Origin` header at the handshake, and close the socket when the session expires or is revoked (A2.8).
6. **Same origin:** both paths reachable under the dashboard's origin through the `/api` and `/ws` proxies (A2.14). The dev server and nginx already proxy them.

## 8. Open questions for C1 and C5

| # | Question | Prototype's choice | Who decides |
|---|---|---|---|
| 1 | Final REST path for reading the window | `GET /response-windows/{incident_id}` (`/api/response-windows/...` from the browser) | C1, C5 |
| 2 | Final WebSocket path | `/ws/response-windows?incident_id=...` | C1, C5 |
| 3 | One socket per incident, or one socket per user that carries all incidents? | One per incident page. One per user would also serve the incident list's "Decision needed" badges (wireframes 4.3) | C1, C5 |
| 4 | Is `response_window.opened` sent again on reconnect? | No. The client reads the window over REST after every reconnect | C5 |
| 5 | Can the REST read return a window that is `decided` or `expired`, so the page can show the outcome after a refresh? | Yes, the latest window with its status | C5 |
| 6 | Is `recommended_scenario_id` nullable when no catalogue scenario matches (spec section 6)? | Yes, the type allows `null` | C5 |
