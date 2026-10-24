// npm run countdown:measure: measures how far the displayed countdown is from the server's true
// remaining time. For each server clock skew it opens a window on the test server, reads it over
// REST like the dashboard does, and samples once per second for 10 seconds.
//
// It uses the dashboard's own clock maths (src/countdown/clock.ts). Node 22.18+ runs that
// TypeScript file directly, because it only uses erasable type syntax.

import { startCountdownServer } from "./countdown-server.mjs";
import { offsetFromRequest, parseIsoMs, remainingMs } from "../src/countdown/clock.ts";

const SKEWS_MS = [0, 90_000, -90_000];
const SAMPLES = 10;
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

async function measure(skewMs) {
  const server = await startCountdownServer({ skewMs, log: () => undefined });
  try {
    server.openWindow("inc-measure");
    const sentAtMs = Date.now();
    const response = await fetch(`${server.url}/response-windows/inc-measure`);
    const window = await response.json();
    const receivedAtMs = Date.now();
    const offsetMs = offsetFromRequest(window.server_time, sentAtMs, receivedAtMs);
    const deadlineMs = parseIsoMs(window.deadline_at);

    const differences = [];
    for (let sample = 0; sample < SAMPLES; sample += 1) {
      await sleep(1_000);
      const shown = remainingMs(window.deadline_at, offsetMs, Date.now());
      const truth = deadlineMs - server.serverNow();
      differences.push(Math.abs(shown - truth));
    }
    const naive = Math.abs(remainingMs(window.deadline_at, 0, Date.now()) - (deadlineMs - server.serverNow()));
    return {
      skewMs,
      max: Math.max(...differences),
      mean: differences.reduce((sum, d) => sum + d, 0) / differences.length,
      naive,
    };
  } finally {
    await server.close();
  }
}

console.log(`Countdown accuracy, ${SAMPLES} samples per skew, 1 s apart (target: < 1000 ms)\n`);
const rows = [];
for (const skewMs of SKEWS_MS) rows.push(await measure(skewMs));

const header = "| Server clock skew | Max abs. difference | Mean abs. difference | Naive client (no offset) |";
console.log(header);
console.log("|---|---|---|---|");
for (const row of rows) {
  const skew = `${row.skewMs > 0 ? "+" : ""}${row.skewMs / 1000} s`;
  console.log(`| ${skew} | ${row.max.toFixed(1)} ms | ${row.mean.toFixed(1)} ms | ${(row.naive / 1000).toFixed(1)} s |`);
}
const worst = Math.max(...rows.map((row) => row.max));
console.log(`\nWorst case ${worst.toFixed(1)} ms: ${worst < 1000 ? "within" : "NOT within"} the 1-second target.`);
process.exitCode = worst < 1000 ? 0 : 1;
