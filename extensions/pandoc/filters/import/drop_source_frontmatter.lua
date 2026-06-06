-- drop_source_frontmatter.lua
--
-- Drop source-document metadata while retaining AutoScribe operational metadata.
--
-- Pandoc merges source YAML frontmatter, defaults-file metadata, metadata-file
-- values, and command-line --metadata values into one doc.meta object before Lua
-- filters run. Lua cannot recover where a metadata key came from.
--
-- This filter therefore uses an explicit namespace policy:
--
--   keep only metadata supplied under the reserved AutoScribe namespace,
--   then unwrap it into ordinary metadata keys for later filters/emitters.
--
-- Supported input forms:
--
--   --metadata=asc_type:prompt
--   --metadata=asc_slug:prv.example.001
--   --metadata=asc_job_slug:job.normalize-import.001
--
-- or in a defaults/metadata file:
--
--   metadata:
--     asc:
--       type: prompt
--       slug: prv.example.001
--       job_slug: job.normalize-import.001
--
-- Output metadata:
--
--   type: prompt
--   slug: prv.example.001
--   job_slug: job.normalize-import.001
--
-- Everything else is discarded, including original source/frontmatter metadata.
--
-- Run this before identity/import filters that deliberately add new metadata.

local ASC_PREFIX = "asc_"
local ASC_HYPHEN_PREFIX = "asc-"

local function starts_with(text, prefix)
  return text:sub(1, #prefix) == prefix
end

local function strip_prefix(text, prefix)
  return text:sub(#prefix + 1)
end

local function normalize_key(key)
  -- Metadata passed as --metadata=asc-job-slug:... is accepted as a courtesy,
  -- but the canonical form is asc_job_slug. After the namespace is removed,
  -- hyphens become underscores so downstream Python models see normal keys.
  return tostring(key or ""):gsub("-", "_")
end

local function is_meta_map(value)
  local value_type = pandoc.utils.type and pandoc.utils.type(value) or type(value)
  return value_type == "MetaMap" or (type(value) == "table" and value.t == nil)
end

local function copy_namespaced_map(cleaned, value)
  if value == nil or not is_meta_map(value) then
    return
  end

  for key, item in pairs(value) do
    local out_key = normalize_key(key)
    if out_key ~= "" then
      cleaned[out_key] = item
    end
  end
end

function Pandoc(doc)
  local cleaned = pandoc.Meta({})

  for key, value in pairs(doc.meta or {}) do
    if key == "asc" then
      copy_namespaced_map(cleaned, value)
    elseif starts_with(key, ASC_PREFIX) then
      local out_key = normalize_key(strip_prefix(key, ASC_PREFIX))
      if out_key ~= "" then
        cleaned[out_key] = value
      end
    elseif starts_with(key, ASC_HYPHEN_PREFIX) then
      local out_key = normalize_key(strip_prefix(key, ASC_HYPHEN_PREFIX))
      if out_key ~= "" then
        cleaned[out_key] = value
      end
    end
  end

  doc.meta = cleaned
  return doc
end
