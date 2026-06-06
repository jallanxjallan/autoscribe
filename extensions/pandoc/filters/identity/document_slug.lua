-- document_slug.lua
-- Validate frontmatter slug and normalize it to MetaString.

local stringify = pandoc.utils.stringify

function Meta(meta)
  local slug_value = meta.slug
  if slug_value == nil then
    error("document_slug: missing required frontmatter field 'slug'")
  end

  local slug = stringify(slug_value)
  if slug == nil or slug:match("^%s*$") then
    error("document_slug: frontmatter field 'slug' must be non-empty")
  end

  meta.slug = pandoc.MetaString(slug)
  return meta
end
