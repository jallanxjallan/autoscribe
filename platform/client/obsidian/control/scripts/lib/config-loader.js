"use strict";

const fs = require("node:fs");
const path = require("node:path");

const CONFIG_ROOT = path.resolve(__dirname, "..", "..", "config");
const CACHE = new Map();

function stripComment(line) {
  let quote = null;
  let escaped = false;
  for (let i = 0; i < line.length; i += 1) {
    const ch = line[i];
    if (escaped) { escaped = false; continue; }
    if (ch === "\\" && quote === '"') { escaped = true; continue; }
    if (quote) {
      if (ch === quote) quote = null;
      continue;
    }
    if (ch === '"' || ch === "'") { quote = ch; continue; }
    if (ch === "#" && (i === 0 || /\s/.test(line[i - 1]))) return line.slice(0, i).trimEnd();
  }
  return line.trimEnd();
}

function scalar(raw) {
  const value = String(raw ?? "").trim();
  if (value === "") return "";
  if (value === "null" || value === "~") return null;
  if (value === "true") return true;
  if (value === "false") return false;
  if (/^-?(?:0|[1-9]\d*)(?:\.\d+)?$/.test(value)) return Number(value);
  if (value.startsWith('"') && value.endsWith('"')) return JSON.parse(value);
  if (value.startsWith("'") && value.endsWith("'")) return value.slice(1, -1).replace(/''/g, "'");
  if ((value.startsWith("[") && value.endsWith("]")) || (value.startsWith("{") && value.endsWith("}"))) {
    try { return JSON.parse(value); } catch (_) {}
  }
  return value;
}

function tokenize(text) {
  const lines = [];
  String(text || "").split(/\r?\n/).forEach((raw, index) => {
    if (/\t/.test(raw.match(/^\s*/)?.[0] || "")) throw new Error(`Tabs are not allowed in config YAML (line ${index + 1}).`);
    const cleaned = stripComment(raw);
    if (!cleaned.trim()) return;
    const indent = cleaned.match(/^ */)[0].length;
    if (indent % 2 !== 0) throw new Error(`Config indentation must use multiples of two spaces (line ${index + 1}).`);
    lines.push({ indent, text: cleaned.trim(), line: index + 1 });
  });
  return lines;
}

function parseYaml(text) {
  const lines = tokenize(text);
  if (!lines.length) return {};

  function parseBlock(start, indent) {
    const isList = lines[start]?.indent === indent && lines[start]?.text.startsWith("- ");
    const output = isList ? [] : {};
    let index = start;

    while (index < lines.length) {
      const item = lines[index];
      if (item.indent < indent) break;
      if (item.indent > indent) throw new Error(`Unexpected indentation at config line ${item.line}.`);

      if (isList) {
        if (!item.text.startsWith("- ")) throw new Error(`Mixed list/map block at config line ${item.line}.`);
        output.push(scalar(item.text.slice(2)));
        index += 1;
        continue;
      }

      if (item.text.startsWith("- ")) throw new Error(`Mixed map/list block at config line ${item.line}.`);
      const match = item.text.match(/^([^:]+):(?:\s+(.*))?$/);
      if (!match) throw new Error(`Unsupported config YAML at line ${item.line}: ${item.text}`);
      const key = match[1].trim();
      if (Object.prototype.hasOwnProperty.call(output, key)) {
        throw new Error(`Duplicate config key '${key}' at line ${item.line}.`);
      }
      const rest = match[2];
      if (rest !== undefined) {
        output[key] = scalar(rest);
        index += 1;
        continue;
      }

      const next = lines[index + 1];
      if (!next || next.indent <= indent) {
        output[key] = {};
        index += 1;
        continue;
      }
      if (next.indent !== indent + 2) throw new Error(`Config nesting must advance by two spaces (line ${next.line}).`);
      const parsed = parseBlock(index + 1, indent + 2);
      output[key] = parsed.value;
      index = parsed.index;
    }
    return { value: output, index };
  }

  return parseBlock(0, lines[0].indent).value;
}

function configPath(name) {
  const clean = String(name || "").replace(/\.ya?ml$/i, "");
  if (!/^[a-z0-9_-]+$/i.test(clean)) throw new Error(`Invalid config name: ${name}`);
  return path.join(CONFIG_ROOT, `${clean}.yaml`);
}

function loadConfig(name) {
  const file = configPath(name);
  const stat = fs.statSync(file);
  const cached = CACHE.get(file);
  if (cached && cached.mtimeMs === stat.mtimeMs && cached.size === stat.size) return cached.value;
  const value = parseYaml(fs.readFileSync(file, "utf8"));
  CACHE.set(file, { mtimeMs: stat.mtimeMs, size: stat.size, value });
  return value;
}

function getConfig(pathSpec, fallback = undefined) {
  const parts = Array.isArray(pathSpec) ? pathSpec : String(pathSpec || "").split(".").filter(Boolean);
  if (!parts.length) return fallback;
  let current = loadConfig(parts.shift());
  for (const part of parts) {
    if (current == null || !Object.prototype.hasOwnProperty.call(current, part)) return fallback;
    current = current[part];
  }
  return current;
}

function configEntries(pathSpec) {
  const value = getConfig(pathSpec, {});
  return value && typeof value === "object" && !Array.isArray(value) ? Object.entries(value) : [];
}

module.exports = { CONFIG_ROOT, parseYaml, loadConfig, getConfig, configEntries };
