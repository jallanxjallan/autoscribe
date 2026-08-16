function encodeMacroArgs(text) {
  return encodeURIComponent(text);
}

function buildMacroArgs(selectedRows, field = "slug") {
  return selectedRows
    .map((row) => row[field])
    .filter(Boolean)
    .join("||");
}

function updateMacroHref(template, args) {
  if (!template || template === "#") return "#";
  return template.replace("__ARGS__", encodeMacroArgs(args));
}

module.exports = {
  encodeMacroArgs,
  buildMacroArgs,
  updateMacroHref
};