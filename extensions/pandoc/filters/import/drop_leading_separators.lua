-- drop_leading_separators.lua
--
-- Removes leading mechanical separator cruft before the first content block.
-- Intended to run after drop_instruction_preamble.lua. It removes only leading
-- HorizontalRule blocks and empty blocks; separators after content are kept.

local stringify = pandoc.utils.stringify

local function trim(text)
  text = tostring(text or "")
  text = text:gsub("\194\160", " ") -- NBSP
  text = text:gsub("^%s+", ""):gsub("%s+$", "")
  return text
end

local function is_empty_block(block)
  if block == nil then
    return true
  end
  if block.t == "Para" or block.t == "Plain" or block.t == "Header" then
    return trim(stringify(block)) == ""
  end
  if block.t == "Div" or block.t == "BlockQuote" then
    return trim(stringify(block)) == ""
  end
  return false
end

local function is_leading_cruft(block)
  return is_empty_block(block) or (block and block.t == "HorizontalRule")
end

function Pandoc(doc)
  local blocks = doc.blocks or pandoc.List:new()
  local first_content = 1

  while first_content <= #blocks and is_leading_cruft(blocks[first_content]) do
    first_content = first_content + 1
  end

  if first_content == 1 then
    return doc
  end

  local out = pandoc.List:new()
  for i = first_content, #blocks do
    out:insert(blocks[i])
  end

  doc.blocks = out
  return doc
end
