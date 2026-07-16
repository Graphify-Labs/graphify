(protocol_declaration
    declaration_kind: "protocol" @name
    .
    _ * @name
    .
    body: (protocol_body)
) @item

(class_declaration
    declaration_kind: (
        [
            "actor"
            "class"
            "extension"
            "enum"
            "struct"
        ]
    ) @name
    .
    _ * @name
    .
    body: (_)
) @item

(init_declaration
    name: "init" @name
    .
    _ * @name
    .
    body: (function_body)
) @item

(deinit_declaration
    "deinit" @name) @item

(function_declaration
    "func" @name
    .
    _ * @name
    .
    body: (function_body)
) @item

(class_body
    (property_declaration
        (value_binding_pattern) @name
        name: (pattern) @name
        (type_annotation)? @name
    ) @item
)

(enum_class_body
    (property_declaration
        (value_binding_pattern) @name
        name: (pattern) @name
        (type_annotation)? @name
    ) @item
)

(
    (protocol_function_declaration) @name
) @item

(
    (protocol_property_declaration) @name
) @item
