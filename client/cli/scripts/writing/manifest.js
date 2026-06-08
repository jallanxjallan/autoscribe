const fs = require("node:fs");
const path = require("node:path");
function vaultKey(root) {
  return path.basename(path.resolve(root))
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "") || "vault";
}

function localAutoscribeDir(root) {
  return path.join(path.resolve(root), ".autoscribe");
}

function manifestPath(root, mode) {
  return path.join(
    localAutoscribeDir(root),
    mode,
    `${mode}-results.json`
  );
}

function manifestItem(mode, item) {
  const base = {
    prompt_slug: item.promptSlug,
    call_identity: item.callIdentity,
    result_identity: item.resultIdentity,
    path: item.path,
    changed: Boolean(item.changed),
  };

  if (mode !== "writenew") {
    return base;
  }

  return {
    ...base,
    extraction_identity: item.extractionIdentity || item.callIdentity,
    extraction_identity_kind: item.extractionIdentityKind || "call_identity",
    filename_strategy: item.filenameStrategy || "",
    filename_stem: item.filenameStem || "",
    filename_hint: item.filenameHint || "",
    filename_hint_reason: item.filenameHintReason || "",
  };
}

function writeWritingManifest({ root, mode, targetDir, written, script }) {
  const outPath = manifestPath(root, mode);

  const payload = {
    kind: `${mode}-results`,
    timestamp: new Date().toISOString(),
    vault: root,
    vault_key: vaultKey(root),
    storage: "vault-local",
    ...(targetDir ? { target_dir: targetDir.relative || targetDir } : {}),
    items: written.map(item => manifestItem(mode, item)),
  };

  fs.mkdirSync(path.dirname(outPath), { recursive: true });
  fs.writeFileSync(outPath, `${JSON.stringify(payload, null, 2)}\n`, "utf8");

  console.error(`${script}: saved ${mode} manifest: ${outPath}`);
}

module.exports = {
  vaultKey,
  localAutoscribeDir,
  manifestPath,
  writeWritingManifest,
};
