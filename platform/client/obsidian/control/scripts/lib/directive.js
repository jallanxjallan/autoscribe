"use strict";

function formatDirective(instruction) {
  const message = String(instruction || "").trim();
  if (!message) throw new Error("A directive instruction is required.");
  return `\`\`\`directive\n${message}\n\`\`\``;
}

module.exports = { formatDirective };
