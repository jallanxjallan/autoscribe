"use strict";

const path = require("node:path");
const { getFrontmatterEntry } = require("../lib/frontmatter.js");
const { normalizeWikiTarget } = require("../lib/wikilinks.js");
const { vaultRoot } = require("../lib/vault-state.js");
const { loadConfig } = require("../lib/config-loader.js");

function propertySpecs() {
  return Object.entries(loadConfig("instructions").resolver_properties || {}).map(([property, item]) => ({ property, ...item }));
}

function links(value) {
  const values = Array.isArray(value) ? value : value == null || value === "" ? [] : [value];
  return values.map(normalizeWikiTarget).filter(Boolean);
}

function component(app, file, expectedPrefix, sourceLabel) {
  const slug = String(getFrontmatterEntry(app, file, "slug") || "").trim();
  if (!slug) throw new Error(`${file.path}: missing slug.`);
  if (expectedPrefix && !slug.startsWith(expectedPrefix)) {
    throw new Error(`${sourceLabel}: expected ${expectedPrefix}* slug, found ${slug}.`);
  }
  return {
    slug,
    path: file.path,
    source_path: file.path,
    abspath: path.resolve(vaultRoot(app), file.path),
  };
}

function resolveLink(app, taskFile, target, spec) {
  const file = app.metadataCache.getFirstLinkpathDest(target, taskFile.path);
  if (!file) throw new Error(`${taskFile.path}: unresolved ${spec.property} wikilink ${target}.`);
  return component(app, file, spec.prefix, `${taskFile.path} ${spec.property}`);
}

function uniqueComponents(items) {
  const seen = new Map();
  for (const item of items) {
    const prior = seen.get(item.slug);
    if (prior && prior.path !== item.path) {
      throw new Error(`Instruction slug ${item.slug} resolves to both ${prior.path} and ${item.path}.`);
    }
    if (!prior) seen.set(item.slug, item);
  }
  return [...seen.values()];
}

function resolveInstructionStack(app, instruction) {
  if (!instruction?.path) {
    throw new Error(`Instruction ${instruction?.slug || "<unknown>"} has no local path.`);
  }
  const taskFile = app.vault.getAbstractFileByPath(instruction.path);
  if (!taskFile) throw new Error(`Instruction file not found: ${instruction.path}`);

  const groups = {};
  const ordered = [];
  for (const spec of propertySpecs()) {
    const resolved = links(getFrontmatterEntry(app, taskFile, spec.property))
      .map((target) => resolveLink(app, taskFile, target, spec));
    groups[spec.payload] = uniqueComponents(resolved);
    ordered.push(...groups[spec.payload]);
  }

  const task = component(app, taskFile, null, taskFile.path);
  groups.instructions = [task];
  ordered.push(task);

  const components = uniqueComponents(ordered);
  return {
    instruction_slugs: {
      role: groups.role.map((item) => item.slug),
      context: groups.context.map((item) => item.slug),
      specifics: groups.specifics.map((item) => item.slug),
      instructions: groups.instructions.map((item) => item.slug),
    },
    components,
  };
}

module.exports = {
  PROPERTY_SPECS: propertySpecs(),
  links,
  resolveInstructionStack,
};
