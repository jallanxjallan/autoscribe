#!/usr/bin/env node

// reset-manifests.js
// Reset all AutoScribe client-side JSON manifests.
// Default is dry-run. Use --apply to write changes.

const fs = require("fs");
const path = require("path");
const APPLY = process.argv.includes("--apply");

function activeVaultRoot() {
  const root = process.env.OBSIDIAN_VAULT_ROOT || process.cwd();
  return path.resolve(root);
}

const STATE_ROOT =
  process.env.AUTOSCRIBE_MANIFEST_ROOT ||
  path.join(activeVaultRoot(), ".autoscribe");

const MANIFEST_NAMES = new Set([
  "selection.json",
  "selections.json",
  "run-manifest.json",
  "current-run.json",
  "manifest.json",
]);

function walk(dir, found = []) {
  if (!fs.existsSync(dir)) return found;

  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const fullPath = path.join(dir, entry.name);

    if (entry.isDirectory()) {
      walk(fullPath, found);
    } else if (
      entry.isFile() &&
      entry.name.endsWith(".json") &&
      isManifestPath(fullPath)
    ) {
      found.push(fullPath);
    }
  }

  return found;
}

function isManifestPath(filePath) {
  const parts = filePath.split(path.sep);
  const base = path.basename(filePath);

  return (
    MANIFEST_NAMES.has(base) ||
    parts.includes("selections") ||
    parts.includes("manifests") ||
    parts.includes("runs") ||
    parts.includes("writeback") ||
    parts.includes("writenew")
  );
}

function resetValueFor(filePath) {
  const parts = filePath.split(path.sep);

  if (parts.includes("selections")) {
    return {
      selected: [],
      updated_at: null,
    };
  }

  if (parts.includes("runs")) {
    return {
      type: "run_manifest",
      calls: [],
      updated_at: null,
    };
  }

  if (parts.includes("writeback") || parts.includes("writenew")) {
    return {
      items: [],
      updated_at: null,
    };
  }

  return {};
}

function main() {
  const files = walk(STATE_ROOT);

  if (files.length === 0) {
    console.log(`reset-manifests: no manifests found under ${STATE_ROOT}`);
    return;
  }

  console.log(`reset-manifests: root: ${STATE_ROOT}`);
  console.log(`reset-manifests: mode: ${APPLY ? "apply" : "dry-run"}`);

  for (const file of files) {
    const nextValue = resetValueFor(file);
    console.log(`${APPLY ? "reset" : "would reset"}: ${file}`);

    if (APPLY) {
      fs.writeFileSync(file, JSON.stringify(nextValue, null, 2) + "\n");
    }
  }

  if (!APPLY) {
    console.log("reset-manifests: dry-run only; rerun with --apply to write changes");
  }
}

main();