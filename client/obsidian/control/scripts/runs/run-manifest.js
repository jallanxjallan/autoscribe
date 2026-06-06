const path = require('path');
const { makeSlug } = require('../lib/slug.js');
const { vaultRoot, writeJson, workflowDir } = require('../lib/vault-state.js');

function compactPrompt(item) {
  return {
    index: item.index,
    call_slug: item.slug || null,
    prompt_slug: item.slug || null,
    label: item.label || null,
    path: item.path || null,
    abspath: item.abspath || null,
    filename: item.path ? path.basename(item.path) : (item.label || ''),
    type: item.type || null,
    status: item.status || null,
    stage: item.stage || null,
    process: item.process || null,
    exists: item.exists,
    size: item.size || null,
    mtime: item.mtime || null,
    repo_state: item.repo_state || null,
    git_status: item.git_status || '',
    git_commit: item.git_commit || null,
    short_commit: item.short_commit || null,
    has_prior_commit: Boolean(item.has_prior_commit),
  };
}

function compactTarget(record) {
  if (!record) return null;
  return {
    key: record.key || null,
    slug: record.slug || null,
    label: record.label || record.key || record.slug || null,
    kind: record.kind || record.type || null,
    type: record.type || null,
    module: record.module || null,
    callable: record.callable || null,
    path: record.path || null,
  };
}

function compactPlanStep(step, index) {
  return {
    index: step.index || index + 1,
    label: step.label || `Step ${index + 1}`,
    engine: compactTarget(step.engine),
    script: compactTarget(step.script),
    rag_profile: compactTarget(step.rag_profile),
    args: step.args && typeof step.args === 'object' && !Array.isArray(step.args) ? step.args : {},
    instructions: Array.isArray(step.instructions)
      ? step.instructions.map((ins) => ({
          slug: ins.slug || null,
          label: ins.label || null,
          kind: ins.kind || null,
          path: ins.path || null,
        }))
      : [],
  };
}

function buildRunManifest({ app, label, selection, plan }) {
  if (!selection || !Array.isArray(selection.items)) throw new Error('A loaded selection is required.');
  if (!plan?.slug) throw new Error('A saved plan with a slug is required.');

  const root = vaultRoot(app);
  const now = new Date().toISOString();
  const cleanLabel = String(label || '').trim() || `${selection.selection_name || 'selection'} + ${plan.label || plan.slug}`;
  const slug = makeSlug('run', cleanLabel);
  const prompts = selection.items.map(compactPrompt);
  const steps = (Array.isArray(plan.steps) ? plan.steps : []).map(compactPlanStep);

  return {
    type: 'run_manifest',
    version: 1,
    label: cleanLabel,
    slug,
    created: now,
    updated: now,
    vault: {
      name: path.basename(root),
      root,
    },
    source_selection: {
      path: selection.selection_file,
      name: selection.selection_name,
      mtime: selection.selection_mtime,
      raw_type: selection.raw_type,
    },
    plan: {
      slug: plan.slug,
      label: plan.label || null,
      description: plan.description || '',
      step_count: steps.length,
      steps,
    },
    call_count: prompts.length,
    calls: prompts.map((prompt, index) => ({
      index: index + 1,
      call_slug: prompt.call_slug,
      prompt_slug: prompt.prompt_slug,
      label: prompt.label,
      path: prompt.path,
      abspath: prompt.abspath,
      filename: prompt.filename,
      plan_slug: plan.slug,
      upload_status: 'pending',
      server_call_identity: null,
      uploaded_at: null,
      upload_error: null,
      export_status: 'pending',
      exported_at: null,
      export_error: null,
      prompt,
    })),
  };
}

function saveRunManifest(app, manifest) {
  const dir = workflowDir(app, 'runs');
  const archiveFile = path.join(dir, `${manifest.slug}.json`);
  const currentFile = path.join(dir, 'current-run.json');
  writeJson(archiveFile, manifest);
  writeJson(currentFile, manifest);
  return { archiveFile, currentFile };
}

module.exports = { buildRunManifest, saveRunManifest };
