[
 (identifier)
 (module_name)
] @variable

(string_literal) @string
(number_literal) @number
(statement_label) @number
(statement_label_reference) @number
(boolean_literal) @boolean
(comment) @comment
(custom_directive) @custom_directive

[
 (derived_type)
 (derived_type_statement)
 (import_statement)
 (intrinsic_type)
 (type_name)
] @type

(intrinsic_type) @type.builtin

(base_type_specifier
  (identifier) @type)

[
 (module_statement)
 (submodule_statement)
] @module

[
 (abstract_specifier)
 (access_specifier)
 (block_label)
 (block_label_start_expression)
 (none)
 (procedure_attributes)
 (procedure_qualifier)
 (type_qualifier)
] @attribute

[
 "#define"
 "#elif"
 "#endif"
 "#if"
 "#ifdef"
 (base_type_specifier)
 (block_construct)
 (contains_statement)
 (default)
 (end_associate_statement)
 (end_block_construct_statement)
 (end_block_data_statement)
 (end_coarray_critical_statement)
 (end_coarray_team_statement)
 (end_do_loop_statement)
 (end_enum_statement)
 (end_enumeration_type_statement)
 (end_forall_statement)
 (end_function_statement)
 (end_if_statement)
 (end_interface_statement)
 (end_module_procedure_statement)
 (end_module_statement)
 (end_program_statement)
 (end_select_statement)
 (end_submodule_statement)
 (end_subroutine_statement)
 (end_type_statement)
 (end_where_statement)
 (enum_statement)
 (enumeration_type_statement)
 (enumerator_statement)
 (equivalence_statement)
 (function_statement)
 (implicit_statement)
 (interface_statement)
 (keyword_statement)
 (language_binding)
 (namelist_statement)
 (print_statement)
 (procedure_statement)
 (program_statement)
 (subroutine_statement)
] @keyword

(use_statement "use" @keyword)
(use_statement "intrinsic" @keyword)
(included_items "only" @keyword)
(allocate_statement "allocate" @keyword)
(deallocate_statement "deallocate" @keyword)
(subroutine_call "call" @keyword)
(do_statement "do" @keyword)
(while_statement "while" @keyword)
(if_statement ["if" "then"] @keyword)
(elseif_clause ["else" "if" "elseif"] @keyword)
(else_clause "else" @keyword)
(open_statement "open" @keyword)
(write_statement "write" @keyword)
(private_statement "private" @keyword)
(public_statement "public" @keyword)


(select_case_statement "select" @keyword "case" @keyword)
(select_type_statement "select" @keyword "type" @keyword)
(select_rank_statement "select" @keyword "rank" @keyword)
(case_statement "case" @keyword)
(type_statement "type" @keyword)
(rank_statement "rank" @keyword)


[
 "*"
 "+"
 "-"
 "/"
 "="
 "<"
 ">"
 "<="
 ">="
 "=="
 "/="
 ".and."
 ".or."
 ".lt."
 ".gt."
 ".ge."
 ".le."
 ".eq."
 ".eqv."
 ".neqv."
 ".ne."
] @operator

;; Brackets
[
 "("
 ")"
 "["
 "]"
 "<<<"
 ">>>"
] @punctuation.bracket

;; Delimiter
[
 "::"
 ","
 "%"
 ":"
] @punctuation.delimiter

"&" @punctuation.special

(parameters
  (identifier) @variable.parameter)

(program_statement
  (name) @variable)

(module_statement
  (name) @variable)

(submodule_statement
  (module_name) (name) @variable)

(function_statement
  (name) @function)

(subroutine_statement
  (name) @function)

(module_procedure_statement
  (name) @function)

(end_program_statement
  (name) @variable)

(end_module_statement
  (name) @variable)

(end_submodule_statement
  (name) @variable)

(end_function_statement
  (name) @function)

(end_subroutine_statement
  (name) @function)

(end_module_procedure_statement
  (name) @function)

(subroutine_call
  (identifier) @function)

(keyword_argument
  name: (identifier) @keyword)

(derived_type_member_expression
  (type_member) @property)
