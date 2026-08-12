-- meta_fill.lua — enrich metadata during render stage
-- Adds uid (timestamp + random digits) and slug (kebab of title or outdir) if missing.
-- Keeps provenance fields (source_relpath, sequence, etc.) passed from split phase.

local function ts_rand()
  math.randomseed(os.time() + tonumber(tostring(os.clock()):gsub('%D','')))
  return os.date('%Y%m%d%H%M%S') .. string.format('%03d', math.random(0,999))
end

local function kebab(s)
  s = tostring(s or "untitled"):lower()
  s = s:gsub("[^%w]+", "-"):gsub("^%-+", ""):gsub("%-+$", ""):gsub("%-+", "-")
  return s
end

return {
  Meta = function(m)
    if not m.uid then
      m.uid = pandoc.MetaString(ts_rand())
    end

    if not m.slug then
      local base = m.start_slug and pandoc.utils.stringify(m.start_slug)
        or (m.title and pandoc.utils.stringify(m.title))
        or (m.outdir and pandoc.utils.stringify(m.outdir))
        or "untitled"
      m.slug = pandoc.MetaString(kebab(base))
    end

    for _, key in ipairs {
      'source_relpath', 'sequence', 'split_level',
      'start_slug', 'start_title', 'outdir'
    } do
      local v = m[key]
      if v and type(v) ~= 'table' then
        m[key] = pandoc.MetaString(tostring(v))
      end
    end

    return m
  end
}
