-- build_file_slug.lua
--
-- Create-only Pandoc Lua filter.
--
-- Required metadata:
--   slug_type: 3-letter prefix, e.g. "pss", "ins"
--
-- Optional metadata:
--   slug_seed
--   slug_seq
--   slug_identity_length
--   slug_schema.separator
--   source
--   input_record
--
-- Outputs:
--   meta.slug
--   meta.input_record.slug

local stringify = pandoc.utils.stringify

local DEFAULT_SEPARATOR = "."
local DEFAULT_IDENTITY_LENGTH = 8
local DEFAULT_HINT = "document"

local function trim(s)
  return (s or ""):gsub("^%s+", ""):gsub("%s+$", "")
end

local function is_meta_map(v)
  return type(v) == "table" and v.t == nil
end

local function as_string(v)
  if v == nil then
    return nil
  end
  if type(v) == "string" then
    v = trim(v)
    return v ~= "" and v or nil
  end
  local ok, s = pcall(stringify, v)
  if not ok then
    return nil
  end
  s = trim(s)
  return s ~= "" and s or nil
end

local function meta_get(map, key)
  if not is_meta_map(map) then
    return nil
  end
  return map[key]
end

local function meta_get_string(map, key)
  return as_string(meta_get(map, key))
end

local function meta_get_int(map, key)
  local s = meta_get_string(map, key)
  if not s then
    return nil
  end
  local n = tonumber(s)
  if not n or n % 1 ~= 0 then
    return nil
  end
  return n
end

local function ensure_meta_map(map, key)
  if not is_meta_map(map[key]) then
    map[key] = pandoc.MetaMap({})
  end
  return map[key]
end

local function slugify_stem(s)
  s = (s or ""):lower()
  s = s:gsub("[%s_]+", "-")
  s = s:gsub("[^a-z0-9%-]", "-")
  s = s:gsub("%-+", "-")
  s = s:gsub("^%-+", ""):gsub("%-+$", "")
  return s
end

local function normalize_seq(v)
  local s = as_string(v)
  if not s then
    return nil
  end

  if s:match("^%d+$") then
    local n = tonumber(s)
    if n and n >= 0 and n <= 999 then
      return string.format("%03d", n)
    end
  end

  error("slug_seq must be an integer 0..999 or a zero-padded 3-digit string")
end

local function validate_type(s)
  return s ~= nil and s:match("^[a-z][a-z][a-z]$") ~= nil
end

local function validate_hint(s)
  return s ~= nil and s:match("^[a-z0-9%-]+$") ~= nil
end

local function validate_identity(s, expected_len)
  return s ~= nil
    and #s == expected_len
    and s:match("^[a-z]+$") ~= nil
end

local function separator_from_meta(meta)
  local schema = meta.slug_schema
  return meta_get_string(schema, "separator") or DEFAULT_SEPARATOR
end

local function identity_length_from_meta(meta)
  local n =
    meta_get_int(meta, "slug_identity_length") or
    meta_get_int(meta.slug_schema, "identity_length")

  if not n then
    return DEFAULT_IDENTITY_LENGTH
  end
  if n < 1 then
    error("slug_identity_length must be >= 1")
  end
  return n
end

local function alpha_identity(seed, length)
  local hex = pandoc.sha1(seed)
  local out = {}

  for i = 1, #hex - 1, 2 do
    local pair = hex:sub(i, i + 1)
    local n = tonumber(pair, 16)
    out[#out + 1] = string.char(string.byte("a") + (n % 26))
    if #out >= length then
      break
    end
  end

  local id = table.concat(out)
  if #id < length then
    error("deterministic identity generation produced too few characters")
  end
  return id
end

local function basename_stem(s)
  if not s then
    return nil
  end

  local normalized = trim(s):gsub("\\", "/"):gsub("/+$", "")
  if normalized == "" then
    return nil
  end

  local leaf = normalized:match("([^/]+)$") or normalized
  if leaf == "" or leaf == "." or leaf == ".." then
    return nil
  end

  if normalized:find("/") or s:find("\\") then
    local stem = leaf:gsub("%.[^.]+$", "")
    return stem ~= "" and stem or leaf
  end

  if leaf:match("^.+%.[A-Za-z0-9][A-Za-z0-9._-]*$") then
    local stem = leaf:gsub("%.[^.]+$", "")
    return stem ~= "" and stem or leaf
  end

  return nil
end

local function key_bonus(key)
  if not key then
    return 0
  end

  local k = key:lower()

  if k:match("source") or k:match("path") or k:match("file") then
    return 30
  end

  if k:match("stem") or k:match("hint") or k:match("title") or k:match("name") then
    return 20
  end

  return 0
end

local function should_skip_key(key)
  if not key then
    return false
  end

  return key == "slug"
    or key == "slug_type"
    or key == "slug_seed"
    or key == "slug_seq"
    or key == "slug_identity_length"
    or key == "slug_schema"
end

local function maybe_update_best(best, key, raw)
  local s = as_string(raw)
  if not s then
    return best
  end

  local stem = basename_stem(s)
  local hint = nil
  local score = -1

  if stem then
    hint = slugify_stem(stem)
    score = 100 + key_bonus(key)
  elseif key and key_bonus(key) > 0 then
    hint = slugify_stem(s)
    score = 40 + key_bonus(key)
  end

  if not hint or hint == "" or not validate_hint(hint) then
    return best
  end

  if score > best.score then
    best.score = score
    best.hint = hint
  end

  return best
end

local function walk_for_hint(value, key, best)
  if value == nil then
    return best
  end

  local t = type(value)

  if t ~= "table" then
    return maybe_update_best(best, key, value)
  end

  if value.t == "MetaString"
    or value.t == "MetaInlines"
    or value.t == "MetaBlocks"
    or value.t == "MetaBool" then
    return maybe_update_best(best, key, value)
  end

  if value.t == "MetaList" or #value > 0 then
    for _, item in ipairs(value) do
      best = walk_for_hint(item, key, best)
    end
    return best
  end

  for child_key, item in pairs(value) do
    if not should_skip_key(child_key) then
      best = walk_for_hint(item, tostring(child_key), best)
    end
  end

  return best
end

local function build_hint(meta)
  local best = { score = -1, hint = nil }
  best = walk_for_hint(meta, nil, best)

  if best.hint then
    return best.hint
  end

  return DEFAULT_HINT
end

local function stable_repr(value)
  if value == nil then
    return "null"
  end

  local t = type(value)

  if t == "string" then
    return string.format("%q", value)
  end

  if t == "number" or t == "boolean" then
    return tostring(value)
  end

  if t ~= "table" then
    local s = as_string(value)
    return s and string.format("%q", s) or "null"
  end

  if value.t == "MetaString"
    or value.t == "MetaInlines"
    or value.t == "MetaBlocks"
    or value.t == "MetaBool" then
    local s = as_string(value)
    return s and string.format("%q", s) or "null"
  end

  if value.t == "MetaList" or #value > 0 then
    local parts = {}
    for _, item in ipairs(value) do
      parts[#parts + 1] = stable_repr(item)
    end
    return "[" .. table.concat(parts, ",") .. "]"
  end

  local keys = {}
  for key, _ in pairs(value) do
    keys[#keys + 1] = tostring(key)
  end
  table.sort(keys)

  local parts = {}
  for _, key in ipairs(keys) do
    parts[#parts + 1] = key .. "=" .. stable_repr(value[key])
  end

  return "{" .. table.concat(parts, ",") .. "}"
end

local function build_seed(meta, slug_type, hint, seq)
  local explicit = meta_get_string(meta, "slug_seed")
  if explicit then
    return explicit
  end

  local source = meta_get_string(meta, "source")
  if not source then
    source = "unknown"
  end

  return table.concat({
    slug_type,
    hint,
    source,
    seq or "",
    stable_repr(meta),
  }, "|")
end

function Meta(meta)
  local slug_type = meta_get_string(meta, "slug_type")
  if not slug_type then
    error("missing required metadata: slug_type")
  end
  slug_type = slug_type:lower()

  if not validate_type(slug_type) then
    error("slug_type must match [a-z][a-z][a-z]")
  end

  local hint = build_hint(meta)
  if not validate_hint(hint) then
    error("derived hint is invalid: " .. tostring(hint))
  end

  local seq = normalize_seq(meta.slug_seq)
  local sep = separator_from_meta(meta)
  local id_len = identity_length_from_meta(meta)
  local seed = build_seed(meta, slug_type, hint, seq)
  local identity = alpha_identity(seed, id_len)

  if not validate_identity(identity, id_len) then
    error("generated identity is invalid: " .. identity)
  end

  local slug = table.concat({ slug_type, hint, identity }, sep)
  if seq then
    slug = slug .. sep .. seq
  end

  meta.slug = pandoc.MetaString(slug)

  local input_record = ensure_meta_map(meta, "input_record")
  input_record.slug = pandoc.MetaString(slug)

  return meta
end