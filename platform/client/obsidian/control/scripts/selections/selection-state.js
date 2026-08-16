const { notify: defaultNotify } = require("../lib/notify");
const { sanitizeForPath } = require("../lib/text");

function getBrowserSessionId(namespace) {
  const key = `${namespace}:browser-session`;
  try {
    let value = window.sessionStorage.getItem(key);
    if (!value) {
      value = `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`;
      window.sessionStorage.setItem(key, value);
    }
    return value;
  } catch (_) {
    return "no-session-storage";
  }
}

function getRuntimeSessionToken(namespace) {
  try {
    if (typeof process !== "undefined" && process?.pid) {
      return `pid-${process.pid}`;
    }
  } catch (_) {}

  return `browser-${getBrowserSessionId(namespace)}`;
}

function resolveTempRoot({ namespace, nodeRequire, tempRoot = "" }) {
  const fs = nodeRequire ? nodeRequire("fs") : null;
  const os = nodeRequire ? nodeRequire("os") : null;
  const pathMod = nodeRequire ? nodeRequire("path") : null;

  if (!fs || !os || !pathMod) {
    return { fs: null, pathMod: null, root: null };
  }

  const base = tempRoot || os.tmpdir();

  return {
    fs,
    pathMod,
    root: pathMod.join(base, `obsidian-${sanitizeForPath(namespace)}`)
  };
}

function createStateStore({
  namespace,
  vaultName,
  queryPath,
  nodeRequire,
  notify = defaultNotify,
  tempRoot = ""
}) {
  const sessionToken = getRuntimeSessionToken(namespace);
  const { fs, pathMod, root } = resolveTempRoot({ namespace, nodeRequire, tempRoot });

  const stateFile = fs && pathMod && root
    ? pathMod.join(
        root,
        `${sanitizeForPath(vaultName)}-${sanitizeForPath(queryPath)}-${sessionToken}.json`
      )
    : null;

  const fallbackStorageKey = `${namespace}:${vaultName}:${queryPath}:${sessionToken}`;

  async function read() {
    try {
      let text = "";

      if (stateFile) {
        try {
          text = await fs.promises.readFile(stateFile, "utf8");
        } catch (error) {
          if (error?.code === "ENOENT") return null;
          throw error;
        }
      } else {
        text = window.sessionStorage.getItem(fallbackStorageKey) || "";
      }

      if (!text.trim()) return null;
      return JSON.parse(text);
    } catch (error) {
      console.error(error);
      notify(`Could not read saved ${namespace} state.`);
      return null;
    }
  }

  async function write(state) {
    const text = JSON.stringify(state, null, 2);

    if (stateFile) {
      await fs.promises.mkdir(pathMod.dirname(stateFile), { recursive: true });
      await fs.promises.writeFile(stateFile, text, "utf8");
      return;
    }

    window.sessionStorage.setItem(fallbackStorageKey, text);
  }

  async function remove() {
    if (stateFile) {
      await fs.promises.rm(stateFile, { force: true });
      return;
    }

    window.sessionStorage.removeItem(fallbackStorageKey);
  }

  return {
    sessionToken,
    stateFile,
    tempRoot: root,
    fallbackStorageKey,
    read,
    write,
    remove
  };
}

module.exports = {
  createStateStore
};
