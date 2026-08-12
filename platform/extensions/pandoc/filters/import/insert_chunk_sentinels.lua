-- insert_chunk_sentinels.lua
--
-- Insert chunk-start sentinel Divs before layout/vignette marker headings in
-- DOCX-derived Pandoc ASTs. Intended to run before a downstream Lua filter that
-- consumes the sentinels and emits one NDJSON record per chunk.
--
-- Usage:
--   pandoc input.docx \
--     --lua-filter=insert_chunk_sentinels.lua \
--     --lua-filter=emit_chunks.lua \
--     -t plain
--
-- Sentinel shape:
--
--   Div(Attr('', {'asc-sentinel'}, {
--     ['data-asc-sentinel'] = 'chunk-start',
--     ['data-asc-kind'] = 'layout-text' | 'vignette' | 'page-marker' | 'asset',
--     ['data-asc-page-start'] = '6',
--     ['data-asc-page-end'] = '7',
--     ['data-asc-title'] = 'Ujung Pandang',
--     ['data-asc-target-words'] = '500',
--     ['data-asc-heading'] = 'Pg 6-7 Ujung Pandang 500',
--     ['data-asc-source'] = 'slsitxt.docx'
--   }))

local SENTINEL_CLASS = 'asc-sentinel'
local SENTINEL_FLAG = 'chunk-start'

local function stringify_inlines(inlines)
  return pandoc.utils.stringify(inlines or {})
end

local function trim(s)
  return (s or ''):gsub('^%s+', ''):gsub('%s+$', '')
end

local function squeeze_space(s)
  s = (s or ''):gsub('_', ' ')
  s = s:gsub('%s+', ' ')
  return trim(s)
end

local function basename(path)
  if not path or path == '' then return '' end
  return path:match('([^/\\]+)$') or path
end

local function source_name()
  local input_files = PANDOC_STATE and PANDOC_STATE.input_files
  if input_files and #input_files > 0 then
    return basename(tostring(input_files[1]))
  end
  return ''
end

local function split_title_and_word_target(rest)
  rest = squeeze_space(rest)

  if rest == '' then
    return '', nil
  end

  local title, words = rest:match('^(.-)%s+(%d+)$')

  if title and title ~= '' then
    return squeeze_space(title), words
  end

  return rest, nil
end

local function parse_marker_heading(raw_heading)
  local heading = squeeze_space(raw_heading)
  local lower = heading:lower()

  -- Vignette Page 06
  local vig_page = lower:match('^vignette%s+page%s+(%d+)%s*$')

  if vig_page then
    return {
      kind = 'vignette',
      page_start = tostring(tonumber(vig_page)),
      page_end = tostring(tonumber(vig_page)),
      page_label = vig_page,
      title = 'Vignette Page ' .. vig_page,
      heading = heading,
    }
  end

  -- Page 4 / Page 5 layout placeholders.
  local page_only = lower:match('^page%s+(%d+)%s*$')

  if page_only then
    return {
      kind = 'page-marker',
      page_start = tostring(tonumber(page_only)),
      page_end = tostring(tonumber(page_only)),
      page_label = page_only,
      title = 'Page ' .. page_only,
      heading = heading,
    }
  end

  -- Pg 6-7 Ujung Pandang 500
  -- pg 14-15 Central Sulawesi 500
  local p1, p2, rest = lower:match('^pg%s+(%d+)%s*%-%s*(%d+)%s+(.+)$')

  if p1 then
    -- Re-match original normalized heading to preserve title case.
    local op1, op2, orest =
      heading:match('^[Pp][Gg]%s+(%d+)%s*%-%s*(%d+)%s+(.+)$')

    local title, words = split_title_and_word_target(orest or rest)

    local kind = 'layout-text'
    local title_lower = title:lower()

    if title_lower:match('photo') or title_lower:match('full%s+bleed') then
      kind = 'asset'
    end

    return {
      kind = kind,
      page_start = tostring(tonumber(op1 or p1)),
      page_end = tostring(tonumber(op2 or p2)),
      page_label = (op1 or p1) .. '-' .. (op2 or p2),
      title = title,
      target_words = words,
      heading = heading,
    }
  end

  -- Pg_3 INtro 250
  -- pg 13 toraja funeral 300
  -- Pg 12 Full Bleed photo
  local p, rest_single = lower:match('^pg%s+(%d+)%s+(.+)$')

  if p then
    local op, orest =
      heading:match('^[Pp][Gg]%s+(%d+)%s+(.+)$')

    local title, words = split_title_and_word_target(orest or rest_single)

    local kind = 'layout-text'
    local title_lower = title:lower()

    if title_lower:match('photo') or title_lower:match('full%s+bleed') then
      kind = 'asset'
    end

    return {
      kind = kind,
      page_start = tostring(tonumber(op or p)),
      page_end = tostring(tonumber(op or p)),
      page_label = op or p,
      title = title,
      target_words = words,
      heading = heading,
    }
  end

  return nil
end

local function sentinel_div(meta)
  local attrs = {
    ['data-asc-sentinel'] = SENTINEL_FLAG,
    ['data-asc-kind'] = meta.kind or '',
    ['data-asc-heading'] = meta.heading or '',
  }

  if meta.page_start then
    attrs['data-asc-page-start'] = meta.page_start
  end

  if meta.page_end then
    attrs['data-asc-page-end'] = meta.page_end
  end

  if meta.page_label then
    attrs['data-asc-page-label'] = meta.page_label
  end

  if meta.title and meta.title ~= '' then
    attrs['data-asc-title'] = meta.title
  end

  if meta.target_words then
    attrs['data-asc-target-words'] = meta.target_words
  end

  local src = source_name()

  if src ~= '' then
    attrs['data-asc-source'] = src
  end

  return pandoc.Div(
    {},
    pandoc.Attr('', { SENTINEL_CLASS }, attrs)
  )
end

local function is_candidate_header(block)
  -- These DOCX files import their layout markers as level-1 headers.
  -- Accept all Header levels anyway, because DOCX style mappings can vary.
  return block and block.t == 'Header'
end

function Pandoc(doc)
  local out = pandoc.List:new()

  for _, block in ipairs(doc.blocks) do
    if is_candidate_header(block) then
      local heading = stringify_inlines(block.content)
      local meta = parse_marker_heading(heading)

      if meta then
        out:insert(sentinel_div(meta))
      end
    end

    out:insert(block)
  end

  doc.blocks = out
  return doc
end