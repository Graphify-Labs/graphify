"""Actual C++ statement ownership for source-only QtTest compatibility views.

This follows typed body/branch relationships rather than treating every callable
descendant as a statement. Runtime and feature branches remain source syntax;
neither their execution nor a test result is established here.
"""
from __future__ import annotations

_BODY = {"while_statement", "do_statement", "for_statement", "for_range_loop",
         "switch_statement", "try_statement", "catch_clause"}
_PREPROC = {"preproc_if", "preproc_ifdef", "preproc_elif", "preproc_else"}
_IMPLICIT = {"while_statement", "do_statement", "for_statement", "for_range_loop"}


def valid_statement_scope(statement):
    """Return the nearest lexical block only through a real callable-body path.

    An exact recovered declaration/expression may be a control substatement or
    preprocessor body, but parameters, initializers and conditions cannot borrow
    that role. Final Qt overlay admission still requires a clean complete source;
    the generic extractor keeps its existing marked partial-input contract.
    """
    if statement.type not in {"declaration", "expression_statement"} or statement.has_error:
        return None
    child, lexical = statement, None
    # Match the parser owner's established depth bound without introducing an
    # unbounded ancestor traversal for each macro in an untrusted source file.
    for _ in range(256):
        parent = child.parent
        if parent is None:
            return None
        kind = parent.type
        if kind == "compound_statement":
            lexical = lexical if lexical is not None else parent
        elif kind in {"function_definition", "lambda_expression"}:
            return lexical if parent.child_by_field_name("body") == child else None
        elif kind == "if_statement":
            if child not in (parent.child_by_field_name("consequence"), parent.child_by_field_name("alternative")):
                return None
        elif kind == "else_clause":
            if parent.named_children != [child]:
                return None
        elif kind in _BODY:
            if parent.child_by_field_name("body") != child and not (
                    kind == "try_statement" and child.type == "catch_clause"):
                return None
        elif kind in {"case_statement", "labeled_statement"}:
            # The parser owns label syntax. Inspect its typed heading fields,
            # avoiding a sibling-list scan per macro in a large switch case.
            heading = parent.child_by_field_name("value") or parent.child_by_field_name("label")
            if heading is not None and child.start_byte < heading.end_byte:
                return None
        elif kind in _PREPROC:
            alternative = parent.child_by_field_name("alternative")
            if child == alternative:
                if child.type not in _PREPROC:
                    return None
            elif any(parent.child_by_field_name(field) == child for field in ("condition", "name", "value")):
                return None
        else:
            return None
        child = parent
    return None


def implicit_data_scope(statement):
    """An unbraced declaration's implicit lifetime ends at its original semicolon.

    The equal-byte inert view creates no declaration, type or braces. Blocks,
    preprocessor bodies and labels retain their real opaque declaration view.
    """
    if statement.type != "expression_statement" or valid_statement_scope(statement) is None:
        return None
    parent = statement.parent
    if parent.type == "if_statement" and parent.child_by_field_name("consequence") == statement:
        return statement
    if parent.type == "else_clause" and parent.named_children == [statement]:
        return statement
    if parent.type in _IMPLICIT and parent.child_by_field_name("body") == statement:
        return statement
    return None
