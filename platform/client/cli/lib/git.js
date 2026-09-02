'use strict';

const { runCommandSync } = require('./shell');

function git(args = [], options = {}) {
  return runCommandSync('/usr/bin/git', args, {
    cwd: options.cwd,
    input: options.input,
    check: options.check ?? true,
    maxBuffer: options.maxBuffer ?? 20 * 1024 * 1024,
  });
}

function gitText(args = [], options = {}) {
  return String(git(args, options).stdout || '').trim();
}

module.exports = { git, gitText };
