-- This Pandoc Lua filter converts file URLs (e.g., "file:///home/username/file.txt") 
-- to Linux system paths (e.g., "/home/username/file.txt") by stripping "file://" from URLs.

function Link(el)
  -- Check if the URL starts with "file://"
  if el.target:match("^file://") then
    -- Remove "file://" prefix to get the system path
    el.target = el.target:gsub("^file://", "")
  end
  return el
end

