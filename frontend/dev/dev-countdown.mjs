// npm run dev:countdown: the normal Vite dev server, with /api and /ws proxied to the countdown
// test server (npm run countdown:server, port 8001) instead of the real API on port 8000.
// Uses Vite's JS API so it works the same in PowerShell, cmd and bash, with no extra dependency.

import { createServer } from "vite";

process.env.ICD_API_TARGET ??= "http://localhost:8001";

const server = await createServer();
await server.listen();
server.printUrls();
console.log(`  /api and /ws are proxied to ${process.env.ICD_API_TARGET}`);
