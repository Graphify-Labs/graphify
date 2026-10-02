"""CUDA source normalization preserves line numbers and extracts kernels (#3911)."""
from pathlib import Path
import pytest

from graphify.extract import _normalize_cuda, _normalize_cpp_cli, extract_cpp

pytest.importorskip("tree_sitter_cpp")


def _labels(result: dict) -> list[str]:
    return [n["label"] for n in result.get("nodes", [])]


def _calls(result: dict) -> list[tuple[str, str]]:
    id_to_label = {n["id"]: n["label"] for n in result.get("nodes", [])}
    return [
        (id_to_label.get(e["source"], e["source"]), id_to_label.get(e["target"], e["target"]))
        for e in result.get("edges", [])
        if e.get("relation") == "calls"
    ]


def test_plain_cpp_is_not_rewritten():
    src = b"void foo() {}\nvoid bar() {\n    foo();\n}\n"
    assert _normalize_cuda(src) is None


def test_cuda_qualifiers_extracted_without_parse_errors_or_phantom_nodes(tmp_path):
    p = tmp_path / "qualifiers.cu"
    p.write_text(
        "__global__ void kernel() {}\n"
        "__device__ int helper() { return 1; }\n"
        "__host__ void host_helper() {}\n"
        "__forceinline__ void inline_helper() {}\n"
        "__constant__ int const_val = 42;\n"
        "__shared__ float s_mem[256];\n"
    )
    result = extract_cpp(p)
    assert result.get("parse_errors") is None
    labels = _labels(result)
    assert "kernel()" in labels
    assert "helper()" in labels
    assert "host_helper()" in labels
    assert "inline_helper()" in labels
    # Phantom type nodes must not be created for CUDA qualifiers
    for phantom in ("global", "__global__", "device", "__device__", "host", "__host__",
                    "forceinline", "__forceinline__", "constant", "__constant__", "shared", "__shared__"):
        assert phantom not in labels


def test_cuda_kernel_launch_recovers_call_and_preserves_location(tmp_path):
    p = tmp_path / "launch.cu"
    p.write_text(
        "__global__ void kernel(int x) {}\n"
        "void caller() {\n"
        "    kernel<<<1, 256>>>(42);\n"
        "}\n"
    )
    result = extract_cpp(p)
    assert result.get("parse_errors") is None
    labels = _labels(result)
    assert "kernel()" in labels
    assert "caller()" in labels
    calls = _calls(result)
    assert ("caller()", "kernel()") in calls

    # Verify caller and call source locations
    caller_node = next(n for n in result["nodes"] if n["label"] == "caller()")
    assert caller_node["source_location"] == "L2"
    call_edge = next(e for e in result["edges"] if e["relation"] == "calls")
    assert call_edge["source_location"] == "L3"


def test_cuda_full_execution_configuration(tmp_path):
    p = tmp_path / "full_launch.cu"
    p.write_text(
        "__global__ void kernel(int x, int y) {}\n"
        "void caller() {\n"
        "    kernel<<<grid, block, smem, stream>>>(10, 20);\n"
        "}\n"
    )
    result = extract_cpp(p)
    assert result.get("parse_errors") is None
    calls = _calls(result)
    assert ("caller()", "kernel()") in calls


def test_cuda_kernel_launch_inside_lambda(tmp_path):
    p = tmp_path / "lambda_launch.cu"
    p.write_text(
        "__global__ void kernel(int x) {}\n"
        "void wrapper() {\n"
        "    [&] {\n"
        "        kernel<<<blocks, threads>>>(x);\n"
        "    }();\n"
        "}\n"
    )
    result = extract_cpp(p)
    assert result.get("parse_errors") is None
    calls = _calls(result)
    assert ("wrapper()", "kernel()") in calls


def test_cuda_preprocessor_branches(tmp_path):
    p = tmp_path / "branches.cu"
    p.write_text(
        "#if __CUDA_ARCH__ >= 800\n"
        "__global__ void fast_kernel() {}\n"
        "#else\n"
        "__global__ void slow_kernel() {}\n"
        "#endif\n"
    )
    result = extract_cpp(p)
    assert result.get("parse_errors") is None
    labels = _labels(result)
    assert "fast_kernel()" in labels
    assert "slow_kernel()" in labels
    nodes = {n["label"]: n["source_location"] for n in result["nodes"]}
    assert nodes["fast_kernel()"] == "L2"
    assert nodes["slow_kernel()"] == "L4"


def test_cuda_normalization_location_preservation_and_crlf(tmp_path):
    # Construct a source containing comments, blank lines, CRLF, multiline launches, qualifiers
    src = (
        b"// Header comment\r\n"
        b"\r\n"
        b"#if __CUDA_ARCH__ >= 800\r\n"
        b"__global__ void fast_kernel(const float* in, float* out) {\r\n"
        b"    // thread index calculation\r\n"
        b"    int idx = blockIdx.x * blockDim.x + threadIdx.x;\r\n"
        b"}\r\n"
        b"#else\r\n"
        b"__global__ void slow_kernel(const float* in, float* out) {\r\n"
        b"    int idx = threadIdx.x;\r\n"
        b"}\r\n"
        b"#endif\r\n"
        b"\r\n"
        b"void host_caller() {\r\n"
        b"    fast_kernel<<<\r\n"
        b"        grid,\r\n"
        b"        block,\r\n"
        b"        0,\r\n"
        b"        stream\r\n"
        b"    >>>(nullptr, nullptr);\r\n"
        b"}\r\n"
    )
    norm = _normalize_cuda(src)
    assert norm is not None
    assert len(norm) == len(src)
    assert [i for i, b in enumerate(norm) if b == 0x0A] == [i for i, b in enumerate(src) if b == 0x0A]
    assert [i for i, b in enumerate(norm) if b == 0x0D] == [i for i, b in enumerate(src) if b == 0x0D]
    assert b"<<<" not in norm
    assert b">>>" not in norm
    assert b"__global__" not in norm

    p = tmp_path / "location.cu"
    p.write_bytes(src)
    result = extract_cpp(p)
    assert result.get("parse_errors") is None

    nodes = {n["label"]: n["source_location"] for n in result["nodes"]}
    assert nodes["fast_kernel()"] == "L4"
    assert nodes["slow_kernel()"] == "L9"
    assert nodes["host_caller()"] == "L14"

    calls = _calls(result)
    assert ("host_caller()", "fast_kernel()") in calls


def test_combined_cli_and_cuda_normalization():
    # A hypothetical source containing both C++/CLI keywords and CUDA constructs
    src = (
        b"[assembly:AssemblyVersion(\"1.0\")];\r\n"
        b"public ref struct CudaWrapper {\r\n"
        b"    void Launch() {\r\n"
        b"        kernel<<<1, 256>>>(0);\r\n"
        b"    }\r\n"
        b"};\r\n"
    )
    norm_cli = _normalize_cpp_cli(src)
    assert norm_cli is not None
    assert len(norm_cli) == len(src)

    norm_cuda = _normalize_cuda(norm_cli)
    assert norm_cuda is not None
    assert len(norm_cuda) == len(src)
    # Both transformations preserve byte length and newline positions
    assert [i for i, b in enumerate(norm_cuda) if b == 0x0A] == [i for i, b in enumerate(src) if b == 0x0A]
    assert [i for i, b in enumerate(norm_cuda) if b == 0x0D] == [i for i, b in enumerate(src) if b == 0x0D]
    assert b"ref struct" not in norm_cuda
    assert b"<<<" not in norm_cuda
