local pandoc = require 'pandoc'

-- =====================================================================
-- Helper 1: URL/Percent Decoder
-- Handles nil input and converts URL-encoded characters (like %20)
-- =====================================================================
local function url_decode(s)
  if not s or s == "" then
    return s
  end
  
  return s:gsub('%%(%x%x)', function(h)
    return string.char(tonumber(h, 16))
  end)
end

-- =====================================================================
-- Helper 2: Strip Metadata (Horizontal Rule Stripping REMOVED)
-- Now only strips the YAML front matter.
-- =====================================================================
local function strip_metadata(content)
  local body = content

  -- 1. Strip YAML front matter (--- ... ---)
  if body:match("^%s*%-%-%-") then
    body = body:gsub("^%s*%-%-%-[\r\n](.-)[\r\n]%-%-%-[\r\n]?", "", 1)
  end

  -- 2. Strip all content *after* the first horizontal rule (HR)
  -- <<< LOGIC COMMENTED OUT TO PRESERVE ALL BODY CONTENT >>>
  -- local hr_pattern = "[\r\n][ ]*([-_*])%s*%1%s*%1%s*[\r\n]"
  -- local start_index, end_index = body:find(hr_pattern)
  -- if start_index then
  --   body = body:sub(1, start_index - 1)
  -- end
  
  return body
end

-- =====================================================================
-- Helper 3: File Existence Check Placeholder (CRASH ON MISSING FILE)
-- Now removes the io.open failure check.
-- =====================================================================
-- The actual file existence check is no longer needed since you want
-- the script to crash on io.open failure inside load_markdown_file.

-- We keep a simple stub for the Para function's internal check
local function is_local_markdown(target_array)
  -- This function is now just a formality to proceed with loading.
  return true 
end

-- =====================================================================
-- Core Loader Function (CRASHES ON MISSING FILE)
-- =====================================================================
local function load_markdown_file(path)
  -- io.open will return nil and print an error if the file is missing.
  -- The following fh:read("*a") will then crash the script with "attempt to index a nil value"
  -- (which is the desired behavior for crashing).
  local fh = io.open(path, "r")
  
  -- !!! Removed the 'if not fh then return {}' check to force crash !!!

  local content = fh:read("*a")
  fh:close()
  
  content = strip_metadata(content)
  
  local doc = pandoc.read(content, "markdown")
  return doc.blocks
end


-- =====================================================================
-- Filter Function: Para (Paragraph) - Unchanged Logic
-- =====================================================================
function Para(para)
  local is_replacement_mode = false
  local target_links = {}

  -- PASS 1: Detect the special marker and collect all other target files
  for _, inline in ipairs(para.content) do
    if inline.t == "Link" then
      -- Check for the special marker link
      if #inline.content == 1
          and inline.content[1].t == "Str"
          and inline.content[1].text == "content_to_expand"
      then
        is_replacement_mode = true
      else
        target_links[#target_links + 1] = inline
      end
    end
  end

  if not is_replacement_mode then
    return nil
  end

  -- PASS 2: Load and combine content from all collected target files
  local out_blocks = {}
  
  for _, link_inline in ipairs(target_links) do
    local encoded_filepath = link_inline.target[1]
    local decoded_filepath = url_decode(encoded_filepath)

    -- Since you want the script to crash on missing files, we only check 
    -- that the path is not nil/empty before calling the loader.
    if decoded_filepath and decoded_filepath ~= "" then
      
      -- is_local_markdown is now only a formality check
      if is_local_markdown({decoded_filepath, link_inline.target[2]}) then

        -- load_markdown_file will crash if the file is not found
        local blocks = load_markdown_file(decoded_filepath)
        
        for _, b in ipairs(blocks) do
          table.insert(out_blocks, b)
        end
      end
    end
  end

  if #out_blocks > 0 then
    return out_blocks
  else
    return {}
  end
end
