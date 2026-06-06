const { spawnSync } = require("child_process");

function loadAscRegistries(options = {}) {
  const ascCommand = options.ascCommand || process.env.ASC_BIN || process.env._AUTOSCRIBE_ASC_BIN || "asc";
  const cwd = options.cwd || process.cwd();
  const env = options.env || process.env;

  const result = spawnSync(
    ascCommand,
    ["registries", "list", "--compact"],
    {
      cwd,
      env,
      encoding: "utf8",
      maxBuffer: 10 * 1024 * 1024,
    }
  );

  if (result.error) {
    throw result.error;
  }

  if (result.status !== 0) {
    const stderr = (result.stderr || "").trim();
    const stdout = (result.stdout || "").trim();

    throw new Error(
      [
        "asc registries list failed",
        `exit status: ${result.status}`,
        stderr ? `stderr: ${stderr}` : null,
        stdout ? `stdout: ${stdout}` : null,
      ]
        .filter(Boolean)
        .join("\n")
    );
  }

  try {
    return JSON.parse(result.stdout);
  } catch (error) {
    throw new Error(
      `Could not parse asc registries JSON: ${error.message}\n\n${result.stdout}`
    );
  }
}

function getEngineOptions(registries) {
  return Object.values(registries.registries.engines || {});
}

function getLocalScriptOptions(registries) {
  return Object.values(registries.registries.local_scripts || {});
}

function getRagProfileOptions(registries) {
  return Object.values(registries.registries.rag_profiles || {});
}

module.exports = {
  loadAscRegistries,
  getEngineOptions,
  getLocalScriptOptions,
  getRagProfileOptions,
};