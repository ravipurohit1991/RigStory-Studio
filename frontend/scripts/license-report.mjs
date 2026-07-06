import { readdir, readFile, writeFile } from "node:fs/promises";
import path from "node:path";

const root = process.cwd();
const nodeModules = path.join(root, "node_modules");
const outputPath = path.join(root, "frontend-license-report.json");
const packages = new Map();

async function readJson(filePath) {
  const raw = await readFile(filePath, "utf-8");
  return JSON.parse(raw);
}

async function collectPackage(packageDir) {
  try {
    const manifest = await readJson(path.join(packageDir, "package.json"));
    if (!manifest.name || !manifest.version) {
      return;
    }
    packages.set(`${manifest.name}@${manifest.version}`, {
      name: manifest.name,
      version: manifest.version,
      license: manifest.license ?? "UNKNOWN",
      repository:
        typeof manifest.repository === "string"
          ? manifest.repository
          : (manifest.repository?.url ?? null)
    });
  } catch {
    return;
  }
}

async function collectNodeModules(directory) {
  const entries = await readdir(directory, { withFileTypes: true });
  for (const entry of entries) {
    if (!entry.isDirectory() || entry.name.startsWith(".")) {
      continue;
    }
    const entryPath = path.join(directory, entry.name);
    if (entry.name.startsWith("@")) {
      const scopedEntries = await readdir(entryPath, { withFileTypes: true });
      await Promise.all(
        scopedEntries
          .filter((scopedEntry) => scopedEntry.isDirectory())
          .map((scopedEntry) => collectPackage(path.join(entryPath, scopedEntry.name)))
      );
      continue;
    }
    await collectPackage(entryPath);
  }
}

await collectNodeModules(nodeModules);

const report = [...packages.values()].sort((left, right) => {
  const byName = left.name.localeCompare(right.name);
  return byName === 0 ? left.version.localeCompare(right.version) : byName;
});

await writeFile(outputPath, `${JSON.stringify(report, null, 2)}\n`, "utf-8");
console.log(`Wrote ${report.length} package licenses to ${path.relative(root, outputPath)}`);
