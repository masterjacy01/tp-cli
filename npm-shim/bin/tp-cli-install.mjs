#!/usr/bin/env node
import { spawnSync } from "node:child_process";

const args = process.argv.slice(2);
const mode = args[0] ?? "install";
const target = args[1] ?? ".";

function run(cmd, argv) {
  return spawnSync(cmd, argv, { stdio: "inherit" });
}

function has(cmd, argv = ["--version"]) {
  const r = spawnSync(cmd, argv, { stdio: "ignore" });
  return r.status === 0;
}

if (mode !== "install") {
  console.error("Usage: npx -y tp-cli-install install [path-or-git-url]");
  process.exit(2);
}

if (has("pipx")) {
  const r = run("pipx", ["install", "--force", target]);
  process.exit(r.status ?? 1);
}

if (has("python3", ["-m", "pip", "--version"])) {
  const r = run("python3", ["-m", "pip", "install", "--upgrade", "--no-cache-dir", target]);
  if ((r.status ?? 1) !== 0) process.exit(r.status ?? 1);
} else if (has("python", ["-m", "pip", "--version"])) {
  const r = run("python", ["-m", "pip", "install", "--upgrade", "--no-cache-dir", target]);
  if ((r.status ?? 1) !== 0) process.exit(r.status ?? 1);
} else {
  console.error("Neither pipx nor python -m pip is available.");
  console.error("Install Python 3 and pipx, then run again.");
  process.exit(1);
}

console.log("\nInstalled tp-cli.");
console.log("Recommended first steps:");
console.log("  tp auth setup --browser chrome");
console.log("  tp doctor");
console.log("  tp workouts");
console.log("  tp workout <id> --full");
console.log("\nIf `tp` is not found, open a new shell session and try again.");
