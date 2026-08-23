"use strict";

const annotations = require("./annotate.js");

function loadAnnotations() {
  return annotations;
}

module.exports = { loadAnnotations };
