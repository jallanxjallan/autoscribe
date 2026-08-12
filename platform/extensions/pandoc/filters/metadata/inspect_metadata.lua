-- inspect_metadata.lua
function Meta(meta)
  local stringify = pandoc.utils.stringify
  local function describe(value)
    if type(value) == "table" and value.t then
      if value.t == "MetaInlines" or value.t == "MetaBlocks" then
        return stringify(value)
      elseif value.t == "MetaList" then
        local items = {}
        for _, item in ipairs(value) do
          table.insert(items, describe(item))
        end
        return "[" .. table.concat(items, ", ") .. "]"
      elseif value.t == "MetaMap" then
        local entries = {}
        for k, v in pairs(value) do
          entries[#entries + 1] = k .. ": " .. describe(v)
        end
        return "{" .. table.concat(entries, ", ") .. "}"
      elseif value.t == "MetaBool" then
        return tostring(value.c)
      elseif value.t == "MetaString" then
        return value.c
      else
        return "(" .. value.t .. ")"
      end
    elseif type(value) == "string" or type(value) == "number" or type(value) == "boolean" then
      return tostring(value)
    else
      return "(unknown type)"
    end
  end

  io.stderr:write("---- Metadata ----\n")
  for key, value in pairs(meta) do
    io.stderr:write(key .. ": " .. describe(value) .. "\n")
  end
  io.stderr:write("---- End Metadata ----\n")

  return meta
end
