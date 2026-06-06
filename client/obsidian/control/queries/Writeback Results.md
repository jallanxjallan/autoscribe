# Writeback Results

```dataviewjs
(() => {
  const fs = require("node:fs");
  const os = require("node:os");
  const path = require("node:path");
  const crypto = require("node:crypto");
  const { spawnSync } = require("node:child_process");

  function vaultRootFromObsidian(app) {
    const adapter = app?.vault?.adapter;

    if (adapter && typeof adapter.getBasePath === "function") {
      return adapter.getBasePath();
    }

    if (adapter && typeof adapter.basePath === "string") {
      return adapter.basePath;
    }

    throw new Error("Could not determine vault root from Obsidian adapter.");
  }

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

  function writebackManifestPath(root) {
    return path.join(
      os.homedir(),
      ".local/share/autoscribe/obsidian/vaults",
      vaultKey(root),
      "writeback",
      "writeback-results.json"
    );
  }

  function normalizeRelPath(relPath) {
    return String(relPath || "")
      .replace(/\\/g, "/")
      .replace(/^\.\//, "");
  }

  function gitStatus(root, relPath) {
    const gitBin = process.env.OBSIDIAN_GIT_BIN || process.env._OBSIDIAN_GIT_BIN || "git";
    const result = spawnSync(gitBin, ["status", "--porcelain", "--", relPath], {
      cwd: root,
      encoding: "utf8",
      shell: false,
    });

    if (result.error) {
      return {
        ok: false,
        status: "",
        message: result.error.message,
      };
    }

    if (result.status !== 0) {
      return {
        ok: false,
        status: "",
        message: String(result.stderr || result.stdout || "").trim() || `git exited ${result.status}`,
      };
    }

    return {
      ok: true,
      status: String(result.stdout || "").trim(),
      message: "",
    };
  }

  function shortIdentity(value) {
    const text = String(value || "");
    if (text.length <= 10) return text;
    return `${text.slice(0, 6)}…${text.slice(-4)}`;
  }

  function statusLabel(root, relPath) {
    const status = gitStatus(root, relPath);

    if (!status.ok) {
      return `git error: ${status.message}`;
    }

    if (!status.status) {
      return "clean";
    }

    return `dirty: ${status.status.slice(0, 2).trim() || "modified"}`;
  }

  try {
    const root = vaultRootFromObsidian(app);
    const manifestPath = writebackManifestPath(root);

    if (!fs.existsSync(manifestPath)) {
      dv.paragraph("No writeback manifest found for this vault.");
      dv.paragraph(`Expected: \`${manifestPath}\``);
      return;
    }

    const manifest = JSON.parse(fs.readFileSync(manifestPath, "utf8"));
    const items = Array.isArray(manifest.items) ? manifest.items : [];

    dv.paragraph(`Manifest: \`${manifestPath}\``);
    dv.paragraph(`Timestamp: ${manifest.timestamp || "unknown"}`);

    if (manifest.vault && manifest.vault !== root) {
      dv.paragraph("⚠️ Manifest vault does not match active vault.");
      dv.paragraph(`Manifest vault: \`${manifest.vault}\``);
      dv.paragraph(`Active vault: \`${root}\``);
    }

    if (items.length === 0) {
      dv.paragraph("No writeback items in the latest manifest.");
      return;
    }

    const rows = items.map(item => {
      const relPath = normalizeRelPath(item.path);
      const fileLink = dv.fileLink(relPath, false, relPath);

      return [
        item.changed ? "changed" : "unchanged",
        statusLabel(root, relPath),
        item.prompt_slug || "",
        fileLink,
        shortIdentity(item.call_identity),
        shortIdentity(item.result_identity),
      ];
    });

    dv.table(
      ["Writeback", "Git", "Slug", "File", "Call", "Result"],
      rows
    );
  } catch (error) {
    dv.paragraph(`Writeback Results query failed: ${error.message}`);
  }
})();
```