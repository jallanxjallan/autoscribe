const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const crypto = require("node:crypto");

function vaultKey(root) {
  const name = path.basename(root)
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "") || "vault";

  const digest = crypto
    .createHash("sha1")
    .update(root)
    .digest("hex")
    .slice(0, 8);

  return `${name}-${digest}`;
}

function manifestPath(root, mode) {
  return path.join(
    os.homedir(),
    ".local/share/autoscribe/obsidian/vaults",
    vaultKey(root),
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
    ...(targetDir ? { target_dir: targetDir.relative || targetDir } : {}),
    items: written.map(item => manifestItem(mode, item)),
  };

  fs.mkdirSync(path.dirname(outPath), { recursive: true });
  fs.writeFileSync(outPath, `${JSON.stringify(payload, null, 2)}\n`, "utf8");

  console.error(`${script}: saved ${mode} manifest: ${outPath}`);
}

module.exports = {
  vaultKey,
  manifestPath,
  writeWritingManifest,
};
