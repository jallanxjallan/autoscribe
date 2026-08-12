"use strict";

function element(tag, attrs = {}, text = null) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs)) {
    if (key === "style") node.setAttribute("style", value);
    else if (key.startsWith("on") && typeof value === "function") node.addEventListener(key.slice(2).toLowerCase(), value);
    else if (key in node) node[key] = value;
    else node.setAttribute(key, value);
  }
  if (text !== null) node.textContent = text;
  return node;
}

function lineDiff(leftText, rightText) {
  const left = String(leftText || "").split(/\r?\n/);
  const right = String(rightText || "").split(/\r?\n/);
  if (left.length * right.length > 250000) {
    return [
      ...left.map((text) => ({ left: text, right: "", kind: "removed" })),
      ...right.map((text) => ({ left: "", right: text, kind: "added" })),
    ];
  }
  const rows = Array.from({ length: left.length + 1 }, () => new Uint32Array(right.length + 1));
  for (let i = left.length - 1; i >= 0; i -= 1) {
    for (let j = right.length - 1; j >= 0; j -= 1) {
      rows[i][j] = left[i] === right[j] ? rows[i + 1][j + 1] + 1 : Math.max(rows[i + 1][j], rows[i][j + 1]);
    }
  }
  const output = [];
  let i = 0;
  let j = 0;
  while (i < left.length || j < right.length) {
    if (i < left.length && j < right.length && left[i] === right[j]) {
      output.push({ left: left[i], right: right[j], kind: "same" });
      i += 1; j += 1;
    } else if (j < right.length && (i === left.length || rows[i][j + 1] >= rows[i + 1][j])) {
      output.push({ left: "", right: right[j], kind: "added" });
      j += 1;
    } else {
      output.push({ left: left[i], right: "", kind: "removed" });
      i += 1;
    }
  }
  return output;
}

function renderDiff(parent, review, options = {}) {
  const leftTitle = options.leftTitle || `Source — ${review.source_path || "current file"}`;
  const rightTitle = options.rightTitle || "Response";
  const grid = element("div", { style: "display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:0.75em;align-items:start;" });
  const source = element("div");
  const response = element("div");
  source.appendChild(element("h3", { style: "margin:0 0 0.4em;" }, leftTitle));
  response.appendChild(element("h3", { style: "margin:0 0 0.4em;" }, rightTitle));
  const codeStyle = "font-family:var(--font-monospace);font-size:0.85em;white-space:pre-wrap;overflow-wrap:anywhere;border:1px solid var(--background-modifier-border);border-radius:6px;overflow:hidden;";
  const sourceCode = element("div", { style: codeStyle });
  const responseCode = element("div", { style: codeStyle });
  for (const row of lineDiff(review.source_body, review.response_body)) {
    const leftStyle = row.kind === "removed" ? "background:rgba(255,80,80,0.16);padding:0 0.5em;min-height:1.35em;" : row.kind === "added" ? "opacity:0.35;padding:0 0.5em;min-height:1.35em;" : "padding:0 0.5em;min-height:1.35em;";
    const rightStyle = row.kind === "added" ? "background:rgba(80,200,120,0.16);padding:0 0.5em;min-height:1.35em;" : row.kind === "removed" ? "opacity:0.35;padding:0 0.5em;min-height:1.35em;" : "padding:0 0.5em;min-height:1.35em;";
    sourceCode.appendChild(element("div", { style: leftStyle }, row.left || " "));
    responseCode.appendChild(element("div", { style: rightStyle }, row.right || " "));
  }
  source.appendChild(sourceCode); response.appendChild(responseCode); grid.append(source, response); parent.appendChild(grid);
  return grid;
}

module.exports = { element, lineDiff, renderDiff };
