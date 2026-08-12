local changed_files = nil

local function capture(cmd)
  local handle = io.popen(cmd, "r")
  if not handle then
    return ""
  end
  local output = handle:read("*a")
  handle:close()
  return output or ""
end

local function resolve_submission_commit(meta)
  if meta and meta["submission-commit"] then
    local requested = pandoc.utils.stringify(meta["submission-commit"]):gsub("%s+", "")
    if requested ~= "" then
      local verify = capture("git cat-file -t " .. requested)
      if verify:match("^commit") then
        io.stderr:write("Using submission commit: " .. requested .. "\n")
        return requested
      end
      io.stderr:write("submission-commit not found: " .. requested .. "\n")
    end
  end

  local auto = capture("git log --grep='Submission\\|^SUBMIT:' --pretty=format:'%H' -n 1")
  auto = auto:match("%S+")
  if auto then
    io.stderr:write("Auto-detected submission commit: " .. auto .. "\n")
    return auto
  end

  io.stderr:write("No submission commit found. Treating all files as changed.\n")
  return nil
end

local function get_changed_files(commit_hash)
  if not commit_hash then
    return nil
  end

  local diff_cmd = "git diff --name-only " .. commit_hash .. " HEAD"
  local output = capture(diff_cmd)

  local files = {}
  for line in output:gmatch("[^\r\n]+") do
    files[line] = true
  end
  return files
end

function Meta(meta)
  local commit_hash = resolve_submission_commit(meta)
  changed_files = get_changed_files(commit_hash)
  return meta
end

local function is_local_file(path)
  return path
    and path ~= ""
    and not path:match("^https?://")
    and not path:match("^mailto:")
end

local function is_file_modified(path)
  if changed_files == nil then
    return true
  end
  return changed_files[path] == true
end

function Para(el)
  local new_inlines = {}
  local has_links = false
  local has_modified_link = false

  for _, inline in ipairs(el.content) do
    if inline.t == "Link" then
      has_links = true
      local target = inline.target
      if is_local_file(target) and not is_file_modified(target) then
        -- Skip unchanged local file link
      else
        table.insert(new_inlines, inline)
        has_modified_link = true
      end
    else
      table.insert(new_inlines, inline)
    end
  end

  if has_links and not has_modified_link then
    return nil
  end
  return pandoc.Para(new_inlines)
end
