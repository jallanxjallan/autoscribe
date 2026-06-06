'use strict';

const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { execFileSync } = require('node:child_process');

function asArray(value) {
  if (value === undefined || value === null) return [];
  return Array.isArray(value) ? value : [value];
}

function defaultsArgs(defaults) {
  const values = asArray(defaults).filter(Boolean);

  if (values.length === 0) {
    throw new Error('runPandocUpload requires at least one defaults file');
  }

  return values.map((value) => `--defaults=${value}`);
}

function isPlainObject(value) {
  return (
    value !== null &&
    typeof value === 'object' &&
    !Array.isArray(value)
  );
}

function isScalarMetadataValue(value) {
  return (
    value === null ||
    typeof value === 'string' ||
    typeof value === 'number' ||
    typeof value === 'boolean'
  );
}

function isSafeMetadataKey(key) {
  return /^[A-Za-z0-9_.-]+$/.test(String(key || ''));
}

function scalarMetadataArg(key, value) {
  if (!isSafeMetadataKey(key)) {
    throw new Error(`metadata key is not safe for command-line metadata: ${key}`);
  }

  if (value === true) {
    return `--metadata=${key}`;
  }

  if (value === null) {
    return `--metadata=${key}:`;
  }

  return `--metadata=${key}:${String(value)}`;
}

function yamlScalar(value) {
  if (value === null) return 'null';
  if (typeof value === 'boolean') return value ? 'true' : 'false';
  if (typeof value === 'number') {
    return Number.isFinite(value) ? String(value) : JSON.stringify(String(value));
  }

  return JSON.stringify(String(value));
}

function yamlKey(key) {
  return /^[A-Za-z0-9_-]+$/.test(key) ? key : JSON.stringify(String(key));
}

function stripUndefinedObjectValues(value) {
  return Object.fromEntries(
    Object.entries(value).filter(([, item]) => item !== undefined)
  );
}

function toYaml(value, indent = 0) {
  const pad = ' '.repeat(indent);

  if (value === undefined) return '';

  if (value === null || typeof value !== 'object') {
    return yamlScalar(value);
  }

  if (Array.isArray(value)) {
    if (value.length === 0) return '[]';

    return value
      .filter((item) => item !== undefined)
      .map((item) => {
        if (item === null || typeof item !== 'object') {
          return `${pad}- ${yamlScalar(item)}`;
        }

        const nested = toYaml(item, indent + 2);
        return `${pad}-\n${nested}`;
      })
      .join('\n');
  }

  const cleanObject = stripUndefinedObjectValues(value);
  const entries = Object.entries(cleanObject);

  if (entries.length === 0) return '{}';

  return entries
    .map(([key, item]) => {
      if (item === null || typeof item !== 'object') {
        return `${pad}${yamlKey(key)}: ${yamlScalar(item)}`;
      }

      return `${pad}${yamlKey(key)}:\n${toYaml(item, indent + 2)}`;
    })
    .join('\n');
}

function writeMetadataFile({ dir, metadata }) {
  const filepath = path.join(dir, 'metadata.yaml');
  fs.writeFileSync(filepath, `---\n${toYaml(metadata)}\n`, 'utf8');
  return filepath;
}

function metadataCommandParts(metadata) {
  if (metadata === undefined || metadata === null) {
    return { args: [], tempDir: null };
  }

  if (!isPlainObject(metadata)) {
    throw new Error('metadata must be a plain object');
  }

  const entries = Object.entries(metadata).filter(([, value]) => value !== undefined);

  if (entries.length === 0) {
    return { args: [], tempDir: null };
  }

  if (entries.length === 1) {
    const [key, value] = entries[0];

    if (isSafeMetadataKey(key) && isScalarMetadataValue(value)) {
      return {
        args: [scalarMetadataArg(key, value)],
        tempDir: null,
      };
    }
  }

  const tempDir = fs.mkdtempSync(path.join(os.tmpdir(), 'pandoc-upload-'));
  const metadataFile = writeMetadataFile({ dir: tempDir, metadata: Object.fromEntries(entries) });

  return {
    args: [`--metadata-file=${metadataFile}`],
    tempDir,
  };
}

function runPandocUpload({ cwd = process.cwd(), input, defaults, metadata = {} }) {
  if (!input) {
    throw new Error('runPandocUpload requires input');
  }

  
  const metadataParts = metadataCommandParts(metadata);

  try {
    const args = [
      
      ...defaultsArgs(defaults),
      ...metadataParts.args,
      '--output=/dev/null',
      input,
    ];

    const pandocBin = process.env.OBSIDIAN_PANDOC_BIN;
    if (!pandocBin) {
      throw new Error('OBSIDIAN_PANDOC_BIN is not set');
    }

    execFileSync(pandocBin, args, {
      cwd,
      stdio: ['ignore', 'inherit', 'inherit'],
    });
  } finally {
    if (metadataParts.tempDir) {
      fs.rmSync(metadataParts.tempDir, { recursive: true, force: true });
    }
  }
}

module.exports = {
  runPandocUpload,
};
