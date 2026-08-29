"use strict";

const { makeSlug } = require("../lib/slug.js");

function normalizeKind(value) {
  return String(value || "").trim().toLowerCase();
}

function compactRegistryRecord(record) {
  if (!record) return null;
  if (typeof record === "string") return { key: record };
  return {
    key: record.key || record.slug || record.record_identity || null,
    slug: record.slug || null,
    kind: normalizeKind(record.kind || record.type),
    type: record.type || null,
    label: record.label || record.title || record.slug || record.key,
  };
}

function parseArgsJson(text, stepNumber) {
  const trimmed = String(text || "").trim();
  if (!trimmed) return {};
  const parsed = JSON.parse(trimmed);
  if (!parsed || Array.isArray(parsed) || typeof parsed !== "object") {
    throw new Error(`Step ${stepNumber}: args JSON must be an object.`);
  }
  return parsed;
}

const STEP_CONTRACT_ARG_KEYS = new Set([
  "index", "kind", "label", "instruction", "instruction_slug",
  "instruction_slugs", "engine", "script", "rag_profile", "model",
]);

function compactStepArgs(args) {
  const compact = {};
  for (const [key, value] of Object.entries(args || {})) {
    if (!STEP_CONTRACT_ARG_KEYS.has(key)) compact[key] = value;
  }
  return compact;
}

function normalizeStepKind(step) {
  const kind = normalizeKind(step?.kind || step?.step_kind || step?.type);
  if (["script", "rag", "llm"].includes(kind)) return kind;
  if (step?.script) return "script";
  if (step?.rag_profile) return "rag";
  return "llm";
}

function slugOf(record) {
  return String(record?.slug || record?.record_identity || record?.key || "").trim();
}

function buildPlanRecord({ label, description, steps, force_slug = null }) {
  const cleanLabel = String(label || "").trim();
  const cleanDescription = String(description || "").trim();
  if (!cleanLabel) throw new Error("Plan label is required.");
  if (!Array.isArray(steps) || !steps.length) throw new Error("At least one step is required.");

  const recordIdentity = force_slug || makeSlug("plan", cleanLabel);
  const planSteps = {};

  steps.forEach((step, index) => {
    const stepNumber = index + 1;
    const kind = normalizeStepKind(step);
    const engine = compactRegistryRecord(step.engine);
    const script = compactRegistryRecord(step.script);
    const ragProfile = compactRegistryRecord(step.rag_profile);
    const model = compactRegistryRecord(step.model);
    const args = compactStepArgs(parseArgsJson(step.argsJson, stepNumber));

    if (kind === "script" && !script?.key) throw new Error(`Step ${stepNumber}: choose a script.`);
    if (kind === "rag" && !ragProfile?.key) throw new Error(`Step ${stepNumber}: choose a RAG profile.`);
    if (kind === "llm" && !engine?.key) throw new Error(`Step ${stepNumber}: choose an LLM provider/engine.`);
    if (kind === "llm" && !model?.key) throw new Error(`Step ${stepNumber}: choose a model.`);

    const out = {
      index: stepNumber,
      kind,
      label: String(step.label || `Step ${stepNumber}`).trim() || `Step ${stepNumber}`,
    };
    if (Object.keys(args).length) out.args = args;
    if (engine?.key) out.engine = engine.key;
    if (kind === "llm") out.model = model.key;
    if (script?.key) out.script = script.key;
    if (ragProfile?.key) out.rag_profile = ragProfile.key;

    if (kind === "llm") {
      const refs = step.instruction_slugs && typeof step.instruction_slugs === "object" && !Array.isArray(step.instruction_slugs)
        ? step.instruction_slugs : {};
      const standing = Array.isArray(refs.standing) ? refs.standing.map(String).map((x) => x.trim()).filter(Boolean) : [];
      const role = Array.isArray(refs.role) ? refs.role.map(String).map((x) => x.trim()).filter(Boolean) : [];
      const context = Array.isArray(refs.context) ? refs.context.map(String).map((x) => x.trim()).filter(Boolean) : [];
      const task = Array.isArray(refs.task) ? refs.task.map(String).map((x) => x.trim()).filter(Boolean) : [];
      if (!task.length && step.task) task.push(slugOf(step.task));
      if (!task.length) throw new Error(`Step ${stepNumber}: choose a task instruction.`);
      out.instruction_slugs = {
        standing: [...new Set(standing)],
        role: role.slice(0, 1),
        context: context.slice(0, 1),
        task: task.slice(0, 1),
      };
    }
    planSteps[String(stepNumber)] = out;
  });

  return {
    record_type: "plan",
    record_identity: recordIdentity,
    record_content: cleanDescription,
    payload: {
      label: cleanLabel,
      description: cleanDescription,
      steps: planSteps,
    },
  };
}

module.exports = { buildPlanRecord };
