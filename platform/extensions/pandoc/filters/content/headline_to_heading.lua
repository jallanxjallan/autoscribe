function Para(element)
    for _, inline in pairs(element.content) do
      if inline.t == 'Strong' then
        return pandoc.Header(1, inline.content)
      end
    end
end
