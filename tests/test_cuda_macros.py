"""CUDA macro kernel recovery tests (#3911)."""
from pathlib import Path
import pytest

from graphify.extract import extract_cpp, _augment_cuda_macros

pytest.importorskip("tree_sitter_cpp")


def _labels(result: dict) -> list[str]:
    return [n["label"] for n in result.get("nodes", [])]


def _nodes_map(result: dict) -> dict[str, dict]:
    return {n["label"]: n for n in result.get("nodes", [])}


def test_basic_kernel_macro(tmp_path):
    p = tmp_path / "basic_macro.cu"
    p.write_text(
        "#define DEFINE_KERNEL(NAME) \\\n"
        "    __global__ void NAME() {}\n"
        "\n"
        "DEFINE_KERNEL(foo);\n"
        "DEFINE_KERNEL(bar);\n"
    )
    result = extract_cpp(p)
    labels = _labels(result)
    assert "foo()" in labels
    assert "bar()" in labels

    nodes = _nodes_map(result)
    assert nodes["foo()"]["source_location"] == "L4"
    assert nodes["bar()"]["source_location"] == "L5"

    # Verify contains edges from file node
    file_nid = next(n["id"] for n in result["nodes"] if n["label"] == "basic_macro.cu")
    foo_nid = nodes["foo()"]["id"]
    bar_nid = nodes["bar()"]["id"]
    contains_targets = {e["target"] for e in result["edges"] if e["source"] == file_nid and e["relation"] == "contains"}
    assert foo_nid in contains_targets
    assert bar_nid in contains_targets


def test_token_pasting(tmp_path):
    p = tmp_path / "token_pasting.cu"
    p.write_text(
        "#define BINARY_KERNEL(NAME) \\\n"
        "    __global__ void NAME##_kernel() {}\n"
        "\n"
        "BINARY_KERNEL(add);\n"
        "BINARY_KERNEL(sub);\n"
    )
    result = extract_cpp(p)
    labels = _labels(result)
    assert "add_kernel()" in labels
    assert "sub_kernel()" in labels

    nodes = _nodes_map(result)
    assert nodes["add_kernel()"]["source_location"] == "L4"
    assert nodes["sub_kernel()"]["source_location"] == "L5"


def test_typed_instantiation(tmp_path):
    p = tmp_path / "typed_instantiation.cu"
    p.write_text(
        "#define AFFINE_KERNEL(NAME, TYPE) \\\n"
        "    __global__ void NAME##_##TYPE() {}\n"
        "\n"
        "AFFINE_KERNEL(affine_forward, float);\n"
        "AFFINE_KERNEL(affine_forward, double);\n"
    )
    result = extract_cpp(p)
    labels = _labels(result)
    assert "affine_forward_float()" in labels
    assert "affine_forward_double()" in labels

    nodes = _nodes_map(result)
    assert nodes["affine_forward_float()"]["source_location"] == "L4"
    assert nodes["affine_forward_double()"]["source_location"] == "L5"
    assert nodes["affine_forward_float()"]["id"] != nodes["affine_forward_double()"]["id"]


def test_multiple_invocations_not_collapsed(tmp_path):
    p = tmp_path / "multi_inv.cu"
    p.write_text(
        "#define DISPATCH_OP(OP, DTYPE) \\\n"
        "    __global__ void OP##_##DTYPE##_kernel(float* a, float* b) {}\n"
        "\n"
        "DISPATCH_OP(add, f32);\n"
        "DISPATCH_OP(add, f64);\n"
        "DISPATCH_OP(sub, f32);\n"
        "DISPATCH_OP(sub, f64);\n"
        "DISPATCH_OP(mul, f32);\n"
    )
    result = extract_cpp(p)
    labels = _labels(result)
    expected = [
        "add_f32_kernel()",
        "add_f64_kernel()",
        "sub_f32_kernel()",
        "sub_f64_kernel()",
        "mul_f32_kernel()",
    ]
    for exp in expected:
        assert exp in labels

    # Confirm all 5 have unique node IDs
    nodes = _nodes_map(result)
    nids = {nodes[exp]["id"] for exp in expected}
    assert len(nids) == 5


def test_multiline_macro_definition(tmp_path):
    p = tmp_path / "multiline_def.cu"
    p.write_text(
        "#define COMPLEX_KERNEL(NAME, OP) \\\n"
        "    __global__ void \\\n"
        "    NAME##_kernel(float* a, float* b, float* out, int n) { \\\n"
        "        int idx = blockIdx.x * blockDim.x + threadIdx.x; \\\n"
        "        if (idx < n) { \\\n"
        "            out[idx] = OP(a[idx], b[idx]); \\\n"
        "        } \\\n"
        "    }\n"
        "\n"
        "COMPLEX_KERNEL(vector_add, add_op);\n"
    )
    result = extract_cpp(p)
    labels = _labels(result)
    assert "vector_add_kernel()" in labels
    nodes = _nodes_map(result)
    assert nodes["vector_add_kernel()"]["source_location"] == "L10"


def test_ordinary_macros_are_ignored(tmp_path):
    p = tmp_path / "ordinary_macros.cu"
    p.write_text(
        "#define LOG_VALUE(x) printf(\"%d\", x)\n"
        "#define MAX(a, b) ((a) > (b) ? (a) : (b))\n"
        "#define CUDA_CHECK(err) if (err != 0) return;\n"
        "\n"
        "void host_fn() {\n"
        "    LOG_VALUE(10);\n"
        "    int m = MAX(1, 2);\n"
        "    CUDA_CHECK(0);\n"
        "}\n"
    )
    result = extract_cpp(p)
    labels = _labels(result)
    assert "host_fn()" in labels
    # Ordinary macros must not be synthesized as functions
    assert "LOG_VALUE()" not in labels
    assert "MAX()" not in labels
    assert "CUDA_CHECK()" not in labels
    assert len(result["nodes"]) == 2  # file node + host_fn


def test_existing_normal_cuda_functions_coexist_without_duplicates(tmp_path):
    p = tmp_path / "coexist.cu"
    p.write_text(
        "__global__ void normal_kernel() {}\n"
        "\n"
        "#define DEFINE_KERNEL(NAME) \\\n"
        "    __global__ void NAME() {}\n"
        "\n"
        "DEFINE_KERNEL(generated_kernel);\n"
        "# Attempted duplicate invocation\n"
        "DEFINE_KERNEL(normal_kernel);\n"
    )
    result = extract_cpp(p)
    labels = _labels(result)
    assert "normal_kernel()" in labels
    assert "generated_kernel()" in labels

    # normal_kernel must only exist once (no duplicate nodes)
    normal_nodes = [n for n in result["nodes"] if n["label"] == "normal_kernel()"]
    assert len(normal_nodes) == 1
    # normal_kernel comes from AST extraction on L1
    assert normal_nodes[0]["source_location"] == "L1"

    gen_nodes = [n for n in result["nodes"] if n["label"] == "generated_kernel()"]
    assert len(gen_nodes) == 1
    assert gen_nodes[0]["source_location"] == "L6"


def test_invocation_source_locations(tmp_path):
    p = tmp_path / "invocation_locations.cu"
    p.write_text(
        "// line 1\n"
        "#define DEFINE_KERNEL(NAME) \\\n"
        "    __global__ void NAME() {}\n"
        "\n"
        "\n"
        "\n"
        "// several lines later on line 8\n"
        "DEFINE_KERNEL(late_kernel);\n"
    )
    result = extract_cpp(p)
    nodes = _nodes_map(result)
    assert "late_kernel()" in nodes
    # Source location must be L8 (invocation), not L2 or L3 (macro definition)
    assert nodes["late_kernel()"]["source_location"] == "L8"


def test_typed_macro_invocation_no_semicolons_no_parse_warning(tmp_path, capsys):
    p = tmp_path / "typed_no_semicolons.cu"
    p.write_text(
        "#define AFFINE_KERNEL(NAME, TYPE) \\\n"
        "    __global__ void NAME##_##TYPE() {}\n"
        "\n"
        "AFFINE_KERNEL(affine_forward, float)\n"
        "AFFINE_KERNEL(affine_forward, double)\n"
    )
    result = extract_cpp(p)
    assert result.get("parse_errors") is None
    labels = _labels(result)
    assert "affine_forward_float()" in labels
    assert "affine_forward_double()" in labels

    nodes = _nodes_map(result)
    assert nodes["affine_forward_float()"]["source_location"] == "L4"
    assert nodes["affine_forward_double()"]["source_location"] == "L5"

    from graphify.extract import extract
    extract([p], cache_root=tmp_path / "cache")
    captured = capsys.readouterr()
    assert "warning:" not in captured.err


def test_typed_macro_invocation_with_semicolons_no_parse_warning(tmp_path):
    p = tmp_path / "typed_semicolons.cu"
    p.write_text(
        "#define AFFINE_KERNEL(NAME, TYPE) \\\n"
        "    __global__ void NAME##_##TYPE() {}\n"
        "\n"
        "AFFINE_KERNEL(foo, float);\n"
        "AFFINE_KERNEL(bar, double);\n"
    )
    result = extract_cpp(p)
    assert result.get("parse_errors") is None
    labels = _labels(result)
    assert "foo_float()" in labels
    assert "bar_double()" in labels


def test_multiple_type_forms(tmp_path):
    p = tmp_path / "multi_types.cu"
    p.write_text(
        "#define DISPATCH_KERNEL(NAME, TYPE) \\\n"
        "    __global__ void NAME##_##TYPE() {}\n"
        "\n"
        "DISPATCH_KERNEL(op, float)\n"
        "DISPATCH_KERNEL(op, double)\n"
        "DISPATCH_KERNEL(op, int)\n"
        "DISPATCH_KERNEL(op, half)\n"
        "DISPATCH_KERNEL(op, bfloat16)\n"
    )
    result = extract_cpp(p)
    assert result.get("parse_errors") is None
    labels = _labels(result)
    assert "op_float()" in labels
    assert "op_double()" in labels
    assert "op_int()" in labels
    assert "op_half()" in labels
    assert "op_bfloat16()" in labels


def test_nested_macro_arguments(tmp_path):
    p = tmp_path / "nested_args.cu"
    p.write_text(
        "#define TRAIT_KERNEL(NAME, TRAIT) \\\n"
        "    __global__ void NAME##_kernel(TRAIT val) {}\n"
        "\n"
        "TRAIT_KERNEL(foo, typename_traits<float>::type)\n"
    )
    result = extract_cpp(p)
    assert result.get("parse_errors") is None
    labels = _labels(result)
    assert "foo_kernel()" in labels
    nodes = _nodes_map(result)
    assert nodes["foo_kernel()"]["source_location"] == "L4"


def test_non_cuda_macro_with_type_arg_ignored(tmp_path):
    p = tmp_path / "non_cuda_macro.cu"
    p.write_text(
        "#define LOG_VALUE(x) printf(x)\n"
        "\n"
        "LOG_VALUE(float)\n"
    )
    result = extract_cpp(p)
    labels = _labels(result)
    # Must not be synthesized as a CUDA kernel
    assert "LOG_VALUE()" not in labels
    assert "float()" not in labels
    assert len([n for n in result.get("nodes", []) if n["label"] != "non_cuda_macro.cu"]) == 0


def test_real_syntax_error_remains_visible(tmp_path, capsys):
    p = tmp_path / "broken.cu"
    p.write_text(
        "#define AFFINE_KERNEL(NAME, TYPE) \\\n"
        "    __global__ void NAME##_##TYPE() {}\n"
        "\n"
        "AFFINE_KERNEL(foo, float)\n"
        "\n"
        "void broken_function( {\n"
        "    int x = 1;\n"
        "}\n"
    )
    result = extract_cpp(p)
    # The kernel from the macro must still be recovered
    labels = _labels(result)
    assert "foo_float()" in labels

    # But the unrelated syntax error in broken_function must NOT be suppressed
    pe = result.get("parse_errors")
    assert pe is not None
    assert pe.get("first_error_line") == 6
    assert pe.get("multiline_error") is True

    from graphify.extract import extract
    extract([p], cache_root=tmp_path / "cache")
    captured = capsys.readouterr()
    assert "had syntax errors and may be partially extracted" in captured.err
    assert "first error at line 6" in captured.err


def test_mixed_normal_cuda_and_macro_kernels_no_warning(tmp_path):
    p = tmp_path / "mixed.cu"
    p.write_text(
        "__global__ void normal_kernel() {}\n"
        "\n"
        "#define AFFINE_KERNEL(NAME, TYPE) \\\n"
        "    __global__ void NAME##_##TYPE() {}\n"
        "\n"
        "AFFINE_KERNEL(foo, float)\n"
    )
    result = extract_cpp(p)
    assert result.get("parse_errors") is None
    labels = _labels(result)
    assert "normal_kernel()" in labels
    assert "foo_float()" in labels

    nodes = _nodes_map(result)
    assert nodes["normal_kernel()"]["source_location"] == "L1"
    assert nodes["foo_float()"]["source_location"] == "L6"


def test_crlf_preservation_and_normalization(tmp_path):
    from graphify.extract import _normalize_cuda
    src = (
        b"#define AFFINE_KERNEL(NAME, TYPE) \\\r\n"
        b"    __global__ void NAME##_##TYPE() {}\r\n"
        b"\r\n"
        b"AFFINE_KERNEL(affine_forward, float)\r\n"
        b"AFFINE_KERNEL(affine_forward, double)\r\n"
    )
    norm = _normalize_cuda(src)
    assert norm is not None
    assert len(norm) == len(src)
    assert [i for i, b in enumerate(norm) if b == 0x0A] == [i for i, b in enumerate(src) if b == 0x0A]
    assert [i for i, b in enumerate(norm) if b == 0x0D] == [i for i, b in enumerate(src) if b == 0x0D]

    p = tmp_path / "crlf.cu"
    p.write_bytes(src)
    result = extract_cpp(p)
    assert result.get("parse_errors") is None
    nodes = _nodes_map(result)
    assert "affine_forward_float()" in nodes
    assert "affine_forward_double()" in nodes
    assert nodes["affine_forward_float()"]["source_location"] == "L4"
    assert nodes["affine_forward_double()"]["source_location"] == "L5"


def test_multiline_block_commented_macro_ignored(tmp_path):
    p = tmp_path / "block_comment.cu"
    p.write_text(
        "#define AFFINE_KERNEL(NAME, TYPE) \\\n"
        "    __global__ void NAME##_##TYPE() {}\n"
        "\n"
        "/*\n"
        "AFFINE_KERNEL(commented, float)\n"
        "*/\n"
        "\n"
        "AFFINE_KERNEL(real, float)\n"
    )
    result = extract_cpp(p)
    labels = _labels(result)
    assert "real_float()" in labels
    assert "commented_float()" not in labels
    assert len([n for n in result["nodes"] if n["label"] != "block_comment.cu"]) == 1


def test_multiline_block_comment_with_text_ignored(tmp_path):
    p = tmp_path / "block_comment_text.cu"
    p.write_text(
        "#define AFFINE_KERNEL(NAME, TYPE) \\\n"
        "    __global__ void NAME##_##TYPE() {}\n"
        "\n"
        "/*\n"
        "    Some text\n"
        "    AFFINE_KERNEL(commented, float)\n"
        "    More text\n"
        "*/\n"
        "\n"
        "AFFINE_KERNEL(real, float)\n"
    )
    result = extract_cpp(p)
    labels = _labels(result)
    assert "real_float()" in labels
    assert "commented_float()" not in labels
    assert len([n for n in result["nodes"] if n["label"] != "block_comment_text.cu"]) == 1


def test_single_line_block_comment_ignored(tmp_path):
    p = tmp_path / "single_line_block.cu"
    p.write_text(
        "#define AFFINE_KERNEL(NAME, TYPE) \\\n"
        "    __global__ void NAME##_##TYPE() {}\n"
        "\n"
        "/* AFFINE_KERNEL(commented, float) */\n"
        "AFFINE_KERNEL(real, float)\n"
    )
    result = extract_cpp(p)
    labels = _labels(result)
    assert "real_float()" in labels
    assert "commented_float()" not in labels
    assert len([n for n in result["nodes"] if n["label"] != "single_line_block.cu"]) == 1
