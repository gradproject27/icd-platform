// Generates TypeScript types from JSON Schemas, for two sets kept apart on purpose:
// - the six shared contracts, from contracts/schemas/*.schema.json into src/api/contracts/;
// - C1's API shapes (upload, job, ...), from docs/api/schemas/*.schema.json into src/api/c1/.
//
//   node scripts/gen-contract-types.mjs           write both folders
//   node scripts/gen-contract-types.mjs --check   exit 1 if any committed file differs
//
// The output is deterministic (sorted files, LF endings, no timestamps), so it is identical on
// Windows and Linux, like the backend's schema export.
//
// Some $defs appear in more than one schema (for example RiskLevel in incident and
// evidence-package). Each contract file keeps its own copy, and index.ts re-exports every name
// once, from the first file in sorted order. The script fails if two copies of a shared name are
// not identical, because then the schemas disagree and their owner (C3 or C1) has to fix them.

import { readdir, readFile, writeFile, mkdir } from "node:fs/promises";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { compile } from "json-schema-to-typescript";

const here = dirname(fileURLToPath(import.meta.url));

const TARGETS = [
  {
    schemasDir: resolve(here, "../../contracts/schemas"),
    outDir: resolve(here, "../src/api/contracts"),
    outName: "src/api/contracts",
    banner:
      "/* GENERATED from contracts/schemas by scripts/gen-contract-types.mjs. Do not edit by hand. */",
    owner: "C3",
  },
  {
    schemasDir: resolve(here, "../../docs/api/schemas"),
    outDir: resolve(here, "../src/api/c1"),
    outName: "src/api/c1",
    banner:
      "/* GENERATED from docs/api/schemas by scripts/gen-contract-types.mjs. Do not edit by hand. */",
    owner: "C1",
  },
];

const toLf = (text) => text.replace(/\r\n/g, "\n");

// Pydantic gives every field a `title`, which json-schema-to-typescript turns into one exported
// alias per field (IncidentId, Score, ...). Keep titles only on the root and on $defs entries,
// so the exported names are exactly the contract and its named definitions. A field written as
// {"$ref", "description", "default"} is reduced to the bare $ref for the same reason: otherwise
// the wrapper becomes a second copy of the definition (IncidentStatus and IncidentStatus1).
function stripFieldTitles(node, keepTitle = false) {
  if (Array.isArray(node)) return node.map((item) => stripFieldTitles(item));
  if (node === null || typeof node !== "object") return node;
  if (typeof node.$ref === "string") return { $ref: node.$ref };
  const out = {};
  for (const [key, value] of Object.entries(node)) {
    if (key === "title" && !keepTitle) continue;
    if (key === "$defs") {
      out.$defs = Object.fromEntries(
        Object.entries(value).map(([name, def]) => [name, stripFieldTitles(def, true)]),
      );
    } else if (key === "properties") {
      out.properties = Object.fromEntries(
        Object.entries(value).map(([name, prop]) => [name, stripFieldTitles(prop)]),
      );
    } else {
      out[key] = stripFieldTitles(value);
    }
  }
  return out;
}

async function generate({ schemasDir, banner, owner: schemaOwner }) {
  const files = (await readdir(schemasDir)).filter((f) => f.endsWith(".schema.json")).sort();
  const outputs = new Map();
  const owners = new Map(); // exported name -> { module, def }

  for (const file of files) {
    const name = file.replace(/\.schema\.json$/, "");
    const schema = JSON.parse(await readFile(join(schemasDir, file), "utf8"));

    for (const [defName, def] of Object.entries(schema.$defs ?? {})) {
      const owner = owners.get(defName);
      if (owner && JSON.stringify(owner.def) !== JSON.stringify(def)) {
        throw new Error(
          `$defs/${defName} differs between ${owner.module}.schema.json and ${file}. ` +
            `The schemas disagree; ask ${schemaOwner} to align them.`,
        );
      }
    }

    const ts = await compile(stripFieldTitles(schema, true), schema.title, {
      bannerComment: banner,
      cwd: schemasDir,
      strictIndexSignatures: true,
      unreachableDefinitions: true,
      style: { endOfLine: "lf" },
    });
    const text = toLf(ts);
    outputs.set(`${name}.ts`, text);

    const exported = [...text.matchAll(/^export (?:type|interface) (\w+)/gm)].map((m) => m[1]);
    for (const typeName of exported) {
      if (!owners.has(typeName)) {
        owners.set(typeName, { module: name, def: schema.$defs?.[typeName] ?? null });
      }
    }
  }

  const byModule = new Map();
  for (const [typeName, { module }] of owners) {
    if (!byModule.has(module)) byModule.set(module, []);
    byModule.get(module).push(typeName);
  }
  const lines = [banner, ""];
  for (const module of [...byModule.keys()].sort()) {
    const names = byModule.get(module).sort();
    lines.push(`export type {\n${names.map((n) => `  ${n},`).join("\n")}\n} from "./${module}";`);
  }
  outputs.set("index.ts", lines.join("\n") + "\n");
  return outputs;
}

const check = process.argv.includes("--check");
let failed = false;

for (const target of TARGETS) {
  const { outDir, outName } = target;
  const outputs = await generate(target);

  if (check) {
    const stale = [];
    const committed = new Set((await readdir(outDir).catch(() => [])).filter((f) => f.endsWith(".ts")));
    for (const [file, text] of outputs) {
      const current = await readFile(join(outDir, file), "utf8").catch(() => null);
      if (current === null || toLf(current) !== text) stale.push(file);
      committed.delete(file);
    }
    stale.push(...[...committed].map((f) => `${f} (not generated by this script)`));
    if (stale.length > 0) {
      console.error(
        `${outName} is out of date: ${stale.join(", ")}.
` +
          "Run `npm run contracts:gen` in frontend/ and commit the result.",
      );
      failed = true;
    } else {
      console.log(`${outName} is up to date (${outputs.size} files).`);
    }
  } else {
    await mkdir(outDir, { recursive: true });
    for (const [file, text] of outputs) await writeFile(join(outDir, file), text, "utf8");
    console.log(`Wrote ${outputs.size} files to ${outName}.`);
  }
}

if (failed) process.exit(1);
