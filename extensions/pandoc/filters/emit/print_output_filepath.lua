local function meta_bool(meta, key)
  local value = meta[key]
  if value == nil then
    return false
  end
  local text = pandoc.utils.stringify(value):lower()
  return text == "true" or text == "1" or text == "yes" or text == "on"
end

local function render_output_path(doc, output_file)
  local output_format = "path"
  if doc.meta and doc.meta["output-path-format"] then
    output_format = pandoc.utils.stringify(doc.meta["output-path-format"]):lower()
  end

  if output_format == "fileurl" then
    local cwd = pandoc.system.get_working_directory()
    local abs_path = pandoc.path.join({ cwd, output_file })
    return "file://" .. abs_path
  end

  return output_file
end

local function copy_to_clipboard(text)
  local pipe = io.popen("xclip -selection clipboard", "w")
  if not pipe then
    io.stderr:write("Failed to open xclip clipboard pipe\n")
    return
  end
  pipe:write(text)
  pipe:close()
end

function Pandoc(doc)
  local output_file = nil
  if PANDOC_STATE then
    output_file = PANDOC_STATE["output_file"]
  end
  if not output_file or output_file == "" then
    return doc
  end

  local rendered = render_output_path(doc, output_file)
  print(rendered)

  if doc.meta and meta_bool(doc.meta, "copy-output-path") then
    copy_to_clipboard(rendered)
  end

  return doc
end
