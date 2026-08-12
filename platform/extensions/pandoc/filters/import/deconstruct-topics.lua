-- deconstruct-topics.lua
--
-- Pandoc Lua filter for deconstructing topic files into finding notes.
--
-- Contract:
--   find Topics -name '*.md' -print0 |
--     xargs -0 -n1 pandoc -d deconstruct_topics -o Findings/_sink.md
--
-- The defaults file owns the Pandoc formats, data-dir, template name, and
-- deconstructor options. The output directory is the directory portion of the
-- outer Pandoc -o path unless deconstruct-output-dir is set in metadata.
--
-- Filesystem names are derived ONLY from the H1 heading text:
--   BCA IPO.md
--   BCA IPO 02.md
--
-- Pipeline identity is kept in frontmatter:
--   slug: fnd.<source-topic-slug>.<section-index>.<heading-slug>
--
-- The source topic filename is retained as metadata and as a safe tag. It is
-- not used as part of the output filename.

local path = pandoc.path

local stats = { written = 0, skipped = 0 }

local function fail(message)
  io.stderr:write("fatal: " .. message .. "\n")
  os.exit(1)
end

local function warn(message)
  io.stderr:write("warning: " .. message .. "\n")
end

local function meta_string(meta, key, fallback)
  local value = meta[key]
  if value == nil then return fallback or "" end
  return pandoc.utils.stringify(value)
end

local function required_meta(meta, key)
  local value = meta_string(meta, key, "")
  if value == "" then
    fail("missing required defaults metadata: " .. key)
  end
  return value
end

local function meta_bool(meta, key)
  local value = pandoc.text.lower(meta_string(meta, key, "false"))
  return value == "true" or value == "yes" or value == "1"
end

local function shell_quote(s)
  return "'" .. tostring(s):gsub("'", "'\\''") .. "'"
end

local function mkdir_p(dir)
  local ok = os.execute("mkdir -p " .. shell_quote(dir))
  if ok ~= true and ok ~= 0 then
    fail("could not create output directory: " .. dir)
  end
end

local function file_exists(file)
  local f = io.open(file, "r")
  if f then f:close(); return true end
  return false
end

local function write_text(file, text)
  local f = io.open(file, "w")
  if not f then fail("could not open output file: " .. file) end
  f:write(text)
  f:close()
end

local function strip_prefix(text, prefix)
  if prefix ~= "" and text:sub(1, #prefix) == prefix then
    return text:sub(#prefix + 1)
  end
  return text
end

local function slugify(text, fallback)
  local s = pandoc.text.lower(tostring(text or ""))
  s = s:gsub("[’']", "")
  s = s:gsub("[^a-z0-9]+", "-")
  s = s:gsub("^-+", ""):gsub("-+$", "")
  if s == "" then return fallback or "untitled" end
  return s
end

local function finding_slug(source_topic_slug, heading, index)
  local heading_slug = slugify(heading, string.format("finding-%03d", index))
  return string.format("fnd.%s.%03d.%s", source_topic_slug, index, heading_slug)
end

local function clean_filename_stem(text, fallback)
  local s = tostring(text or "")

  -- Keep the heading readable, but remove path separators and control chars.
  -- This deliberately does NOT slugify and does NOT add fnd/tpc prefixes.
  s = s:gsub("[\r\n\t]+", " ")
  s = s:gsub("[/\\]", "-")
  s = s:gsub(":", " -")
  s = s:gsub("[%c]", "")
  s = s:gsub("%s+", " ")
  s = s:gsub("^%s+", ""):gsub("%s+$", "")
  s = s:gsub("^%.", "_")

  if s == "" then return fallback or "Untitled" end
  return s
end

local function unique_output_file(out_dir, heading, index, used, overwrite)
  local base = clean_filename_stem(heading, string.format("Untitled %03d", index))
  local n = used[base] or 0

  while true do
    n = n + 1
    used[base] = n

    local output_stem = base
    if n > 1 then
      output_stem = string.format("%s %02d", base, n)
    end

    local output_file = path.normalize(path.join({ out_dir, output_stem .. ".md" }))

    if overwrite or not file_exists(output_file) then
      return output_file, output_stem
    end
  end
end

local function yaml_quote(value)
  local s = tostring(value or "")
  s = s:gsub("\\", "\\\\"):gsub('"', '\\"')
  return '"' .. s .. '"'
end

local function yaml_scalar(key, value)
  return key .. ": " .. yaml_quote(value) .. "\n"
end

local function yaml_number(key, value)
  return key .. ": " .. tostring(value) .. "\n"
end

local function yaml_tag(value)
  return "  - " .. yaml_quote(value) .. "\n"
end

local function today_iso()
  return os.date("%Y-%m-%d")
end

local function sha256(text)
  local ok, out = pcall(pandoc.pipe, "sha256sum", {}, text)
  if not ok then fail("sha256sum is not available on PATH") end
  return out:match("^([a-fA-F0-9]+)") or ""
end

local function demote_blocks(blocks, by)
  local out = {}
  for _, block in ipairs(blocks) do
    if block.t == "Header" then
      table.insert(out, pandoc.Header(block.level + by, block.content, block.attr))
    else
      table.insert(out, block)
    end
  end
  return out
end

local function is_substantive(blocks)
  for _, block in ipairs(blocks) do
    if block.t ~= "HorizontalRule" then return true end
  end
  return false
end

local function split_at_h1(blocks, include_preamble)
  local sections = {}
  local current_title = ""
  local current_blocks = {}

  local function flush()
    if not is_substantive(current_blocks) then
      current_title = ""
      current_blocks = {}
      return
    end

    if current_title ~= "" or include_preamble then
      table.insert(sections, {
        index = #sections + 1,
        title = current_title ~= "" and current_title or "Preamble",
        blocks = current_blocks,
      })
    end

    current_title = ""
    current_blocks = {}
  end

  for _, block in ipairs(blocks) do
    if block.t == "Header" and block.level == 1 then
      flush()
      current_title = pandoc.utils.stringify(block.content)
      if current_title == "" then current_title = "Untitled" end
      current_blocks = {}
    else
      table.insert(current_blocks, block)
    end
  end

  flush()

  if #sections == 0 and is_substantive(blocks) then
    fail("no level-1 headings found; H1 is the split contract")
  end

  return sections
end

local function first_input_file()
  if PANDOC_STATE and PANDOC_STATE.input_files and #PANDOC_STATE.input_files > 0 then
    return PANDOC_STATE.input_files[1]
  end
  return ""
end

local function output_dir(doc)
  local explicit = meta_string(doc.meta, "deconstruct-output-dir", "")
  if explicit ~= "" then return path.normalize(explicit) end

  if PANDOC_STATE and PANDOC_STATE.output_file and PANDOC_STATE.output_file ~= "" then
    return path.normalize(path.directory(PANDOC_STATE.output_file))
  end

  fail("no output filepath found; pass -o OUT/_sink.md or set deconstruct-output-dir")
end

local function user_data_dir()
  if PANDOC_STATE and PANDOC_STATE.user_data_dir and PANDOC_STATE.user_data_dir ~= "" then
    return PANDOC_STATE.user_data_dir
  end
  return ""
end

local function inner_pandoc_args(doc)
  local args = {}
  local data_dir = user_data_dir()
  if data_dir ~= "" then
    table.insert(args, "--data-dir")
    table.insert(args, data_dir)
  end

  table.insert(args, "--from")
  table.insert(args, required_meta(doc.meta, "deconstruct-from"))

  table.insert(args, "--to")
  table.insert(args, required_meta(doc.meta, "deconstruct-to"))

  table.insert(args, "--standalone")
  table.insert(args, "--template")
  table.insert(args, required_meta(doc.meta, "deconstruct-template"))

  table.insert(args, "--wrap")
  table.insert(args, meta_string(doc.meta, "deconstruct-wrap", "none"))

  return args
end

local function writer_format(doc)
  return required_meta(doc.meta, "deconstruct-to")
end

local function unescape_frontmatter(rendered)
  local head, fm, tail = rendered:match("^(%-%-%-\n)(.-)(\n%-%-%-\n.*)$")
  if not fm then return rendered end
  fm = fm:gsub("\\_", "_")
  return head .. fm .. tail
end

local function render_with_template(markdown, out_file, doc)
  local ok, rendered = pcall(pandoc.pipe, "pandoc", inner_pandoc_args(doc), markdown)
  if not ok then
    fail("inner pandoc failed for " .. out_file .. ": " .. tostring(rendered))
  end
  write_text(out_file, unescape_frontmatter(rendered))
end

local function section_input(metadata, body)
  local y = "---\n"
  y = y .. yaml_scalar("id", metadata.id)
  y = y .. yaml_scalar("slug", metadata.slug)
  y = y .. yaml_scalar("title", metadata.title)
  y = y .. yaml_scalar("kind", "finding")
  y = y .. yaml_scalar("topic", metadata.topic)
  y = y .. yaml_scalar("status", "imported")
  y = y .. yaml_scalar("verification_status", metadata.verification_status)
  y = y .. yaml_scalar("source_status", metadata.source_status)
  y = y .. yaml_scalar("source_topic_file", metadata.source_topic_file)
  y = y .. yaml_scalar("source_topic_title", metadata.source_topic_title)
  y = y .. yaml_scalar("source_topic_tag", metadata.source_topic_tag)
  y = y .. yaml_scalar("source_heading", metadata.source_heading)
  y = y .. yaml_number("source_index", metadata.source_index)
  y = y .. yaml_scalar("input_sha256", metadata.input_sha256)
  y = y .. yaml_scalar("last_pipeline_run", "")
  y = y .. yaml_scalar("updated", metadata.updated)
  y = y .. "tags:\n"
  y = y .. yaml_tag("finding")
  y = y .. yaml_tag("imported_topic")
  y = y .. yaml_tag(metadata.source_topic_tag)
  y = y .. "---\n\n"
  return y .. body .. "\n"
end

function Pandoc(doc)
  local source_path = meta_string(doc.meta, "deconstruct-source-path", first_input_file())
  if source_path == "" then fail("could not determine source path") end

  local out_dir = output_dir(doc)
  mkdir_p(out_dir)

  local finding_prefix = required_meta(doc.meta, "deconstruct-finding-prefix")
  local topic_prefix = required_meta(doc.meta, "deconstruct-topic-prefix")
  local overwrite = meta_bool(doc.meta, "deconstruct-overwrite")
  local include_preamble = meta_bool(doc.meta, "deconstruct-include-preamble")
  local sections = split_at_h1(doc.blocks, include_preamble)

  local source_stem = path.split_extension(path.filename(source_path))
  source_stem = strip_prefix(strip_prefix(source_stem, finding_prefix), topic_prefix)

  local source_topic_title = clean_filename_stem(source_stem, "Untitled Topic")
  local source_topic_slug = slugify(source_stem, "untitled-topic")
  local source_topic_tag = "topic/" .. source_topic_slug

  local inferred_topic = topic_prefix .. source_topic_slug
  local topic_id = meta_string(doc.meta, "id", "")
  if topic_id == "" then topic_id = meta_string(doc.meta, "topic", inferred_topic) end

  local used_output_stems = {}

  for _, section in ipairs(sections) do
    local out_file, output_stem = unique_output_file(
      out_dir,
      section.title,
      section.index,
      used_output_stems,
      overwrite
    )

    -- Human-readable filename stem doubles as note id. The machine slug below
    -- carries the fnd.* pipeline identity.
    local finding_id = output_stem

    local body_doc = pandoc.Pandoc(demote_blocks(section.blocks, 1), pandoc.Meta({}))
    local body = pandoc.write(body_doc, writer_format(doc), { wrap_text = "none" }):gsub("%s+$", "")
    local input_hash = sha256(body)

    local metadata = {
      id = finding_id,
      slug = finding_slug(source_topic_slug, section.title, section.index),
      title = section.title,
      topic = meta_string(doc.meta, "topic", topic_id),
      verification_status = meta_string(doc.meta, "verification_status", "pending"),
      source_status = meta_string(doc.meta, "source_status", "unchecked"),
      source_topic_file = source_path,
      source_topic_title = source_topic_title,
      source_topic_tag = source_topic_tag,
      source_heading = section.title,
      source_index = section.index,
      input_sha256 = input_hash,
      updated = today_iso(),
    }

    if file_exists(out_file) and not overwrite then
      warn("skip existing " .. out_file)
      stats.skipped = stats.skipped + 1
    else
      render_with_template(section_input(metadata, body), out_file, doc)
      io.stderr:write("wrote " .. out_file .. "\n")
      stats.written = stats.written + 1
    end
  end

  local summary = string.format(
    "deconstructed `%s`: written=%d skipped=%d sections=%d",
    source_path,
    stats.written,
    stats.skipped,
    #sections
  )

  return pandoc.Pandoc({ pandoc.Para({ pandoc.Str(summary) }) }, pandoc.Meta({}))
end
