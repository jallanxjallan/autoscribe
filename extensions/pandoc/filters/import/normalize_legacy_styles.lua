-- normalize_legacy_styles.lua
--
-- Salvages common legacy Word styles when using from: docx+styles.
-- The goal is conservative structural cleanup, not perfect typography.

local function canonical(text)
  local s = tostring(text or ""):lower()
  s = s:gsub("[^%w]+", " ")
  s = s:gsub("^%s+", ""):gsub("%s+$", "")
  s = s:gsub("%s+", " ")
  return s
end

local function has_class(el, class)
  for _, c in ipairs(el.classes or {}) do
    if c == class then
      return true
    end
  end
  return false
end

local function add_class(el, class)
  if not has_class(el, class) then
    table.insert(el.classes, class)
  end
end

local function custom_style(el)
  if el and el.attributes then
    return el.attributes["custom-style"] or el.attributes["customstyle"] or ""
  end
  return ""
end

local function style_matches(key, patterns)
  for _, p in ipairs(patterns) do
    if key:match(p) then
      return true
    end
  end
  return false
end

local boxout_styles = {
  "boxout", "box out", "sidebar", "side bar", "case study", "feature box",
  "background", "explainer", "note box", "textbox", "text box"
}

local caption_styles = {
  "caption", "image caption", "figure caption", "photo caption", "picture caption"
}

local pullquote_styles = {
  "pull quote", "pullquote", "pull quotation", "display quote"
}

local verse_styles = {
  "verse", "poetry", "poem", "stanza"
}

local source_styles = {
  "source", "sources", "bibliography", "reference", "references", "credit", "credits"
}

function Div(el)
  local key = canonical(custom_style(el))
  if key == "" then
    return el
  end

  if style_matches(key, boxout_styles) then
    add_class(el, "boxout")
    el.attributes["data-custom-style"] = custom_style(el)
    el.attributes["custom-style"] = nil
    return el
  end

  if style_matches(key, caption_styles) then
    add_class(el, "caption")
    el.attributes["data-custom-style"] = custom_style(el)
    el.attributes["custom-style"] = nil
    return el
  end

  if style_matches(key, verse_styles) then
    add_class(el, "verse")
    el.attributes["data-custom-style"] = custom_style(el)
    el.attributes["custom-style"] = nil
    return el
  end

  if style_matches(key, source_styles) then
    add_class(el, "source")
    el.attributes["data-custom-style"] = custom_style(el)
    el.attributes["custom-style"] = nil
    return el
  end

  if style_matches(key, pullquote_styles) then
    return pandoc.BlockQuote(el.content)
  end

  return el
end

function Span(el)
  local key = canonical(custom_style(el))
  if key == "" then
    return el
  end

  if key:match("small caps") or key:match("smallcaps") then
    return pandoc.SmallCaps(el.content)
  end

  if key:match("strong") or key:match("bold") then
    return pandoc.Strong(el.content)
  end

  if key:match("emphasis") or key:match("italic") then
    return pandoc.Emph(el.content)
  end

  if key:match("superscript") or key:match("super script") then
    return pandoc.Superscript(el.content)
  end

  if key:match("subscript") or key:match("sub script") then
    return pandoc.Subscript(el.content)
  end

  if key:match("review") or key:match("comment") then
    add_class(el, "reviewer-note")
    el.attributes["data-custom-style"] = custom_style(el)
    el.attributes["custom-style"] = nil
    return el
  end

  return el
end
