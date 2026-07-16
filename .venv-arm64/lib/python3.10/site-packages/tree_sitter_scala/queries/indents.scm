; These indent queries adhere to nvim-tree-sytter syntax.
; See `nvim-tree-sitter-indentation-mod` vim help page.

[
  (template_body)
  (block)
  (parameters)
  (arguments)
  (match_expression)
  (splice_expression)
  (import_declaration)
  (function_definition)
  (ERROR ":")
  (ERROR "=")
  ("match")
  (":")
  ("=")
] @indent.begin

(arguments ")" @indent.end)

"}" @indent.end

"end" @indent.end

[
  ")"
  "]"
  "}"
] @indent.branch
