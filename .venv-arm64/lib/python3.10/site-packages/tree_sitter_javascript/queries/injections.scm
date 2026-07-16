; Parse the contents of tagged template literals using
; a language inferred from the tag.

(call_expression
  function: [
    (identifier) @injection.language
    (member_expression
      property: (property_identifier) @injection.language)
  ]
  arguments: (template_string (string_fragment) @injection.content)
  (#set! injection.combined)
  (#set! injection.include-children))


; Parse regex syntax within regex literals

((regex_pattern) @injection.content
 (#set! injection.language "regex"))

 ; Parse JSDoc annotations in comments

((comment) @injection.content
 (#set! injection.language "jsdoc"))

; Parse Ember/Glimmer/Handlebars/HTMLBars/etc. template literals
; e.g.: await render(hbs`<SomeComponent />`)
(call_expression
  function: ((identifier) @_name
             (#eq? @_name "hbs"))
  arguments: ((template_string) @glimmer
              (#offset! @glimmer 0 1 0 -1)))
