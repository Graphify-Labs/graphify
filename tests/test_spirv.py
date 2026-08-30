from __future__ import annotations

import struct
from pathlib import Path

import pytest

import graphify.extractors.spirv as spirv
from graphify.extractors.spirv import extract_spirv
from graphify.validate import validate_extraction


def _string(value: str) -> list[int]:
    raw = value.encode("utf-8") + b"\0"
    raw += b"\0" * (-len(raw) % 4)
    return [int.from_bytes(raw[i:i + 4], "little") for i in range(0, len(raw), 4)]


def _op(opcode: int, *operands: int) -> list[int]:
    return [((len(operands) + 1) << 16) | opcode, *operands]


def _module(*instructions: list[int], bound: int = 100, endian: str = "<",
            version: int = 0x00010600, schema: int = 0) -> bytes:
    words = [0x07230203, version, 0x12340001, bound, schema]
    for instruction in instructions:
        words.extend(instruction)
    return struct.pack(f"{endian}{len(words)}I", *words)


def _write(tmp_path: Path, data: bytes, name: str = "shader.spv") -> Path:
    path = tmp_path / name
    path.write_bytes(data)
    return path


def _by_label(result: dict, label: str) -> dict:
    return next(node for node in result["nodes"] if node["label"] == label)


def _shader(node: dict) -> dict:
    return node["metadata"]["shader"]


def test_reflects_entry_points_resources_layout_calls_and_debug(tmp_path: Path):
    data = _module(
        _op(17, 1),                                      # Shader capability
        _op(11, 40, *_string("GLSL.std.450")),
        _op(7, 41, *_string("source.hlsl")),
        _op(3, 5, 2021, 41),                           # HLSL source
        _op(14, 0, 1),                                 # Logical, GLSL450
        _op(15, 4, 30, *_string("main"), 20, 21),     # Fragment entry point
        _op(16, 30, 7),                                # OriginUpperLeft
        _op(5, 8, *_string("Globals")),
        _op(6, 8, 0, *_string("color")),
        _op(5, 22, *_string("globals")),
        _op(5, 20, *_string("position")),
        _op(5, 21, *_string("target")),
        _op(5, 31, *_string("helper")),
        _op(5, 50, *_string("QUALITY")),
        _op(73, 60),                                   # decoration group
        _op(71, 60, 34, 2),                            # DescriptorSet 2
        _op(74, 60, 22),
        _op(71, 22, 33, 3),                            # Binding 3
        _op(71, 8, 2),                                 # Block
        _op(72, 8, 0, 35, 16),                         # member Offset 16
        _op(71, 20, 30, 0),                            # Location 0
        _op(71, 21, 30, 1),                            # Location 1
        _op(71, 50, 1, 7),                             # SpecId 7
        _op(19, 1),                                    # void
        _op(22, 2, 32),                                # float32
        _op(23, 3, 2, 4),                              # float4
        _op(30, 8, 3),                                 # Globals { float4 }
        _op(32, 9, 2, 8),                              # Uniform pointer
        _op(32, 10, 1, 3),                             # Input pointer
        _op(32, 11, 3, 3),                             # Output pointer
        _op(21, 12, 32, 0),                            # uint32
        _op(50, 12, 50, 4),                            # specialization constant
        _op(33, 13, 1),                                # void ()
        _op(59, 9, 22, 2),                             # UBO variable
        _op(59, 10, 20, 1),                            # stage input
        _op(59, 11, 21, 3),                            # stage output
        _op(8, 41, 12, 4),                             # debug line
        _op(54, 1, 31, 0, 13), _op(56),               # helper
        _op(8, 41, 20, 2),
        _op(54, 1, 30, 0, 13),
        _op(57, 1, 70, 31),                            # main -> helper
        _op(56),
        bound=80,
    )
    result = extract_spirv(_write(tmp_path, data))

    assert "error" not in result
    assert validate_extraction(result) == []
    module = _by_label(result, "shader.spv")
    module_meta = _shader(module)["spirv"]
    assert module["source_location"] == "L1"
    assert module_meta["version"] == "1.6"
    assert module_meta["capability_names"] == ["Shader"]
    assert module_meta["source_language"]["name"] == "HLSL"
    assert module_meta["debug_source_file"] == "source.hlsl"

    globals_node = _by_label(result, "globals")
    globals_shader = _shader(globals_node)
    assert globals_shader["kind"] == "uniform_buffer"
    assert globals_shader["bindings"] == [{"descriptor_set": 2, "binding": 3}]
    assert globals_shader["access"] == "read"
    assert _shader(_by_label(result, "color"))["layout"]["offset"] == 16
    assert _shader(_by_label(result, "position"))["interface"]["location"] == 0
    assert _shader(_by_label(result, "target"))["interface"]["location"] == 1

    spec = _by_label(result, "QUALITY")
    assert _shader(spec)["spirv"]["spec_id"] == 7
    assert _shader(spec)["spirv"]["default_value"] == 4

    main = _by_label(result, "main")
    assert _shader(main)["kind"] == "entry_point"
    assert _shader(main)["stage"] == "fragment"
    assert _shader(main)["spirv"]["debug_file"] == "source.hlsl"
    helper = _by_label(result, "helper")
    assert any(edge["source"] == main["id"] and edge["target"] == helper["id"]
               and edge["relation"] == "calls" for edge in result["edges"])
    assert {edge["relation"] for edge in result["edges"] if edge["source"] == main["id"]} >= {
        "calls", "stage_input", "stage_output"
    }
    assert all(node["source_location"] == "L1" or node["source_location"].startswith("W")
               for node in result["nodes"])


def test_big_endian_and_local_size_id_are_reflected(tmp_path: Path):
    result = extract_spirv(_write(tmp_path, _module(
        _op(17, 1), _op(14, 0, 1),
        _op(15, 5, 20, *_string("main")),
        _op(331, 20, 38, 30, 31, 32),
        _op(19, 1), _op(21, 2, 32, 0),
        _op(43, 2, 30, 8), _op(43, 2, 31, 4), _op(43, 2, 32, 2),
        _op(33, 3, 1), _op(54, 1, 20, 0, 3), _op(56),
        bound=40, endian=">",
    )))

    assert "error" not in result
    assert _shader(_by_label(result, "shader.spv"))["spirv"]["byte_order"] == "big"
    assert _shader(_by_label(result, "main"))["thread_group_size"] == [8, 4, 2]


@pytest.mark.parametrize(
    ("qualifier", "expected"),
    [(0, "read"), (1, "write"), (2, "read_write")],
)
def test_image_access_qualifier_is_reflected(
    tmp_path: Path, qualifier: int, expected: str,
):
    result = extract_spirv(_write(tmp_path, _module(
        _op(5, 5, *_string("image")),
        _op(22, 1, 32),
        _op(25, 2, 1, 1, 0, 0, 0, 2, 0, qualifier),
        _op(32, 3, 0, 2),
        _op(59, 3, 5, 0),
        bound=6,
    )))
    image = _shader(_by_label(result, "image"))
    assert image["kind"] == "storage_image"
    assert image["access"] == expected
    assert image["spirv"]["access_qualifier"]["value"] == qualifier


@pytest.mark.parametrize("opcode", [4191, 65000])
def test_unknown_opcode_is_safe_partial_reflection(tmp_path: Path, opcode: int):
    result = extract_spirv(_write(tmp_path, _module(_op(opcode))))
    module = _by_label(result, "shader.spv")
    assert result["edges"] == []
    assert _shader(module)["spirv"]["unknown_opcodes"] == [opcode]
    assert _shader(module)["spirv"]["reflection_partial"] is True


def test_known_but_unhandled_reflection_opcode_is_partial(tmp_path: Path):
    result = extract_spirv(_write(tmp_path, _module(
        _op(21, 1, 32, 0), _op(43, 1, 2, 4),
        _op(5288, 3, 1, 2),  # OpTypeVectorIdEXT
        bound=4,
    )))
    metadata = _shader(_by_label(result, "shader.spv"))["spirv"]
    assert metadata["unknown_opcodes"] == []
    assert metadata["unhandled_opcodes"] == [5288]
    assert metadata["reflection_partial"] is True


@pytest.mark.parametrize(
    "data,error",
    [
        (b"", "header"),
        (b"not spirv" * 3, "aligned"),
        (struct.pack("<5I", 0, 0x00010600, 0, 1, 0), "magic"),
        (_module(schema=1), "schema"),
        (_module(version=0x00020600), "major"),
        (_module([0]), "zero instruction"),
        (_module([0x00020011]), "truncated"),
        (_module(_op(19, 5), bound=5), "outside bound"),
        (_module(_op(21, 1, 32, 0), _op(28, 2, 1, 99), bound=3), "array length"),
        (_module(_op(5, 1, 0x41414141), bound=2), "unterminated"),
    ],
)
def test_malformed_modules_return_no_partial_graph(tmp_path: Path, data: bytes, error: str):
    result = extract_spirv(_write(tmp_path, data))
    assert result["nodes"] == []
    assert result["edges"] == []
    assert error in result["error"]


def test_limits_and_suffix_are_enforced(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    path = _write(tmp_path, _module(_op(0)), "shader.bin")
    assert extract_spirv(path)["error"] == "not a .spv file"

    path = _write(tmp_path, _module(_op(0), _op(0)))
    monkeypatch.setattr(spirv, "_MAX_INSTRUCTIONS", 1)
    assert "instruction limit" in extract_spirv(path)["error"]

    monkeypatch.setattr(spirv, "_MAX_INSTRUCTIONS", 1_000_000)
    monkeypatch.setattr(spirv, "_MAX_BYTES", 8)
    assert "exceeds" in extract_spirv(path)["error"]


def test_decoration_group_expansion_is_bounded(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(spirv, "_MAX_ENTITIES", 5)
    result = extract_spirv(_write(tmp_path, _module(
        _op(19, 1), _op(19, 2), _op(19, 3),
        _op(73, 4), _op(71, 4, 0), _op(71, 4, 18),
        _op(74, 4, 1, 2, 3),
        bound=5,
    )))
    assert result["nodes"] == []
    assert "decoration limit" in result["error"]


def test_reflected_nodes_and_edges_are_bounded(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(spirv, "_MAX_ENTITIES", 3)
    result = extract_spirv(_write(tmp_path, _module(
        _op(5, 2, *_string("Big")), _op(21, 1, 32, 0),
        _op(30, 2, 1, 1, 1, 1),
        bound=3,
    )))
    assert result["nodes"] == []
    assert "entity limit" in result["error"]

    monkeypatch.setattr(spirv, "_MAX_ENTITIES", 100_000)
    monkeypatch.setattr(spirv, "_MAX_EDGES", 1)
    result = extract_spirv(_write(tmp_path, _module(
        _op(5, 1, *_string("A")), _op(5, 2, *_string("B")),
        _op(19, 1), _op(19, 2),
        bound=3,
    )))
    assert result["nodes"] == []
    assert "edge limit" in result["error"]


def test_type_nesting_and_recursion_fail_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(spirv, "_MAX_TYPE_DEPTH", 3)
    result = extract_spirv(_write(tmp_path, _module(
        _op(5, 1, *_string("Deep")),
        _op(21, 10, 32, 0), _op(43, 10, 9, 1),
        _op(28, 4, 10, 9), _op(28, 3, 4, 9),
        _op(28, 2, 3, 9), _op(28, 1, 2, 9),
        bound=11,
    )))
    assert result["nodes"] == []
    assert "type nesting limit" in result["error"]

    monkeypatch.setattr(spirv, "_emit", lambda *_args: (_ for _ in ()).throw(
        RecursionError("recursive metadata")
    ))
    result = extract_spirv(_write(tmp_path, _module()))
    assert result["nodes"] == []
    assert "recursive metadata" in result["error"]
