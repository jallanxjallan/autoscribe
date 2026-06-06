'use strict';

const { runWritingCommand } = require("./core");
const {
  extractResultPayload,
  markResultExported,
} = require("./asc");
const {
  ensureFinalNewline,
  stripLeadingResultFrontmatter,
} = require("./markdown");
const {
  absVaultPath,
  normalizeRelPath,
  resolveVaultRelativeDir,
  targetExists,
} = require("./vault");
const { identityRegexText } = require("./pending");

const {
  slugPrefix,
  slugRegexText,
} = require("../../lib/slug");

const fs = require("node:fs");
const path = require("node:path");

function fail(script, message) {
  console.error(`${script}: ERROR: ${message}`);
  process.exit(1);
}

function info(script, message) {
  console.error(`${script}: ${message}`);
}

function isProvisionalSlug(slug) {
  return slugPrefix(slug) === "prv";
}

function parseJsonStringObject(value) {
  const text = String(value || "").trim();
  if (!text || (!text.startsWith("{") && !text.startsWith("["))) return null;

  const parsed = JSON.parse(text);
  if (!parsed || typeof parsed !== "object") return null;
  return parsed;
}

function splitWords(value) {
  return String(value || "")
    .replace(/([a-z])([A-Z])/g, "$1 $2")
    .replace(/[_+\-.]+/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

function titleCaseStem(value) {
  const words = splitWords(value)
    .split(" ")
    .map(word => word.trim())
    .filter(Boolean);

  if (words.length === 0) return "";

  return words.map(word => {
    if (/^[A-Z0-9]{2,}$/.test(word)) return word;
    if (/^\d+$/.test(word)) return word;
    return `${word.slice(0, 1).toUpperCase()}${word.slice(1).toLowerCase()}`;
  }).join(" ");
}

function cleanFilenameStem(value) {
  let stem = String(value || "").trim();
  if (!stem) return "";

  stem = stem
    .replace(/[<>:"/\\|?*\x00-\x1F]/g, " ")
    .replace(/\s+/g, " ")
    .trim()
    .replace(/^[-.\s]+|[-.\s]+$/g, "");

  stem = titleCaseStem(stem)
    .replace(/[<>:"/\\|?*\x00-\x1F]/g, " ")
    .replace(/\s+/g, " ")
    .trim()
    .replace(/^[-.\s]+|[-.\s]+$/g, "");

  if (stem.length > 160) {
    stem = stem.slice(0, 160).trim().replace(/^[-.\s]+|[-.\s]+$/g, "");
  }

  return stem;
}

function filenameKeyScore(key) {
  const normalized = String(key || "")
    .replace(/[^a-zA-Z0-9]+/g, "_")
    .toLowerCase();

  if (!normalized) return 0;
  if (/^(filename|file_name|filename_hint|source_filename|source_filename_hint|basename|base_name)$/.test(normalized)) return 140;
  if (normalized.includes("filename") || normalized.includes("file_name")) return 130;
  if (/(^|_)file(_|$)/.test(normalized) && /(hint|name|path|source|origin|uri|url)/.test(normalized)) return 120;
  if (normalized.includes("filepath") || normalized.includes("file_path")) return 120;
  if (/^(path|source_path|origin_path|input_path|document_path)$/.test(normalized) || normalized.endsWith("_path")) return 110;
  if (/^(url|uri|source_url|source_uri|origin_url|origin_uri)$/.test(normalized) || normalized.endsWith("_url") || normalized.endsWith("_uri")) return 100;
  if (/^(title|name|label|heading|document_title|source_title)$/.test(normalized) || normalized.endsWith("_title") || normalized.endsWith("_name") || normalized.endsWith("_label")) return 85;
  if (/^(source|origin|provenance|input_record|raw_record|metadata)$/.test(normalized)) return 35;
  return 0;
}

function stringLooksLikeFilename(value) {
  const text = String(value || "").trim();
  if (!text || text.length > 500) return false;
  if (/\b[a-z][a-z0-9+.-]*:\/\//i.test(text)) return true;
  if (/[\\/]/.test(text)) return true;
  if (/\.[A-Za-z0-9]{1,12}(?:[?#].*)?$/.test(text)) return true;
  return false;
}

function looksLikeSlugOrIdentity(value) {
  const text = String(value || "").trim();
  if (!text) return true;
  if (new RegExp(`^${slugRegexText()}$`).test(text)) return true;
  if (new RegExp(`^${identityRegexText()}$`).test(text)) return true;
  return false;
}

function stemFromStringCandidate(value, allowPlainTitle = false) {
  let source = String(value || "").trim();
  if (!source || looksLikeSlugOrIdentity(source)) return "";

  if (!allowPlainTitle && !stringLooksLikeFilename(source)) return "";
  if (source.length > 500) return "";

  source = source.replace(/[?#].*$/, "");
  source = decodeURIComponent(source);

  if (/^[a-z][a-z0-9+.-]*:\/\//i.test(source)) {
    const parsed = new URL(source);
    source = parsed.pathname || source;
  }

  source = source.replace(/\\/g, "/");

  let base = source.includes("/") ? path.posix.basename(source) : source;
  base = base.replace(/^\.+/, "").trim();
  if (!base) return "";

  const parsed = path.parse(base);
  const stem = parsed.name || base;

  if (!allowPlainTitle && stem === base && !stringLooksLikeFilename(base)) return "";

  return cleanFilenameStem(stem);
}

function addFilenameCandidate(candidates, value, score, reason) {
  const allowPlainTitle = score >= 85;
  const stem = stemFromStringCandidate(value, allowPlainTitle);
  if (!stem) return;

  candidates.push({
    stem,
    raw: String(value || "").trim(),
    score,
    reason,
  });
}

function collectFilenameCandidates(value, candidates = [], options = {}) {
  const seen = options.seen || new Set();
  const keyPath = options.keyPath || [];
  const inheritedScore = options.inheritedScore || 0;

  if (value === null || value === undefined) return candidates;

  if (typeof value === "string") {
    const key = keyPath[keyPath.length - 1] || "";
    const keyScore = filenameKeyScore(key);
    const score = Math.max(inheritedScore, keyScore);

    if (score > 0) {
      addFilenameCandidate(candidates, value, score, keyPath.join("."));
    } else if (stringLooksLikeFilename(value)) {
      addFilenameCandidate(candidates, value, 25, keyPath.join(".") || "string");
    }

    const parsed = parseJsonStringObject(value);

    if (parsed) {
      collectFilenameCandidates(parsed, candidates, {
        seen,
        keyPath: [...keyPath, "json"],
        inheritedScore: Math.max(inheritedScore - 5, 0),
      });
    }

    return candidates;
  }

  if (typeof value !== "object") return candidates;
  if (seen.has(value)) return candidates;
  seen.add(value);

  if (Array.isArray(value)) {
    value.forEach((item, index) => {
      collectFilenameCandidates(item, candidates, {
        seen,
        keyPath: [...keyPath, String(index)],
        inheritedScore: Math.max(inheritedScore - 2, 0),
      });
    });

    return candidates;
  }

  for (const [key, child] of Object.entries(value)) {
    const keyScore = filenameKeyScore(key);
    const score = Math.max(inheritedScore, keyScore);

    collectFilenameCandidates(child, candidates, {
      seen,
      keyPath: [...keyPath, key],
      inheritedScore: score,
    });
  }

  return candidates;
}

function bestFilenameCandidate(...sources) {
  const candidates = [];

  for (const source of sources) {
    collectFilenameCandidates(source, candidates);
  }

  if (candidates.length === 0) {
    return { stem: "", raw: "", score: 0, reason: "" };
  }

  candidates.sort((a, b) => {
    if (b.score !== a.score) return b.score - a.score;
    if (a.stem.length !== b.stem.length) return a.stem.length - b.stem.length;
    return a.stem.localeCompare(b.stem);
  });

  return candidates[0];
}

function mdFilename(stem) {
  const cleaned = cleanFilenameStem(stem);
  return cleaned ? `${cleaned}.md` : "";
}

function allocateNamedTarget(root, targetDirRel, preferredStem, reservedRelPaths) {
  const baseStem = cleanFilenameStem(preferredStem);
  if (!baseStem) return null;

  for (let n = 1; n <= 999; n += 1) {
    const stem = n === 1 ? baseStem : `${baseStem} ${String(n).padStart(3, "0")}`;
    const relPath = normalizeRelPath(path.join(targetDirRel, mdFilename(stem)));

    if (reservedRelPaths.has(relPath)) continue;
    if (targetExists(root, relPath)) continue;

    reservedRelPaths.add(relPath);
    return relPath;
  }

  return null;
}

function allocateUntitledTarget(root, targetDirRel, reservedRelPaths, script) {
  for (let n = 1; n <= 9999; n += 1) {
    const stem = `Untitled ${String(n).padStart(3, "0")}`;
    const relPath = normalizeRelPath(path.join(targetDirRel, `${stem}.md`));

    if (reservedRelPaths.has(relPath)) continue;
    if (targetExists(root, relPath)) continue;

    reservedRelPaths.add(relPath);
    return relPath;
  }

  fail(script, "could not allocate an Untitled filename");
}

function selectWritenewCandidates({ vaultSlugs, pendingExports, script }) {
  const nonProvisionalCount = pendingExports.filter(record => !isProvisionalSlug(record.promptSlug)).length;

  const provisional = pendingExports
    .filter(record => isProvisionalSlug(record.promptSlug))
    .filter(record => !vaultSlugs.has(record.promptSlug));

  const bySlug = new Map();
  const duplicateTargets = new Map();

  for (const item of provisional) {
    if (bySlug.has(item.promptSlug)) {
      const list = duplicateTargets.get(item.promptSlug) || [bySlug.get(item.promptSlug)];
      list.push(item);
      duplicateTargets.set(item.promptSlug, list);
    } else {
      bySlug.set(item.promptSlug, item);
    }
  }

  if (duplicateTargets.size > 0) {
    const lines = ["multiple pending provisional results target the same slug:"];

    for (const [slug, records] of duplicateTargets.entries()) {
      lines.push(`  ${slug}`);
      for (const record of records) {
        lines.push(`    - call ${record.callIdentity}, result ${record.resultIdentity}`);
      }
    }

    fail(script, lines.join("\n"));
  }

  provisional.sort((a, b) => a.promptSlug.localeCompare(b.promptSlug));

  return {
    items: provisional,
    summaryLines: [
      `non-provisional pending exports skipped: ${nonProvisionalCount}`,
      `writenew candidates: ${provisional.length}`,
    ],
  };
}

function prepareWritenewItems({ root, items, options, script }) {
  const targetDir = resolveVaultRelativeDir({
    root,
    targetDirArg: options.targetDirArg,
    script,
  });

  const reservedRelPaths = new Set();
  const prepared = [];

  for (const item of items) {
    const exported = extractResultPayload({
      root,
      ascBin: options.ascBin,
      item,
      script,
    });

    const body = stripLeadingResultFrontmatter(exported.content).replace(/^\n+/, "");

    if (!body.trim()) {
      fail(script, `${item.promptSlug}: exported result content is empty after frontmatter stripping`);
    }

    const filenameCandidate = bestFilenameCandidate(item.raw, exported.raw);
    let targetPath = "";
    let filenameStrategy = "";

    if (filenameCandidate.stem) {
      targetPath = allocateNamedTarget(root, targetDir.relative, filenameCandidate.stem, reservedRelPaths);
      filenameStrategy = "heuristic";
    }

    if (!targetPath) {
      targetPath = allocateUntitledTarget(root, targetDir.relative, reservedRelPaths, script);
      filenameStrategy = "untitled";
    }

    prepared.push({
      ...item,
      body,
      path: targetPath,
      filenameStrategy,
      filenameStem: path.parse(path.basename(targetPath)).name,
      filenameHint: filenameCandidate.raw || "",
      filenameHintReason: filenameCandidate.reason || "",
      extractionIdentity: exported.extractionIdentity,
      extractionIdentityKind: exported.extractionIdentityKind,
    });
  }

  return {
    items: prepared,
    targetDir,
    summaryLines: [`target dir: ${targetDir.relative}`],
  };
}

function applyWritenewItem({ root, item, options, script }) {
  const fullPath = absVaultPath(root, item.path);

  if (fs.existsSync(fullPath)) {
    fail(script, `${item.path}: target file appeared before writenew; aborting`);
  }

  fs.mkdirSync(path.dirname(fullPath), { recursive: true });
  fs.writeFileSync(fullPath, ensureFinalNewline(item.body), "utf8");

  markResultExported({
    root,
    ascBin: options.ascBin,
    resultIdentity: item.resultIdentity,
    script,
  });

  info(script, `wrote: ${item.promptSlug} -> ${item.path}`);

  return {
    ...item,
    changed: true,
  };
}

function main() {
  return runWritingCommand({
    script: "writenew",
    mode: "writenew",
    defaultTargetDir: "new",
    selectCandidates: selectWritenewCandidates,
    prepareItems: prepareWritenewItems,
    applyItem: applyWritenewItem,
  });
}

module.exports = {
  main,
  selectWritenewCandidates,
  prepareWritenewItems,
  applyWritenewItem,
  isProvisionalSlug,
  bestFilenameCandidate,
  cleanFilenameStem,
  allocateNamedTarget,
  allocateUntitledTarget,
};

if (require.main === module) main();
