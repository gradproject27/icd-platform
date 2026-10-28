// npm run dev:countdown and npm run dev:stub: the normal Vite dev server, with /api and /ws
// proxied to a local test server on port 8001 instead of the real API on port 8000:
// the countdown test server (npm run countdown:server) or the stub server (npm run stub:server).
// Uses Vite's JS API so it works the same in PowerShell, cmd and bash, with no extra dependency.

import { createServer } from "vite";

process.env.ICD_API_TARGET ??= "http://localhost:8001";
const serverName = process.argv.includes("--stub") ? "stub server" : "countdown test server";

const server = await createServer();
await server.listen();
server.printUrls();
console.log(`  /api and /ws are proxied to ${process.env.ICD_API_TARGET} (${serverName})`);
