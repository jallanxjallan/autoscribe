local comment_id = 0

function RawInline(rb)
  local comment_text = rb.text:sub(5, -4) 
  print(comment_id)
  if comment_text then 
    print(comment_text)
    comment_id = comment_id + 1
    start = pandoc.Span(comment_text)
    start.attr = {class='comment-start', id=comment_id, author="Jeremy Allan", date=os.date(("%Y-%m-%dT%H:%M:%S"))}
    finish=pandoc.Span('')
    finish.attr = {class='comment-end', id=comment_id}
    new = {}
    table.insert(new, start)
    table.insert(new, pandoc.Str(comment_text))
    table.insert(new, finish)
    return new
  end
  return rb
end

