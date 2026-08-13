local system = require("pandoc.system")

local file_has_changes = false
local git_diff_output = ""
local source_file = nil

-- Helper to extract plain string from meta field
local function stringify_meta(meta_value)
  if type(meta_value) == "string" then
    return meta_value
  elseif meta_value.t == "MetaString" then
    return meta_value.text
  elseif meta_value.t == "MetaInlines" then
    return pandoc.utils.stringify(meta_value)
  end
  return nil
end

function Meta(meta)
  source_file = PANDOC_STATE.input_files[1]
  
  if not source_file then
    io.stderr:write("Warning: No input file found. Skipping git check.\n")
    return nil
  end

  -- Run git diff
  local cmd = 'git diff HEAD -- ' .. pandoc.utils.stringify(source_file)
  local pipe = io.popen(cmd, 'r')
  local diff = pipe:read("*a")
  pipe:close()

  if diff and #diff > 0 then
    file_has_changes = true
    git_diff_output = diff
  end

  return nil
end

function Pandoc(doc)
  if file_has_changes then
    local changed_lines = {}

    for line in git_diff_output:gmatch("[^\r\n]+") do
      -- Include only changed content (additions or deletions)
      if line:match("^%+[^+]") or line:match("^%-[^%-]") then
        table.insert(changed_lines, line)
      end
    end

    if #changed_lines > 0 then
      table.insert(doc.blocks, pandoc.HorizontalRule())
      table.insert(doc.blocks, pandoc.Para{pandoc.Str("⚠ Uncommitted changes (raw diff):")})
      table.insert(doc.blocks, pandoc.CodeBlock(table.concat(changed_lines, "\n"), {class = "diff"}))
    end
  end
  return doc
end


