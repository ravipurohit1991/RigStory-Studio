/** Test-only loader for the shared fixtures under samples/. */

import { readFileSync } from "node:fs";
import { resolve } from "node:path";

// Vitest runs with the frontend package as the working directory.
const samplesRoot = resolve(process.cwd(), "..", "samples");

export function readSample(relativePath: string): unknown {
  return JSON.parse(readFileSync(resolve(samplesRoot, relativePath), "utf-8"));
}
