local function trim(text)
  return (text or ""):gsub("^%s+", ""):gsub("%s+$", "")
end

local captured_inline_instruction = nil

local function has_class(classes, target)
  for _, class_name in ipairs(classes or {}) do
    if class_name == target then
      return true
    end
  end
  return false
end

function Div(el)
  local classes = el.classes or {}
  if has_class(classes, "inline_instruction") then
    captured_inline_instruction = trim(pandoc.utils.stringify(el.content))
    return {}
  end
end

function Pandoc(doc)
  if captured_inline_instruction ~= nil and captured_inline_instruction ~= "" then
    doc.meta.inline_instruction = pandoc.MetaString(captured_inline_instruction)
  end
  return doc
end
