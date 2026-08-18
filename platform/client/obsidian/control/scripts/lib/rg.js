const { runCommandSync } = require("./shell");

const { loadConfig } = require("./config-loader");
function defaultRg() {
  const cfg = loadConfig("paths");
  return process.env[String(cfg.environment?.rg_primary || "OBSIDIAN_RG_BIN")]
    || process.env[String(cfg.environment?.rg_secondary || "RG_BIN")]
    || String(cfg.rg_command || "rg");
}

function rgAvailable(rg = defaultRg()) {
  try {
    const result = runCommandSync(rg, ["--version"], { check: false });
    return result.status === 0;
  } catch (_) {
    return false;
  }
}

function runRg(args, options = {}) {
  const rg = options.rg || defaultRg();
  return runCommandSync(rg, args, {
    cwd: options.cwd,
    check: options.check ?? false,
    maxBuffer: options.maxBuffer ?? Number(loadConfig("workflow").control_loader?.rg_max_buffer_bytes || 20971520),
  });
}

function rgLines(args, options = {}) {
  const result = runRg(args, options);
  return String(result.stdout || "")
    .split(/\r?\n/)
    .filter(Boolean);
}

function findSlugLines({ root, prefixes = [], rg = defaultRg() } = {}) {
  if (!root) throw new Error("findSlugLines requires root.");

  const pattern = prefixes.length > 0
    ? `^slug:\\s*(${prefixes.map(escapeRegex).join("|")})\\.`
    : "^slug:\\s*[^[:space:]]+";

  return rgLines([
    "--line-number",
    "--no-heading",
    "--glob", "*.md",
    pattern,
    ".",
  ], { cwd: root, rg });
}

function buildSlugPathMap({ root, prefixes = [], rg = defaultRg() } = {}) {
  const map = new Map();
  const duplicates = new Map();

  for (const line of findSlugLines({ root, prefixes, rg })) {
    const match = line.match(/^(.+?):(\d+):\s*slug:\s*(\S+)\s*$/);
    if (!match) continue;

    const [, relPath, lineNumber, slug] = match;
    const cleanPath = relPath.replace(/^\.\//, "");
    const record = {
      slug,
      path: cleanPath,
      lineNumber: Number(lineNumber),
    };

    if (map.has(slug)) {
      const list = duplicates.get(slug) || [map.get(slug)];
      list.push(record);
      duplicates.set(slug, list);
    } else {
      map.set(slug, record);
    }
  }

  return { bySlug: map, duplicates };
}

function escapeRegex(text) {
  return String(text).replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

module.exports = {
  DEFAULT_RG: defaultRg(),
  rgAvailable,
  runRg,
  rgLines,
  findSlugLines,
  buildSlugPathMap,
};
