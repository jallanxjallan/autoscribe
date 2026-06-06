function Meta(meta)
  local input_file = nil
  local output_file = nil

  if PANDOC_STATE and PANDOC_STATE["input_files"] and #PANDOC_STATE["input_files"] > 0 then
    input_file = PANDOC_STATE["input_files"][1]
  end
  if PANDOC_STATE then
    output_file = PANDOC_STATE["output_file"]
  end

  if input_file and input_file ~= "" then
    meta["inputfile"] = pandoc.MetaString(input_file)
    if not meta["source"] then
      meta["source"] = pandoc.MetaString(input_file)
    end
  end

  if output_file and output_file ~= "" then
    meta["outputfile"] = pandoc.MetaString(output_file)
  end

  return meta
end
