-- autoscribe_chunk_ndjson.lua
-- Pandoc Lua filter: DOCX/Markdown -> AutoScribe chunk NDJSON.
--
-- Usage:
--   AUTOSCRIBE_DOC_SLUG=prv.pasisir \
--   AUTOSCRIBE_JOB_SLUG=job.import.dummy \
--   AUTOSCRIBE_NDJSON_OUT=/tmp/pasisir.ndjson \
--   pandoc pasisir.doc.docx --lua-filter=autoscribe_chunk_ndjson.lua -t plain -o /dev/null
--
-- If AUTOSCRIBE_NDJSON_OUT is unset, NDJSON is written to stdout.

local stringify = pandoc.utils.stringify

local SCHEMA = "autoscribe.chunk.v0"
local DEFAULT_JOB_SLUG = os.getenv("AUTOSCRIBE_JOB_SLUG") or "job.import.dummy"
local INCLUDE_CHUNK_HEADING = (os.getenv("AUTOSCRIBE_INCLUDE_CHUNK_HEADING") or "1") ~= "0"

local function strip(s)
  s = tostring(s or "")
  s = s:gsub("\194\160", " ") -- NBSP
  return (s:gsub("^%s+", ""):gsub("%s+$", ""))
end

local function trim(s)
  return (strip(s):gsub("%s+", " "))
end

local function slugify(s)
  s = trim(s):lower()
  s = s:gsub("[‘’'`´]", "")
  s = s:gsub("&", " and ")
  s = s:gsub("[^%w]+", "-")
  s = s:gsub("^-+", ""):gsub("-+$", "")
  if s == "" then s = "untitled" end
  return s
end

local function stem_from_input()
  local fallback = "document"
  if not PANDOC_STATE or not PANDOC_STATE.input_files or not PANDOC_STATE.input_files[1] then
    return fallback
  end
  local name = PANDOC_STATE.input_files[1]:match("([^/\\]+)$") or fallback
  -- Handle double extensions such as pasisir.doc.docx.
  name = name:gsub("%.docx$", "")
  name = name:gsub("%.doc$", "")
  name = name:gsub("%.odt$", "")
  name = name:gsub("%.md$", "")
  return slugify(name)
end

local DOCUMENT_SLUG = os.getenv("AUTOSCRIBE_DOC_SLUG") or ("prv." .. stem_from_input())

local function header_text(block)
  if block.t ~= "Header" then return nil end
  return trim(stringify(block.content))
end

local function parse_page(raw)
  raw = trim(raw)
  local page = raw:match("doublespread%s*(%d+)") or raw:match("(%d+)%s*$")
  if page then return tonumber(page) end
  return nil
end

local function clean_title(raw)
  local s = trim(raw)
  s = s:gsub("Number range%s+doublespread%s*%d+", "")
  s = s:gsub("%s+%d+%s*$", "")
  return trim(s)
end

local function parse_vignette_header(raw)
  local normalized = trim(raw)
  local title = normalized:match("^VIGNETTE%s*: ?(.-)%s+ILLUSTRATION%s*: ?(.+)$")
  local illustration = normalized:match("^VIGNETTE%s*: ?.-%s+ILLUSTRATION%s*: ?(.+)$")
  if title then
    return trim(title), trim(illustration)
  end
  title = normalized:match("^VIGNETTE%s*: ?(.+)$") or "Vignette"
  return trim(title), nil
end

local function parse_boundary(raw, pending)
  local lower = raw:lower()

  -- A standalone production marker: it sets the type of the following chunk.
  if lower:match("^opener%s+%d+") then
    return {
      marker_only = true,
      pending_type = "opener",
      page = parse_page(raw),
      raw = raw,
    }
  end

  if lower:match("^vignette") then
    local title, illustration = parse_vignette_header(raw)
    return {
      starts_chunk = true,
      chunk_type = "vignette",
      title = title,
      illustration = illustration,
      page = parse_page(raw),
      raw = raw,
      production_kind = "vignette",
    }
  end

  if pending and pending.pending_type == "opener" then
    return {
      starts_chunk = true,
      chunk_type = "opener",
      title = clean_title(raw),
      page = parse_page(raw) or pending.page,
      raw = raw,
      production_kind = "opener",
      opener_marker = pending.raw,
    }
  end

  if lower:match("^itin%s*:") then
    local title = raw:gsub("^[Ii][Tt][Ii][Nn]%s*:%s*", "")
    return {
      starts_chunk = true,
      chunk_type = "main_text",
      title = clean_title(title),
      page = parse_page(raw),
      raw = raw,
      production_kind = "itinerary",
    }
  end

  if lower:match("^cont%s*:") then
    local title = raw:gsub("^[Cc][Oo][Nn][Tt]%s*:%s*", "")
    title = clean_title(title)
    if title == "" then title = "Continuation" end
    return {
      starts_chunk = true,
      chunk_type = "main_text",
      title = title,
      page = parse_page(raw),
      raw = raw,
      production_kind = "continuation",
    }
  end

  -- Untagged production heads in this format still carry the page-range marker.
  if lower:match("number range%s+doublespread") then
    return {
      starts_chunk = true,
      chunk_type = "main_text",
      title = clean_title(raw),
      page = parse_page(raw),
      raw = raw,
      production_kind = "main",
    }
  end

  -- Tail heads like "on to Surabaya 290" are short production heads, not body subheads.
  if lower:match("^on to .+%s+%d+$") then
    return {
      starts_chunk = true,
      chunk_type = "main_text",
      title = clean_title(raw),
      page = parse_page(raw),
      raw = raw,
      production_kind = "main",
    }
  end

  return { starts_chunk = false }
end

local function first_header_title(blocks)
  for _, b in ipairs(blocks) do
    if b.t == "Header" then return header_text(b) end
    if b.t == "Para" or b.t == "Plain" then return nil end
  end
  return nil
end

local function clone_blocks(blocks)
  local out = {}
  for _, b in ipairs(blocks) do out[#out + 1] = b end
  return out
end

local function markdown_for_chunk(chunk)
  local blocks = clone_blocks(chunk.blocks)
  if INCLUDE_CHUNK_HEADING and chunk.title and chunk.title ~= "" then
    local heading = pandoc.Header(2, pandoc.Inlines({ pandoc.Str(chunk.title) }))
    table.insert(blocks, 1, heading)
  end
  local md = pandoc.write(pandoc.Pandoc(blocks, pandoc.Meta({})), "gfm")
  return strip(md) .. "\n"
end

local function text_for_chunk(blocks)
  local parts = {}
  for _, b in ipairs(blocks) do
    local txt = trim(stringify(b))
    if txt ~= "" then parts[#parts + 1] = txt end
  end
  return table.concat(parts, "\n")
end

local function word_count(s)
  local n = 0
  for _ in tostring(s or ""):gmatch("%S+") do n = n + 1 end
  return n
end

local function dummy_steps_for(chunk_type)
  local steps
  if chunk_type == "opener" then
    steps = {
      {
        step_slug = "dummy.annotate.opener",
        handler = "local",
        registry_ref = "script.dummy.annotate_chunk",
        params = { annotation = "opener", purpose = "mark framing, thesis, and reader promise" },
      },
      {
        step_slug = "dummy.qa.opener",
        handler = "local",
        registry_ref = "script.dummy.qa_chunk",
        params = { checks = { "has_clear_frame", "sets_context", "flags_date_sensitive_claims" } },
      },
    }
  elseif chunk_type == "vignette" then
    steps = {
      {
        step_slug = "dummy.annotate.vignette",
        handler = "local",
        registry_ref = "script.dummy.annotate_chunk",
        params = { annotation = "vignette", purpose = "mark sidebar/capsule material and illustration cue" },
      },
      {
        step_slug = "dummy.qa.vignette",
        handler = "local",
        registry_ref = "script.dummy.qa_chunk",
        params = { checks = { "stands_alone", "has_asset_cue", "short_enough_for_sidebar" } },
      },
    }
  else
    steps = {
      {
        step_slug = "dummy.annotate.main_text",
        handler = "local",
        registry_ref = "script.dummy.annotate_chunk",
        params = { annotation = "main_text", purpose = "mark body-section structure and subheads" },
      },
      {
        step_slug = "dummy.qa.main_text",
        handler = "local",
        registry_ref = "script.dummy.qa_chunk",
        params = { checks = { "subheads_preserved", "sequence_intact", "fact_flags_only" } },
      },
    }
  end

  for i, step in ipairs(steps) do
    step.step_number = i
    step.step_count = #steps
  end
  return steps
end

local function finalise_chunk(chunk)
  if not chunk then return nil end
  if #chunk.blocks == 0 then return nil end

  if chunk.title == "Continuation" or chunk.title == "" or chunk.title == nil then
    local derived = first_header_title(chunk.blocks)
    if derived and derived ~= "" then chunk.title = derived end
  end

  chunk.text = text_for_chunk(chunk.blocks)
  chunk.content = markdown_for_chunk(chunk)
  chunk.word_count = word_count(chunk.text)
  return chunk
end

local function open_output()
  local path = os.getenv("AUTOSCRIBE_NDJSON_OUT")
  if path and path ~= "" then
    local fh, err = io.open(path, "w")
    if not fh then error("Could not open AUTOSCRIBE_NDJSON_OUT: " .. tostring(err)) end
    return fh, true
  end
  return io.stdout, false
end

local function emit_records(chunks)
  local out, close_when_done = open_output()
  local chunk_count = #chunks

  for idx, chunk in ipairs(chunks) do
    local chunk_no = idx
    local title_slug = slugify(chunk.title or chunk.chunk_type or "chunk")
    local chunk_slug = string.format("%s.%03d-%s", DOCUMENT_SLUG, chunk_no, title_slug)
    local steps = dummy_steps_for(chunk.chunk_type)

    for _, step in ipairs(steps) do
      step.document_slug = DOCUMENT_SLUG
      step.chunk_slug = chunk_slug
      step.chunk_number = chunk_no
      step.chunk_count = chunk_count
    end

    local record = {
      type = "document_chunk",
      schema = SCHEMA,
      job_slug = DEFAULT_JOB_SLUG,
      document_slug = DOCUMENT_SLUG,
      chunk_slug = chunk_slug,
      chunk_type = chunk.chunk_type,
      chunk_number = chunk_no,
      chunk_count = chunk_count,
      title = chunk.title,
      page = chunk.page,
      word_count = chunk.word_count,
      content = chunk.content,
      steps = steps,
      input_record = {
        origin = "pandoc-lua-filter",
        source_file = (PANDOC_STATE and PANDOC_STATE.input_files and PANDOC_STATE.input_files[1]) or nil,
        source_format = "pandoc-ast",
        production = {
          raw_header = chunk.raw_header,
          kind = chunk.production_kind,
          opener_marker = chunk.opener_marker,
          illustration = chunk.illustration,
        },
      },
    }

    out:write(pandoc.json.encode(record), "\n")
  end

  if close_when_done then out:close() end
  io.stderr:write(string.format("autoscribe_chunk_ndjson: emitted %d chunks from %s\n", chunk_count, DOCUMENT_SLUG))
end

function Pandoc(doc)
  local chunks = {}
  local current = nil
  local pending = nil

  local function push_current()
    local finished = finalise_chunk(current)
    if finished then chunks[#chunks + 1] = finished end
    current = nil
  end

  for _, block in ipairs(doc.blocks) do
    local htext = header_text(block)
    if htext then
      local boundary = parse_boundary(htext, pending)
      if boundary.marker_only then
        pending = boundary
      elseif boundary.starts_chunk then
        push_current()
        current = {
          chunk_type = boundary.chunk_type,
          title = boundary.title,
          page = boundary.page,
          raw_header = boundary.raw,
          production_kind = boundary.production_kind,
          opener_marker = boundary.opener_marker,
          illustration = boundary.illustration,
          blocks = {},
        }
        pending = nil
      else
        if not current then
          current = {
            chunk_type = "main_text",
            title = clean_title(htext),
            page = parse_page(htext),
            raw_header = htext,
            production_kind = "implicit",
            blocks = {},
          }
        else
          current.blocks[#current.blocks + 1] = block
        end
        pending = nil
      end
    else
      if not current then
        current = {
          chunk_type = "main_text",
          title = "Untitled",
          production_kind = "implicit",
          blocks = {},
        }
      end
      current.blocks[#current.blocks + 1] = block
    end
  end

  push_current()
  emit_records(chunks)

  -- Suppress normal Pandoc output; this filter emits NDJSON as its side effect.
  return pandoc.Pandoc({}, doc.meta)
end
