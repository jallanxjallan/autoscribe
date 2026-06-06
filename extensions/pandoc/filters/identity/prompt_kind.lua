-- prompt_kind.lua
-- Set meta.kind from meta.class

local stringify = pandoc.utils.stringify

function Meta(meta)
  local class_value = meta["class"]
  if class_value == nil then
    return meta
  end

  local kind = stringify(class_value)
  if kind ~= "" then
    meta.kind = pandoc.MetaString(kind)
  end

  return meta
end