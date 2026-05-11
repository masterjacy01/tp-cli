#!/usr/bin/env node
import { spawnSync } from "node:child_process";
import { existsSync, readFileSync, rmSync } from "node:fs";
import { homedir } from "node:os";
import { join } from "node:path";

function run(cmd, args) {
  return spawnSync(cmd, args, { stdio: "inherit" });
}

function has(cmd, args = ["--version"]) {
  const r = spawnSync(cmd, args, { stdio: "ignore" });
  return r.status === 0;
}

function cleanupStaleTpLauncher() {
  const tpPath = join(homedir(), ".local", "bin", "tp");
  if (!existsSync(tpPath)) return;
  try {
    const content = readFileSync(tpPath, "utf8");
    const firstLine = content.split("\n")[0] ?? "";
    if (firstLine.startsWith("#!") && firstLine.includes("/trainingpeaks-cli/.venv/")) {
      rmSync(tpPath);
      console.log(`Removed stale launcher: ${tpPath}`);
    }
  } catch {
    // Non-fatal; continue install
  }
}

const args = process.argv.slice(2);
const mode = args[0] ?? "install";
const target = args[1] ?? ".";

if (mode !== "install") {
  console.error("Usage: npx @masterjacy01/tp-cli install [path-or-git-url]");
  process.exit(2);
}

cleanupStaleTpLauncher();

if (has("pipx")) {
  const r = run("pipx", ["install", "--force", target]);
  process.exit(r.status ?? 1);
}

if (has("python3", ["-m", "pip", "--version"])) {
  run("python3", ["-m", "pip", "uninstall", "-y", "tp-cli"]);
  const r = run("python3", ["-m", "pip", "install", "--user", "--upgrade", "--no-cache-dir", target]);
  if ((r.status ?? 1) !== 0) process.exit(r.status ?? 1);
  console.log("\nInstalled tp-cli.");
  console.log("Recommended first steps:");
  console.log("  tp auth setup --browser chrome");
  console.log("  tp doctor");
  console.log("  tp workouts");
  console.log("  tp workout <id> --full");
  console.log("\nIf `tp` is not found, open a new shell session and try again.");
  process.exit(0);
}

if (has("python", ["-m", "pip", "--version"])) {
  run("python", ["-m", "pip", "uninstall", "-y", "tp-cli"]);
  const r = run("python", ["-m", "pip", "install", "--user", "--upgrade", "--no-cache-dir", target]);
  if ((r.status ?? 1) !== 0) process.exit(r.status ?? 1);
  console.log("\nInstalled tp-cli.");
  console.log("Recommended first steps:");
  console.log("  tp auth setup --browser chrome");
  console.log("  tp doctor");
  console.log("  tp workouts");
  console.log("  tp workout <id> --full");
  console.log("\nIf `tp` is not found, open a new shell session and try again.");
  process.exit(0);
}

console.error("Neither pipx nor python -m pip is available.");
console.error("Install Python 3 and pipx, then run again.");
process.exit(1);
