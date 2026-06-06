-- clipboard_copy.lua

local input_files = PANDOC_STATE.input_files or {}

function Pandoc(doc)
  local markdown = pandoc.write(doc, "markdown")

  -- Pipe markdown to the clipboard using xclip
  local pipe = io.popen("xclip -selection clipboard", "w")
  if not pipe then
    io.stderr:write("Failed to open pipe to xclip.\n")
    os.exit(1)
  end
  pipe:write(markdown)
  pipe:close()

  local names = #input_files > 0 and table.concat(input_files, ", ") or "stdin"
  print("Copied " .. names .. " to clipboard")
  os.exit()
end

