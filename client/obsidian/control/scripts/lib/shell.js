const { spawnSync } = require("node:child_process");

function runCommandSync(command, args = [], options = {}) {
  const {
    cwd = process.cwd(),
    env = process.env,
    input = undefined,
    encoding = "utf8",
    allowFailure = false,
    check,
    maxBuffer,
  } = options || {};

  const result = spawnSync(command, args, {
    cwd,
    env,
    input,
    encoding,
    shell: false,
    maxBuffer,
  });

  const stdout = result.stdout || "";
  const stderr = result.stderr || "";
  const status = result.status ?? 0;

  const shouldCheck = check !== undefined ? check : !allowFailure;

  if (result.error && shouldCheck) {
    throw result.error;
  }

  if (shouldCheck && status !== 0) {
    const rendered = [command, ...args].join(" ");
    const message = stderr
      ? `Command failed (${status}): ${rendered}\n${stderr}`
      : `Command failed (${status}): ${rendered}`;

    const error = new Error(message);
    error.status = status;
    error.stdout = stdout;
    error.stderr = stderr;
    throw error;
  }

  return {
    status,
    stdout,
    stderr,
    error: result.error || null,
  };
}

function runTextSync(command, args = [], options = {}) {
  return runCommandSync(command, args, options).stdout;
}

module.exports = {
  runCommandSync,
  runTextSync,
};
