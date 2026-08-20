"use strict";

function loadAnnotations() {
  const modulePath = require.resolve("./annotate.js");
  delete require.cache[modulePath];
  return require(modulePath);
}

module.exports = { loadAnnotations };
