[
  (block)
  (switch_expression)
  (initializer_list)
] @indent.begin

(block
  "}" @indent.end)

[
  "("
  ")"
  "["
  "]"
  "{"
  "}"
] @indent.branch

[
  (comment)
  (multiline_string)
] @indent.ignore
