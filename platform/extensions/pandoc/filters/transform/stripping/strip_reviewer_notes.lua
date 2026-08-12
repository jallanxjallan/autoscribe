-- strip_reviewer_notes.lua
--
-- Removes any text written as ==highlighted text== in the markdown source.
-- Assumes Pandoc is reading markdown with the `mark` extension enabled,
-- so ==...== becomes a Span with class "mark".

local function has_mark_class(el)
  return el.classes and el.classes:includes("mark")
end

function Span(el)
  if has_mark_class(el) then
    return {}
  end
  return nil
end

local function block_is_empty(block)
  return (block.t == "Para" or block.t == "Plain") and #block.content == 0
end

function Pandoc(doc)
  local cleaned = doc:walk({
    Span = Span
  })

  local blocks = {}
  for _, block in ipairs(cleaned.blocks) do
    if not block_is_empty(block) then
      table.insert(blocks, block)
    end
  end

  cleaned.blocks = blocks
  return cleaned
end