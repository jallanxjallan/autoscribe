-- drop_instruction_preamble.lua
--
-- Drops leading instruction/prompt blocks before the first real article block.
-- This is intentionally leading-only: once real content starts, the filter
-- stops and leaves the rest of the document untouched.
--
-- It removes obvious AI/editorial directives such as:
--   Compare the...
--   Identify...
--   You are...
--   - Revise...
--   - Summarize...
--
-- Horizontal rules are not removed here. They are allowed while scanning so
-- that a later drop_leading_separators.lua pass can do the mechanical cleanup.

local stringify = pandoc.utils.stringify

local DIRECTIVE_STARTS = {
  "Compare",
  "Identify",
  "Revise",
  "Rewrite",
  "Summarize",
  "Summarise",
  "Analyze",
  "Analyse",
  "Update",
  "Edit",
  "Describe",
  "Explain",
  "List",
  "Note",
  "Review",
  "Ensure",
  "Make sure",
  "Check",
  "Consider",
  "Use",
  "Write",
  "Adapt",
  "Convert",
  "Translate",
  "Improve",
  "Correct",
}

local function trim(text)
  text = tostring(text or "")
  text = text:gsub("\194\160", " ") -- NBSP
  text = text:gsub("^%s+", ""):gsub("%s+$", "")
  return text
end

local function squeeze(text)
  return trim(tostring(text or ""):gsub("%s+", " "))
end

local function starts_with_directive(text)
  local s = squeeze(text)

  if s == "" then
    return false
  end

  if s:match("^You are%s") then
    return true
  end

  for _, verb in ipairs(DIRECTIVE_STARTS) do
    local escaped = verb:gsub("([^%w%s])", "%%%1")
    if s:match("^" .. escaped .. "%f[%A]") then
      return true
    end
  end

  -- Bullet/list items represented as text after parsing. Keep this broad but
  -- still directive-like: Capitalized verb followed by "the".
  if s:match("^[A-Z][a-z]+%s+the%s") then
    return true
  end

  if s:match("^[A-Z][a-z]+(ify|ize|ise|ate|ing)%f[%A]") then
    return true
  end

  return false
end

local function block_text(block)
  return squeeze(stringify(block))
end

local function is_empty_block(block)
  return block_text(block) == ""
end

local function is_separator(block)
  return block and block.t == "HorizontalRule"
end

local function is_directive_para(block)
  if not block or (block.t ~= "Para" and block.t ~= "Plain") then
    return false
  end
  return starts_with_directive(block_text(block))
end

local function item_text(item)
  return squeeze(stringify(item or {}))
end

local function list_item_is_directive(item)
  local text = item_text(item)
  if text == "" then
    return false
  end
  return starts_with_directive(text)
end

local function is_directive_list(block)
  if not block or (block.t ~= "BulletList" and block.t ~= "OrderedList") then
    return false
  end

  local items = block.content or block.c or {}
  local total = 0
  local directive = 0

  for _, item in ipairs(items) do
    local text = item_text(item)
    if text ~= "" then
      total = total + 1
      if list_item_is_directive(item) then
        directive = directive + 1
      end
    end
  end

  if total == 0 then
    return false
  end

  -- Drop only lists that are clearly preamble instructions. This avoids
  -- deleting an article that genuinely begins with a normal bullet list.
  return directive == total or (total <= 5 and directive >= 2 and directive / total >= 0.5)
end

local function is_directive_blockquote(block)
  if not block or block.t ~= "BlockQuote" then
    return false
  end
  return starts_with_directive(block_text(block))
end

local function is_instruction_block(block)
  return is_directive_para(block)
    or is_directive_list(block)
    or is_directive_blockquote(block)
end

function Pandoc(doc)
  local out = pandoc.List:new()
  local i = 1
  local blocks = doc.blocks or pandoc.List:new()

  while i <= #blocks do
    local block = blocks[i]

    if is_empty_block(block) then
      -- Pandoc usually removes blank lines already, but be defensive.
      i = i + 1
    elseif is_separator(block) then
      -- Keep separators for the dedicated cleanup filter, but keep scanning so
      -- separator-before-instruction-before-content still works.
      out:insert(block)
      i = i + 1
    elseif is_instruction_block(block) then
      i = i + 1
    else
      break
    end
  end

  for j = i, #blocks do
    out:insert(blocks[j])
  end

  doc.blocks = out
  return doc
end
