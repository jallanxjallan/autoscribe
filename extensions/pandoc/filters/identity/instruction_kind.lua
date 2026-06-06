-- instruction_kind.lua
-- Set meta.kind from meta.scope

local stringify = pandoc.utils.stringify

function Meta(meta)
  local scope_value = meta["scope"]
  if scope_value == nil then
    return meta
  end

  local kind = stringify(scope_value)
  if kind ~= "" then
    meta.kind = pandoc.MetaString(kind)
  end

  return meta
end