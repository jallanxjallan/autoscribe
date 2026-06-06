const { requireNodeModule } = require("./node");

function pad(n) {
  return String(n).padStart(2, "0");
}

function formatTimestamp(date = new Date()) {
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}`;
}

function formatFileStamp(date = new Date()) {
  return `${date.getFullYear()}${pad(date.getMonth() + 1)}${pad(date.getDate())}-${pad(date.getHours())}${pad(date.getMinutes())}${pad(date.getSeconds())}`;
}

function safeStemPart(text, fallback = "manifest") {
  return String(text || fallback)
    .trim()
    .replace(/[^A-Za-z0-9_.-]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 80) || fallback;
}

function ensureDirSync(dirpath) {
  const fs = requireNodeModule("fs");
  fs.mkdirSync(dirpath, { recursive: true });
}



function allocateManifestPath({ dirpath, stem }) {
  const fs = requireNodeModule("fs");
  const path = requireNodeModule("path");

  let currentStem = stem;
  let filepath = path.join(dirpath, `${currentStem}.json`);

  if (!fs.existsSync(filepath)) {
    return { stem: currentStem, filepath };
  }

  let n = 2;

  while (true) {
    currentStem = `${stem}-${n}`;
    filepath = path.join(dirpath, `${currentStem}.json`);

    if (!fs.existsSync(filepath)) {
      return { stem: currentStem, filepath };
    }

    n += 1;
  }
}



module.exports = {
  pad,
  formatTimestamp,
  formatFileStamp,
  safeStemPart,
  ensureDirSync,
  allocateManifestPath,
};