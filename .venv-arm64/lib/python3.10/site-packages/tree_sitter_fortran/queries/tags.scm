(derived_type_statement
  (type_name) @name) @definition.class

(base_type_specifier
  (identifier) @name) @reference.class

(program_statement
  (name) @name) @definition.module

(module_statement
  (name) @name) @definition.module

(submodule_statement
  (module_name) (name) @name) @definition.module

(interface
 (function
   (function_statement
    (name) @name) @definition.interface))

(interface
 (subroutine
   (subroutine_statement
    (name) @name) @definition.interface))

(function_statement
  (name) @name) @definition.function

(subroutine_statement
  (name) @name) @definition.function

(module_procedure_statement
  (name) @name) @reference.implementation

(call_expression
  (identifier) @name) @reference.call

(subroutine_call
  (identifier) @name) @reference.call

(derived_type
   (type_name) @name) @reference.class
