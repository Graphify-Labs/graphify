

; MARK: Structure

(function_declaration
  body: (_) @function.inside) @function.around

; TODO: Classes/structs/enums


; MARK: Tests

; Only matches prefix test. Other conventions
; might be nice to add!
(function_declaration
	name: (simple_identifier) @_name
	(#match? @_name "^test")
)

