"""Bounded, dependency-free structural reflection for binary SPIR-V modules."""
from __future__ import annotations

from collections import Counter, defaultdict
from pathlib import Path
import stat
import struct

from graphify.extractors.base import _file_stem, _make_id
from graphify.security import sanitize_label, sanitize_metadata


_MAGIC = 0x07230203
_MAX_BYTES = 50 * 1024 * 1024
_MAX_INSTRUCTIONS = 1_000_000
_MAX_ENTITIES = 100_000
_MAX_EDGES = 200_000
_MAX_TYPE_DEPTH = 256
_CURRENT_MINOR = 6


class _SpirvError(ValueError):
    pass


_SOURCE_LANGUAGE = {
    0: "Unknown", 1: "ESSL", 2: "GLSL", 3: "OpenCL_C", 4: "OpenCL_CPP",
    5: "HLSL", 6: "CPP_for_OpenCL", 7: "SYCL", 8: "HERO_C", 9: "NZSL",
    10: "WGSL", 11: "Slang", 12: "Zig", 13: "Rust",
}
_EXECUTION_MODEL = {
    0: "Vertex", 1: "TessellationControl", 2: "TessellationEvaluation",
    3: "Geometry", 4: "Fragment", 5: "GLCompute", 6: "Kernel",
    5267: "TaskNV", 5268: "MeshNV", 5313: "RayGenerationKHR",
    5314: "IntersectionKHR", 5315: "AnyHitKHR", 5316: "ClosestHitKHR",
    5317: "MissKHR", 5318: "CallableKHR", 5364: "TaskEXT", 5365: "MeshEXT",
}
_STAGE = {
    0: "vertex", 1: "tessellation_control", 2: "tessellation_evaluation",
    3: "geometry", 4: "fragment", 5: "compute", 6: "kernel",
    5267: "task", 5268: "mesh", 5313: "ray_generation", 5314: "intersection",
    5315: "any_hit", 5316: "closest_hit", 5317: "miss", 5318: "callable",
    5364: "task", 5365: "mesh",
}
_EXECUTION_MODE = {
    0: "Invocations", 1: "SpacingEqual", 2: "SpacingFractionalEven",
    3: "SpacingFractionalOdd", 4: "VertexOrderCw", 5: "VertexOrderCcw",
    6: "PixelCenterInteger", 7: "OriginUpperLeft", 8: "OriginLowerLeft",
    9: "EarlyFragmentTests", 10: "PointMode", 11: "Xfb", 12: "DepthReplacing",
    14: "DepthGreater", 15: "DepthLess", 16: "DepthUnchanged", 17: "LocalSize",
    18: "LocalSizeHint", 19: "InputPoints", 20: "InputLines",
    21: "InputLinesAdjacency", 22: "Triangles", 23: "InputTrianglesAdjacency",
    24: "Quads", 25: "Isolines", 26: "OutputVertices", 27: "OutputPoints",
    28: "OutputLineStrip", 29: "OutputTriangleStrip", 30: "VecTypeHint",
    31: "ContractionOff", 35: "SubgroupSize", 36: "SubgroupsPerWorkgroup",
    37: "SubgroupsPerWorkgroupId", 38: "LocalSizeId", 39: "LocalSizeHintId",
}
_ADDRESSING_MODEL = {0: "Logical", 1: "Physical32", 2: "Physical64", 5348: "PhysicalStorageBuffer64"}
_MEMORY_MODEL = {0: "Simple", 1: "GLSL450", 2: "OpenCL", 3: "Vulkan"}
_STORAGE_CLASS = {
    0: "UniformConstant", 1: "Input", 2: "Uniform", 3: "Output", 4: "Workgroup",
    5: "CrossWorkgroup", 6: "Private", 7: "Function", 8: "Generic",
    9: "PushConstant", 10: "AtomicCounter", 11: "Image", 12: "StorageBuffer",
    5328: "CallableDataKHR", 5329: "IncomingCallableDataKHR", 5338: "RayPayloadKHR",
    5339: "HitAttributeKHR", 5342: "IncomingRayPayloadKHR", 5343: "ShaderRecordBufferKHR",
    5349: "PhysicalStorageBuffer", 5402: "TaskPayloadWorkgroupEXT",
}
_DECORATION = {
    0: "RelaxedPrecision", 1: "SpecId", 2: "Block", 3: "BufferBlock",
    4: "RowMajor", 5: "ColMajor", 6: "ArrayStride", 7: "MatrixStride",
    11: "BuiltIn", 13: "NoPerspective", 14: "Flat", 15: "Patch",
    16: "Centroid", 17: "Sample", 18: "Invariant", 19: "Restrict",
    20: "Aliased", 21: "Volatile", 22: "Constant", 23: "Coherent",
    24: "NonWritable", 25: "NonReadable", 29: "Stream", 30: "Location",
    31: "Component", 32: "Index", 33: "Binding", 34: "DescriptorSet",
    35: "Offset", 36: "XfbBuffer", 37: "XfbStride", 43: "InputAttachmentIndex",
    44: "Alignment", 5271: "PerPrimitiveEXT", 5272: "PerViewNV",
    5273: "PerTaskNV", 5285: "PerVertexKHR", 5300: "NonUniform",
    5635: "UserSemantic",
}
_BUILTIN = {
    0: "Position", 1: "PointSize", 3: "ClipDistance", 4: "CullDistance",
    5: "VertexId", 6: "InstanceId", 7: "PrimitiveId", 8: "InvocationId",
    9: "Layer", 10: "ViewportIndex", 11: "TessLevelOuter", 12: "TessLevelInner",
    13: "TessCoord", 14: "PatchVertices", 15: "FragCoord", 16: "PointCoord",
    17: "FrontFacing", 18: "SampleId", 19: "SamplePosition", 20: "SampleMask",
    22: "FragDepth", 23: "HelperInvocation", 24: "NumWorkgroups",
    25: "WorkgroupSize", 26: "WorkgroupId", 27: "LocalInvocationId",
    28: "GlobalInvocationId", 29: "LocalInvocationIndex", 42: "VertexIndex",
    43: "InstanceIndex", 5319: "LaunchIdKHR", 5320: "LaunchSizeKHR",
}
_CAPABILITY = {
    0: "Matrix", 1: "Shader", 2: "Geometry", 3: "Tessellation", 4: "Addresses",
    5: "Linkage", 6: "Kernel", 7: "Vector16", 8: "Float16Buffer", 9: "Float16",
    10: "Float64", 11: "Int64", 12: "Int64Atomics", 13: "ImageBasic",
    14: "ImageReadWrite", 15: "ImageMipmap", 17: "Pipes", 18: "Groups",
    22: "Int16", 32: "ClipDistance", 33: "CullDistance", 35: "SampleRateShading",
    39: "Int8", 40: "InputAttachment", 41: "SparseResidency",
    4433: "StorageBuffer16BitAccess", 4448: "StorageBuffer8BitAccess",
    4472: "RayQueryKHR", 4479: "RayTracingKHR", 5283: "MeshShadingEXT",
    5301: "ShaderNonUniform", 5302: "RuntimeDescriptorArray",
    5345: "VulkanMemoryModel", 5347: "PhysicalStorageBufferAddresses",
}
_DIM = {0: "1D", 1: "2D", 2: "3D", 3: "Cube", 4: "Rect", 5: "Buffer", 6: "SubpassData"}
_IMAGE_FORMAT = {
    0: "Unknown", 1: "Rgba32f", 2: "Rgba16f", 3: "R32f", 4: "Rgba8",
    5: "Rgba8Snorm", 21: "Rgba32i", 24: "R32i", 30: "Rgba32ui", 33: "R32ui",
}
_ACCESS = {0: "ReadOnly", 1: "WriteOnly", 2: "ReadWrite"}

# Exact contiguous ranges from the current Khronos core grammar. Keeping the
# holes out matters: extension opcode spaces are sparse, and treating a hole as
# known would silently claim complete reflection for an unknown instruction.
_KNOWN_OPCODE_RANGES = (
    (0, 8), (10, 12), (14, 17), (19, 39), (41, 46), (48, 52), (54, 57),
    (59, 75), (77, 84), (86, 107), (109, 124), (126, 152), (154, 191),
    (194, 205), (207, 215), (218, 221), (224, 225), (227, 242), (245, 257),
    (259, 271), (274, 288), (291, 366), (400, 403), (4160, 4166),
    (4181, 4186), (4190, 4190), (4195, 4195), (4416, 4434), (4445, 4463),
    (4472, 4477), (4479, 4483), (4497, 4497), (4500, 4503), (4540, 4542),
    (4545, 4545), (5000, 5007), (5011, 5012), (5056, 5056), (5074, 5076),
    (5078, 5078), (5090, 5090), (5101, 5101), (5103, 5104), (5110, 5111),
    (5115, 5115), (5119, 5119), (5121, 5121), (5126, 5127), (5129, 5129),
    (5147, 5148), (5158, 5159), (5249, 5281), (5283, 5283), (5288, 5296),
    (5299, 5341), (5344, 5352), (5358, 5382), (5384, 5384), (5390, 5398),
    (5427, 5439), (5571, 5578), (5580, 5581), (5585, 5598), (5600, 5601),
    (5609, 5611), (5614, 5615), (5630, 5633), (5699, 5816), (5818, 5820),
    (5840, 5843), (5846, 5882), (5887, 5887), (5911, 5913), (5923, 5934),
    (5938, 5938), (5946, 5947), (5949, 5949), (6016, 6032), (6035, 6035),
    (6086, 6086), (6090, 6092), (6096, 6096), (6116, 6117), (6142, 6143),
    (6145, 6145), (6163, 6166), (6199, 6199), (6221, 6221), (6231, 6235),
    (6237, 6237), (6242, 6242), (6244, 6244), (6248, 6254), (6258, 6259),
    (6401, 6408), (6426, 6426), (6428, 6429), (6529, 6531), (6916, 6918),
)

# Known instructions that affect structural reflection but are not decoded yet.
# Ordinary unhandled arithmetic/control-flow opcodes need no partial marker;
# missing types, globals, constants, or decorations do.
_UNSUPPORTED_REFLECTION_OPCODES = frozenset({
    323, 328, 4190, 4418, 4461, 4462, 5076, 5103, 5104, 5127, 5129,
    5147, 5148, 5288, 5370, 5371, 5600, *range(5700, 5713), 5818,
    6090, 6091, 6092, 6199, 6244, 6251, 6252, 6253,
})


def _enum(table: dict[int, str], value: int) -> dict[str, object]:
    return {"name": table.get(value, f"Unknown({value})"), "value": value}


def _known_opcode(opcode: int) -> bool:
    return any(lo <= opcode <= hi for lo, hi in _KNOWN_OPCODE_RANGES)


def _decode_string(words: tuple[int, ...], start: int = 0) -> tuple[str, int]:
    raw = b"".join(word.to_bytes(4, "little") for word in words[start:])
    nul = raw.find(b"\0")
    if nul < 0:
        raise _SpirvError("unterminated literal string")
    used = nul // 4 + 1
    if any(raw[nul + 1:used * 4]):
        raise _SpirvError("non-zero literal string padding")
    try:
        return raw[:nul].decode("utf-8"), start + used
    except UnicodeDecodeError as exc:
        raise _SpirvError("literal string is not valid UTF-8") from exc


def _read(path: Path) -> tuple[bytes, str, tuple[int, int, int, int, int]]:
    if path.suffix.casefold() != ".spv":
        raise _SpirvError("not a .spv file")
    try:
        if not stat.S_ISREG(path.stat().st_mode):
            raise _SpirvError("SPIR-V input is not a regular file")
        with path.open("rb") as handle:
            data = handle.read(_MAX_BYTES + 1)
    except OSError as exc:
        raise _SpirvError(str(exc)) from exc
    if len(data) > _MAX_BYTES:
        raise _SpirvError("SPIR-V file exceeds 50 MiB limit")
    if len(data) < 20:
        raise _SpirvError("SPIR-V header is truncated")
    if len(data) % 4:
        raise _SpirvError("SPIR-V size is not 32-bit aligned")
    little = struct.unpack_from("<I", data)[0]
    big = struct.unpack_from(">I", data)[0]
    if little == _MAGIC:
        endian = "<"
    elif big == _MAGIC:
        endian = ">"
    else:
        raise _SpirvError("invalid SPIR-V magic")
    header = struct.unpack_from(f"{endian}5I", data)
    version, bound, schema = header[1], header[3], header[4]
    if version & 0xFF0000FF:
        raise _SpirvError("malformed SPIR-V version word")
    if ((version >> 16) & 0xFF) != 1:
        raise _SpirvError("unsupported SPIR-V major version")
    if bound == 0:
        raise _SpirvError("SPIR-V id bound must be nonzero")
    if schema != 0:
        raise _SpirvError("unsupported SPIR-V schema")
    return data, endian, header


def _validate_instructions(data: bytes, endian: str) -> None:
    pos = 20
    count = 0
    while pos < len(data):
        first = struct.unpack_from(f"{endian}I", data, pos)[0]
        words = first >> 16
        if words == 0:
            raise _SpirvError(f"zero instruction word count at W{pos // 4}")
        end = pos + words * 4
        if end > len(data):
            raise _SpirvError(f"truncated instruction at W{pos // 4}")
        count += 1
        if count > _MAX_INSTRUCTIONS:
            raise _SpirvError("SPIR-V instruction limit exceeded")
        pos = end


def _instructions(data: bytes, endian: str):
    pos = 20
    while pos < len(data):
        first = struct.unpack_from(f"{endian}I", data, pos)[0]
        count, opcode = first >> 16, first & 0xFFFF
        operands = (() if count == 1 else
                    struct.unpack_from(f"{endian}{count - 1}I", data, pos + 4))
        yield pos // 4, opcode, operands
        pos += count * 4


def _arity(operands: tuple[int, ...], minimum: int, name: str,
           maximum: int | None = None) -> None:
    if len(operands) < minimum or (maximum is not None and len(operands) > maximum):
        expected = str(minimum) if maximum == minimum else f"{minimum}..{maximum or 'n'}"
        raise _SpirvError(f"{name} has {len(operands)} operands, expected {expected}")


def _parse(data: bytes, endian: str, bound: int) -> dict:
    state = {
        "names": {}, "member_names": {}, "strings": {}, "types": {}, "constants": {},
        "spec_constants": {}, "variables": {}, "functions": {}, "calls": [],
        "entries": [], "modes": defaultdict(list), "decorations": defaultdict(list),
        "member_decorations": defaultdict(list), "groups": set(), "group_targets": [],
        "group_members": [], "capabilities": [], "extensions": [], "ext_imports": {},
        "sources": [], "source_extensions": [], "module_processed": [],
        "memory_model": None, "unknown_opcodes": set(), "unhandled_opcodes": set(),
    }
    declared: dict[int, str] = {}
    current_function: int | None = None
    current_debug: tuple[int, int, int] | None = None
    fact_count = 0
    decoration_count = 0

    def check_id(value: int, what: str) -> int:
        if value == 0 or value >= bound:
            raise _SpirvError(f"{what} id %{value} is outside bound {bound}")
        return value

    def declare(value: int, what: str) -> int:
        nonlocal fact_count
        check_id(value, what)
        if value in declared:
            raise _SpirvError(f"duplicate result id %{value}")
        declared[value] = what
        fact_count += 1
        if fact_count > _MAX_ENTITIES:
            raise _SpirvError("SPIR-V reflected entity limit exceeded")
        return value

    def decoration(number: int, values: tuple[int, ...], *, ids: bool = False,
                   text: str | None = None) -> dict:
        if ids:
            for value in values:
                check_id(value, "decoration operand")
        result = {"name": _DECORATION.get(number, f"Unknown({number})"),
                  "value": number, "operands": list(values)}
        if ids:
            result["id_operands"] = True
        if text is not None:
            result["text"] = text
        return result

    def append_decoration(container: dict, key, record: dict) -> None:
        nonlocal decoration_count
        if decoration_count >= _MAX_ENTITIES:
            raise _SpirvError("SPIR-V decoration limit exceeded")
        container[key].append(record)
        decoration_count += 1

    type_kinds = {
        19: "void", 20: "bool", 21: "int", 22: "float", 23: "vector",
        24: "matrix", 25: "image", 26: "sampler", 27: "sampled_image",
        28: "array", 29: "runtime_array", 30: "struct", 31: "opaque",
        32: "pointer", 33: "function_type", 34: "event", 35: "device_event",
        36: "reserve_id", 37: "queue", 38: "pipe", 322: "pipe_storage",
        327: "named_barrier", 4163: "tensor", 4417: "untyped_pointer",
        4456: "cooperative_matrix", 4472: "ray_query", 5115: "buffer",
        5281: "hit_object", 5313: "hit_object", 5341: "acceleration_structure",
        5358: "cooperative_matrix", 6086: "buffer_surface",
    }

    for offset, opcode, operands in _instructions(data, endian):
        debug = current_debug
        if opcode == 2 or opcode == 4 or opcode == 10 or opcode == 330:
            _arity(operands, 1, "literal string instruction")
            text, end = _decode_string(operands)
            if end != len(operands):
                raise _SpirvError("extra operands after literal string")
            key = {2: "source_extensions", 4: "source_extensions", 10: "extensions",
                   330: "module_processed"}[opcode]
            state[key].append(text)
        elif opcode == 3:
            _arity(operands, 2, "OpSource")
            source = {"language": _enum(_SOURCE_LANGUAGE, operands[0]), "version": operands[1]}
            if len(operands) >= 3:
                source["file_id"] = check_id(operands[2], "source file")
            if len(operands) >= 4:
                _text, end = _decode_string(operands, 3)
                if end != len(operands):
                    raise _SpirvError("extra OpSource operands")
                source["embedded_source"] = True
            state["sources"].append(source)
        elif opcode == 5:
            _arity(operands, 2, "OpName")
            target = check_id(operands[0], "name target")
            text, end = _decode_string(operands, 1)
            if end != len(operands):
                raise _SpirvError("extra OpName operands")
            state["names"][target] = text
        elif opcode == 6:
            _arity(operands, 3, "OpMemberName")
            target = check_id(operands[0], "member name type")
            text, end = _decode_string(operands, 2)
            if end != len(operands):
                raise _SpirvError("extra OpMemberName operands")
            state["member_names"][(target, operands[1])] = text
        elif opcode == 7:
            _arity(operands, 2, "OpString")
            result = declare(operands[0], "string")
            text, end = _decode_string(operands, 1)
            if end != len(operands):
                raise _SpirvError("extra OpString operands")
            state["strings"][result] = text
        elif opcode == 8:
            _arity(operands, 3, "OpLine", 3)
            current_debug = (check_id(operands[0], "debug file"), operands[1], operands[2])
        elif opcode == 317:
            _arity(operands, 0, "OpNoLine", 0)
            current_debug = None
        elif opcode == 11:
            _arity(operands, 2, "OpExtInstImport")
            result = declare(operands[0], "extended instruction import")
            text, end = _decode_string(operands, 1)
            if end != len(operands):
                raise _SpirvError("extra OpExtInstImport operands")
            state["ext_imports"][result] = text
        elif opcode == 14:
            _arity(operands, 2, "OpMemoryModel", 2)
            state["memory_model"] = (_enum(_ADDRESSING_MODEL, operands[0]),
                                     _enum(_MEMORY_MODEL, operands[1]))
        elif opcode == 15:
            _arity(operands, 3, "OpEntryPoint")
            function = check_id(operands[1], "entry point")
            name, end = _decode_string(operands, 2)
            interface = [check_id(value, "entry interface") for value in operands[end:]]
            state["entries"].append({"model": operands[0], "function": function,
                                     "name": name, "interface": interface, "offset": offset})
        elif opcode in (16, 331):
            _arity(operands, 2, "OpExecutionMode")
            entry = check_id(operands[0], "execution mode entry")
            values = list(operands[2:])
            if opcode == 331:
                values = [check_id(value, "execution mode operand") for value in values]
            state["modes"][entry].append({"mode": operands[1], "operands": values,
                                          "ids": opcode == 331, "offset": offset})
        elif opcode == 17:
            _arity(operands, 1, "OpCapability", 1)
            state["capabilities"].append(operands[0])
        elif opcode in type_kinds:
            minimum = {21: 3, 22: 2, 23: 3, 24: 3, 25: 8, 27: 2, 28: 3,
                       29: 2, 30: 1, 31: 2, 32: 3, 33: 2, 38: 2,
                       4163: 2, 4417: 2, 4456: 6, 5115: 2, 5358: 5, 6086: 2}.get(opcode, 1)
            _arity(operands, minimum, f"type opcode {opcode}")
            result = declare(operands[0], "type")
            args: tuple[object, ...] = tuple(operands[1:])
            if opcode == 31:
                text, end = _decode_string(operands, 1)
                if end != len(operands):
                    raise _SpirvError("extra OpTypeOpaque operands")
                args = (text,)
            refs: list[int] = []
            if opcode in (23, 24, 25, 27, 28, 29):
                refs = [int(operands[1])]
                if opcode == 28:
                    check_id(operands[2], "array length")
            elif opcode == 30:
                refs = [int(value) for value in operands[1:]]
            elif opcode == 32:
                refs = [int(operands[2])]
            elif opcode == 33:
                refs = [int(value) for value in operands[1:]]
            elif opcode in (4163, 4456, 5358):
                refs = [int(value) for value in operands[1:]]
            for ref in refs:
                check_id(ref, "type reference")
            state["types"][result] = {"kind": type_kinds[opcode], "opcode": opcode,
                                      "args": args, "refs": refs, "offset": offset,
                                      "debug": debug}
        elif opcode == 39:
            _arity(operands, 2, "OpTypeForwardPointer", 2)
            check_id(operands[0], "forward pointer")
        elif opcode in (41, 42, 43, 44, 45, 46, 48, 49, 50, 51, 52):
            _arity(operands, 2, "constant instruction")
            type_id = check_id(operands[0], "constant type")
            result = declare(operands[1], "constant")
            fact = {"type": type_id, "opcode": opcode, "words": tuple(operands[2:]),
                    "offset": offset, "debug": debug}
            state["constants"][result] = fact
            if opcode in (48, 49, 50, 51, 52):
                state["spec_constants"][result] = fact
        elif opcode == 54:
            _arity(operands, 4, "OpFunction", 4)
            if current_function is not None:
                raise _SpirvError("nested OpFunction")
            result = declare(operands[1], "function")
            check_id(operands[0], "function return type")
            check_id(operands[3], "function type")
            state["functions"][result] = {"return_type": operands[0], "control": operands[2],
                                          "function_type": operands[3], "parameters": [],
                                          "offset": offset, "debug": debug}
            current_function = result
        elif opcode == 55:
            _arity(operands, 2, "OpFunctionParameter", 2)
            if current_function is None:
                raise _SpirvError("OpFunctionParameter outside a function")
            type_id = check_id(operands[0], "parameter type")
            result = declare(operands[1], "function parameter")
            state["functions"][current_function]["parameters"].append(
                {"id": result, "type": type_id, "offset": offset, "debug": debug})
        elif opcode == 56:
            _arity(operands, 0, "OpFunctionEnd", 0)
            if current_function is None:
                raise _SpirvError("OpFunctionEnd outside a function")
            current_function = None
        elif opcode == 57:
            _arity(operands, 3, "OpFunctionCall")
            if current_function is None:
                raise _SpirvError("OpFunctionCall outside a function")
            check_id(operands[0], "call result type")
            declare(operands[1], "call result")
            target = check_id(operands[2], "called function")
            for value in operands[3:]:
                check_id(value, "call argument")
            state["calls"].append({"caller": current_function, "target": target,
                                   "offset": offset, "debug": debug})
        elif opcode == 59:
            _arity(operands, 3, "OpVariable")
            type_id = check_id(operands[0], "variable type")
            result = declare(operands[1], "variable")
            if len(operands) > 4:
                raise _SpirvError("OpVariable has too many operands")
            if len(operands) == 4:
                check_id(operands[3], "variable initializer")
            if operands[2] != 7:
                state["variables"][result] = {"type": type_id, "storage": operands[2],
                                              "offset": offset, "debug": debug}
        elif opcode in (71, 332):
            _arity(operands, 2, "OpDecorate")
            target = check_id(operands[0], "decoration target")
            append_decoration(
                state["decorations"], target,
                decoration(operands[1], tuple(operands[2:]), ids=opcode == 332),
            )
        elif opcode == 72:
            _arity(operands, 3, "OpMemberDecorate")
            target = check_id(operands[0], "member decoration type")
            append_decoration(
                state["member_decorations"], (target, operands[1]),
                decoration(operands[2], tuple(operands[3:])),
            )
        elif opcode == 73:
            _arity(operands, 1, "OpDecorationGroup", 1)
            state["groups"].add(declare(operands[0], "decoration group"))
        elif opcode == 74:
            _arity(operands, 2, "OpGroupDecorate")
            group = check_id(operands[0], "decoration group")
            targets = [check_id(value, "group decoration target") for value in operands[1:]]
            state["group_targets"].append((group, targets))
        elif opcode == 75:
            _arity(operands, 3, "OpGroupMemberDecorate")
            if (len(operands) - 1) % 2:
                raise _SpirvError("OpGroupMemberDecorate has an incomplete pair")
            group = check_id(operands[0], "decoration group")
            pairs = [(check_id(operands[i], "group member type"), operands[i + 1])
                     for i in range(1, len(operands), 2)]
            state["group_members"].append((group, pairs))
        elif opcode in (5632, 5633):
            minimum = 3 if opcode == 5632 else 4
            _arity(operands, minimum, "OpDecorateString")
            target = check_id(operands[0], "string decoration target")
            member = None if opcode == 5632 else operands[1]
            dec_index = 1 if opcode == 5632 else 2
            text, end = _decode_string(operands, dec_index + 1)
            if end != len(operands):
                raise _SpirvError("extra string decoration operands")
            record = decoration(operands[dec_index], (), text=text)
            if member is None:
                append_decoration(state["decorations"], target, record)
            else:
                append_decoration(state["member_decorations"], (target, member), record)
        elif not _known_opcode(opcode):
            state["unknown_opcodes"].add(opcode)
        elif opcode in _UNSUPPORTED_REFLECTION_OPCODES:
            state["unhandled_opcodes"].add(opcode)

    if current_function is not None:
        raise _SpirvError("unterminated OpFunction")
    for group, targets in state["group_targets"]:
        if group not in state["groups"]:
            raise _SpirvError(f"unknown decoration group %{group}")
        inherited = state["decorations"].get(group, ())
        for target in targets:
            if decoration_count + len(inherited) > _MAX_ENTITIES:
                raise _SpirvError("SPIR-V decoration limit exceeded")
            state["decorations"][target].extend(inherited)
            decoration_count += len(inherited)
    for group, pairs in state["group_members"]:
        if group not in state["groups"]:
            raise _SpirvError(f"unknown decoration group %{group}")
        inherited = state["decorations"].get(group, ())
        for target, member in pairs:
            if decoration_count + len(inherited) > _MAX_ENTITIES:
                raise _SpirvError("SPIR-V decoration limit exceeded")
            state["member_decorations"][(target, member)].extend(inherited)
            decoration_count += len(inherited)
    for entry in state["entries"]:
        if entry["function"] not in state["functions"]:
            raise _SpirvError(f"entry point %{entry['function']} is not a function")
        for interface in entry["interface"]:
            if interface not in state["variables"]:
                raise _SpirvError(f"entry interface %{interface} is not a global variable")
    for call in state["calls"]:
        if call["target"] not in state["functions"]:
            raise _SpirvError(f"call target %{call['target']} is not a function")
    return state


def _constant_value(fact: dict, types: dict[int, dict]):
    opcode = fact["opcode"]
    if opcode in (41, 48):
        return True
    if opcode in (42, 49):
        return False
    words = fact["words"]
    type_fact = types.get(fact["type"])
    if opcode not in (43, 50) or not type_fact or type_fact["kind"] != "int" or not words:
        return None
    width, signed = type_fact["args"][:2]
    if width > 64:
        return None
    value = sum(word << (32 * index) for index, word in enumerate(words))
    value &= (1 << width) - 1
    if signed and value & (1 << (width - 1)):
        value -= 1 << width
    return value


def _emit(path: Path, header: tuple[int, int, int, int, int], endian: str,
          state: dict) -> dict:
    _, version, generator, bound, schema = header
    major, minor = (version >> 16) & 0xFF, (version >> 8) & 0xFF
    str_path, stem = str(path), _file_stem(path)
    nodes: list[dict] = []
    edges: list[dict] = []
    file_nid = _make_id(str_path)

    def debug_metadata(debug) -> dict:
        if not debug:
            return {}
        file_id, line, column = debug
        return {"debug_file": state["strings"].get(file_id, f"%{file_id}"),
                "debug_line": line, "debug_column": column}

    entries_by_function: dict[int, list[dict]] = defaultdict(list)
    for entry in state["entries"]:
        entries_by_function[entry["function"]].append(entry)

    preferred: dict[int, str] = {}
    entity_ids = (set(state["types"]) | set(state["variables"]) |
                  set(state["spec_constants"]) | set(state["functions"]))
    for function in state["functions"].values():
        entity_ids.update(param["id"] for param in function["parameters"])
    for result in entity_ids:
        preferred[result] = state["names"].get(result, "")
        if not preferred[result] and entries_by_function.get(result):
            preferred[result] = entries_by_function[result][0]["name"]
    counts = Counter(name for name in preferred.values() if name)
    ids: dict[int, str] = {}
    for result in entity_ids:
        name = preferred[result]
        ids[result] = (_make_id(stem, name) if name and counts[name] == 1 else
                       _make_id(stem, name, str(result)) if name else
                       _make_id(stem, "spirv", str(result)))

    def add_node(result_id: int | None, nid: str, label: str, kind: str, offset: int | str,
                 shader: dict, debug=None) -> None:
        if len(nodes) >= _MAX_ENTITIES:
            raise _SpirvError("SPIR-V reflected entity limit exceeded")
        spirv = dict(shader.pop("spirv", {}))
        if result_id is not None:
            spirv["result_id"] = result_id
        spirv.update(debug_metadata(debug))
        shader = {"language": "spirv", "kind": kind, **shader, "spirv": spirv}
        nodes.append({"id": nid, "label": sanitize_label(label), "file_type": "code",
                      "type": kind, "source_file": str_path,
                      "source_location": offset if isinstance(offset, str) else f"W{offset}",
                      "metadata": sanitize_metadata({"shader": shader})})

    def add_edge(source: str, target: str, relation: str, offset: int,
                 metadata: dict | None = None) -> None:
        if source == target:
            return
        if len(edges) >= _MAX_EDGES:
            raise _SpirvError("SPIR-V reflected edge limit exceeded")
        edge = {"source": source, "target": target, "relation": relation,
                "confidence": "EXTRACTED", "confidence_score": 1.0,
                "source_file": str_path, "source_location": f"W{offset}", "weight": 1.0}
        if metadata:
            edge["metadata"] = sanitize_metadata(metadata)
        edges.append(edge)

    source_info = state["sources"][0] if state["sources"] else None
    module_spirv = {
        "version": f"{major}.{minor}", "version_word": version,
        "generator": {"raw": generator, "tool_id": generator >> 16,
                      "tool_version": generator & 0xFFFF},
        "bound": bound, "schema": schema, "byte_order": "little" if endian == "<" else "big",
        "capabilities": [_enum(_CAPABILITY, value) for value in state["capabilities"]],
        "capability_names": [_CAPABILITY.get(value, f"Unknown({value})")
                             for value in state["capabilities"]],
        "extensions": state["extensions"],
        "extended_instruction_imports": [
            {"result_id": result, "name": name} for result, name in state["ext_imports"].items()
        ],
        "module_processed": state["module_processed"],
        "unknown_opcodes": sorted(state["unknown_opcodes"]),
        "unhandled_opcodes": sorted(state["unhandled_opcodes"]),
        "reflection_partial": bool(
            state["unknown_opcodes"] or state["unhandled_opcodes"] or minor > _CURRENT_MINOR
        ),
    }
    if state["memory_model"]:
        module_spirv["addressing_model"], module_spirv["memory_model"] = state["memory_model"]
    if source_info:
        module_spirv["source_language"] = source_info["language"]
        module_spirv["source_version"] = source_info["version"]
        if "file_id" in source_info:
            module_spirv["debug_source_file"] = state["strings"].get(
                source_info["file_id"], f"%{source_info['file_id']}")
    add_node(None, file_nid, path.name, "module", "L1", {"spirv": module_spirv})

    constants = {result: _constant_value(fact, state["types"])
                 for result, fact in state["constants"].items()}
    type_cache: dict[int, str] = {}

    def type_text(result: int) -> str:
        """Render the single-dependency type chain without Python recursion."""
        if result in type_cache:
            return type_cache[result]

        root = result
        chain: list[tuple[int, dict]] = []
        active: set[int] = set()
        while True:
            if result in type_cache:
                text = type_cache[result]
                break
            fact = state["types"].get(result)
            if not fact:
                text = f"%{result}"
                break
            if result in active:
                text = state["names"].get(result, f"%{result}")
                break

            kind, args = fact["kind"], fact["args"]
            dependency = (
                args[1] if kind == "pointer" else args[0]
                if kind in ("vector", "matrix", "array", "runtime_array", "image", "sampled_image")
                else None
            )
            if dependency is None:
                if kind == "void": text = "void"
                elif kind == "bool": text = "bool"
                elif kind == "int": text = ("int" if args[1] else "uint") + str(args[0])
                elif kind == "float": text = "float" + str(args[0])
                elif kind == "struct": text = state["names"].get(result, f"struct %{result}")
                elif kind == "opaque": text = str(args[0])
                else: text = kind
                type_cache[result] = text
                break

            active.add(result)
            chain.append((result, fact))
            if len(chain) > _MAX_TYPE_DEPTH:
                raise _SpirvError("SPIR-V type nesting limit exceeded")
            result = dependency

        for result, fact in reversed(chain):
            kind, args = fact["kind"], fact["args"]
            if kind in ("vector", "matrix"):
                text = f"{text}x{args[1]}"
            elif kind == "array":
                length = constants.get(args[1])
                text = f"{text}[{length if length is not None else '%' + str(args[1])}]"
            elif kind == "runtime_array":
                text = f"{text}[]"
            elif kind == "pointer":
                text = f"ptr<{_STORAGE_CLASS.get(args[0], args[0])}, {text}>"
            elif kind == "image":
                text = f"image<{_DIM.get(args[1], args[1])}, {text}>"
            else:
                text = f"sampled<{text}>"
            type_cache[result] = text
        return type_cache.get(root, text)

    roots = {fact["type"] for fact in state["variables"].values()}
    roots.update(fact["type"] for fact in state["spec_constants"].values())
    for result, function in state["functions"].items():
        roots.update((function["return_type"], function["function_type"]))
        roots.update(param["type"] for param in function["parameters"])
    roots.update(result for result in state["types"] if result in state["names"])
    reachable: set[int] = set()
    pending = list(roots)
    while pending:
        result = pending.pop()
        if result in reachable or result not in state["types"]:
            continue
        reachable.add(result)
        pending.extend(state["types"][result]["refs"])

    def dec_value(decs: list[dict], value: int):
        for dec in decs:
            if dec["value"] == value and dec["operands"]:
                return dec["operands"][0]
        return None

    def layout(decs: list[dict]) -> dict:
        result = {}
        for number, key in ((6, "array_stride"), (7, "matrix_stride"), (35, "offset"),
                            (36, "xfb_buffer"), (37, "xfb_stride"), (44, "alignment")):
            value = dec_value(decs, number)
            if value is not None: result[key] = value
        for number, key in ((2, "block"), (3, "buffer_block"), (4, "row_major"),
                            (5, "column_major")):
            if any(dec["value"] == number for dec in decs): result[key] = True
        return result

    for result in sorted(reachable):
        fact = state["types"][result]
        decs = list(state["decorations"].get(result, ()))
        shader = {"type": type_text(result),
                  "spirv": {"type_kind": fact["kind"], "opcode": fact["opcode"],
                            "decorations": decs}}
        type_layout = layout(decs)
        if type_layout: shader["layout"] = type_layout
        add_node(result, ids[result], state["names"].get(result, type_text(result)), "type",
                 fact["offset"], shader, fact["debug"])
        add_edge(file_nid, ids[result], "contains", fact["offset"])
        for ref in fact["refs"]:
            if ref in reachable:
                add_edge(ids[result], ids[ref], "references", fact["offset"])
        if fact["kind"] == "struct":
            for index, member_type in enumerate(fact["args"]):
                member_name = state["member_names"].get((result, index), f"member {index}")
                member_nid = _make_id(ids[result], member_name, str(index))
                member_decs = list(state["member_decorations"].get((result, index), ()))
                member_shader = {"type": type_text(member_type),
                                 "spirv": {"member_index": index, "decorations": member_decs}}
                member_layout = layout(member_decs)
                if member_layout: member_shader["layout"] = member_layout
                builtin = dec_value(member_decs, 11)
                location = dec_value(member_decs, 30)
                if builtin is not None or location is not None:
                    member_shader["interface"] = {}
                    if builtin is not None: member_shader["interface"]["builtin"] = _enum(_BUILTIN, builtin)
                    if location is not None: member_shader["interface"]["location"] = location
                add_node(None, member_nid, member_name, "member", fact["offset"], member_shader)
                add_edge(ids[result], member_nid, "contains", fact["offset"])
                if member_type in reachable:
                    add_edge(member_nid, ids[member_type], "references", fact["offset"])

    def unwrap(type_id: int) -> tuple[int, list[object], int | None]:
        dimensions: list[object] = []
        pointer_storage = None
        fact = state["types"].get(type_id)
        if fact and fact["kind"] == "pointer":
            pointer_storage, type_id = fact["args"][:2]
        while True:
            fact = state["types"].get(type_id)
            if not fact or fact["kind"] not in ("array", "runtime_array"):
                break
            if fact["kind"] == "array":
                dimensions.append(constants.get(fact["args"][1], f"%{fact['args'][1]}"))
            else:
                dimensions.append("runtime")
            type_id = fact["args"][0]
        return type_id, dimensions, pointer_storage

    for result, fact in state["variables"].items():
        decs = list(state["decorations"].get(result, ()))
        base, dimensions, pointer_storage = unwrap(fact["type"])
        base_fact = state["types"].get(base, {})
        base_decs = list(state["decorations"].get(base, ()))
        storage, base_kind = fact["storage"], base_fact.get("kind")
        if storage == 1: kind = "stage_input"
        elif storage == 3: kind = "stage_output"
        elif storage == 9: kind = "push_constant"
        elif storage == 12 or (storage == 2 and any(d["value"] == 3 for d in base_decs)):
            kind = "storage_buffer"
        elif storage == 2 and any(d["value"] == 2 for d in base_decs): kind = "uniform_buffer"
        elif storage == 0 and base_kind == "sampler": kind = "sampler"
        elif storage == 0 and base_kind == "sampled_image": kind = "combined_image_sampler"
        elif storage == 0 and base_kind == "image":
            kind = "input_attachment" if len(base_fact.get("args", ())) > 1 and base_fact["args"][1] == 6 else (
                "storage_image" if len(base_fact.get("args", ())) > 5 and base_fact["args"][5] == 2 else "sampled_texture")
        elif storage == 0 and base_kind == "acceleration_structure": kind = "acceleration_structure"
        else: kind = "global_variable"
        image_access = None
        access_qualifier = None
        if base_kind == "image" and len(base_fact.get("args", ())) > 7:
            access_qualifier = int(base_fact["args"][7])
            image_access = {0: "read", 1: "write", 2: "read_write"}.get(
                access_qualifier, "unknown"
            )
        shader = {"type": type_text(fact["type"]),
                  "spirv": {"storage_class": _enum(_STORAGE_CLASS, storage),
                            "pointer_storage_class": _enum(_STORAGE_CLASS, pointer_storage)
                            if pointer_storage is not None else None,
                             "base_type_id": base, "array_dimensions": dimensions,
                             "decorations": decs}}
        if access_qualifier is not None:
            shader["spirv"]["access_qualifier"] = _enum(_ACCESS, access_qualifier)
        descriptor_set, binding = dec_value(decs, 34), dec_value(decs, 33)
        if descriptor_set is not None or binding is not None:
            shader["bindings"] = [{"descriptor_set": descriptor_set, "binding": binding}]
        interface = {}
        for number, key in ((30, "location"), (31, "component"), (32, "index"),
                            (43, "input_attachment_index")):
            value = dec_value(decs, number)
            if value is not None: interface[key] = value
        builtin = dec_value(decs, 11)
        if builtin is not None: interface["builtin"] = _enum(_BUILTIN, builtin)
        if interface: shader["interface"] = interface
        combined_layout = layout(base_decs + decs)
        if combined_layout: shader["layout"] = combined_layout
        access_decs = decs + list(state["decorations"].get(fact["type"], ())) + base_decs
        if any(dec["value"] == 24 for dec in access_decs): shader["access"] = "read"
        elif any(dec["value"] == 25 for dec in access_decs): shader["access"] = "write"
        elif image_access is not None: shader["access"] = image_access
        elif kind in ("stage_output",): shader["access"] = "write"
        elif kind in ("storage_buffer", "storage_image"): shader["access"] = "read_write"
        else: shader["access"] = "read"
        add_node(result, ids[result], state["names"].get(result, f"%{result}"), kind,
                 fact["offset"], shader, fact["debug"])
        add_edge(file_nid, ids[result], "contains", fact["offset"])
        if fact["type"] in reachable:
            add_edge(ids[result], ids[fact["type"]], "references", fact["offset"])

    for result, fact in state["spec_constants"].items():
        decs = list(state["decorations"].get(result, ()))
        value = constants[result]
        spirv = {"opcode": fact["opcode"], "decorations": decs,
                 "spec_id": dec_value(decs, 1), "value_words": list(fact["words"])}
        if value is not None: spirv["default_value"] = value
        shader = {"type": type_text(fact["type"]), "spirv": spirv}
        add_node(result, ids[result], state["names"].get(result, f"spec %{result}"),
                 "specialization_constant", fact["offset"], shader, fact["debug"])
        add_edge(file_nid, ids[result], "contains", fact["offset"])
        if fact["type"] in reachable:
            add_edge(ids[result], ids[fact["type"]], "references", fact["offset"])

    for result, fact in state["functions"].items():
        entries = entries_by_function.get(result, [])
        modes = []
        thread_group_size = None
        for mode in state["modes"].get(result, ()):
            values = [constants.get(value, f"%{value}") for value in mode["operands"]] if mode["ids"] else mode["operands"]
            modes.append({"name": _EXECUTION_MODE.get(mode["mode"], f"Unknown({mode['mode']})"),
                          "value": mode["mode"], "operands": values, "id_operands": mode["ids"]})
            if mode["mode"] in (17, 38) and len(values) == 3:
                thread_group_size = values
        shader = {"entry_point": entries[0]["name"] if entries else None,
                  "stage": _STAGE.get(entries[0]["model"]) if entries else None,
                  "thread_group_size": thread_group_size,
                  "type": type_text(fact["function_type"]),
                  "spirv": {"return_type_id": fact["return_type"],
                            "function_type_id": fact["function_type"],
                            "function_control": fact["control"],
                            "entry_points": [{"name": entry["name"],
                                              "execution_model": _enum(_EXECUTION_MODEL, entry["model"])}
                                             for entry in entries],
                            "execution_modes": modes}}
        add_node(result, ids[result], preferred[result] or f"function %{result}",
                 "entry_point" if entries else "function", fact["offset"], shader, fact["debug"])
        add_edge(file_nid, ids[result], "contains", fact["offset"])
        for type_id in (fact["return_type"], fact["function_type"]):
            if type_id in reachable: add_edge(ids[result], ids[type_id], "references", fact["offset"])
        for index, param in enumerate(fact["parameters"]):
            param_id = param["id"]
            label = preferred[param_id] or f"parameter {index}"
            add_node(param_id, ids[param_id], label, "parameter", param["offset"],
                     {"type": type_text(param["type"]), "spirv": {"index": index}}, param["debug"])
            add_edge(ids[result], ids[param_id], "contains", param["offset"])
            if param["type"] in reachable:
                add_edge(ids[param_id], ids[param["type"]], "references", param["offset"])

    for call in state["calls"]:
        add_edge(ids[call["caller"]], ids[call["target"]], "calls", call["offset"],
                 debug_metadata(call["debug"]))
    for entry in state["entries"]:
        source = ids[entry["function"]]
        for interface_id in entry["interface"]:
            storage = state["variables"][interface_id]["storage"]
            relation = "stage_input" if storage == 1 else "stage_output" if storage == 3 else "references"
            add_edge(source, ids[interface_id], relation, entry["offset"],
                     {"stage": _STAGE.get(entry["model"]), "entry_point": entry["name"]})

    if len(nodes) > _MAX_ENTITIES:
        raise _SpirvError("SPIR-V reflected entity limit exceeded")
    return {"nodes": nodes, "edges": edges}


def extract_spirv(path: Path) -> dict:
    """Reflect a binary .spv module without invoking a compiler or disassembler.

    Malformed and over-limit inputs never produce a partial graph: they return
    empty nodes/edges plus an error. Well-formed unrecognized opcodes are skipped
    and recorded as partial reflection on the module node.
    """
    try:
        path = Path(path)
        data, endian, header = _read(path)
        _validate_instructions(data, endian)
        state = _parse(data, endian, header[3])
        return _emit(path, header, endian, state)
    except (_SpirvError, OSError, struct.error, ValueError, RecursionError) as exc:
        return {"nodes": [], "edges": [], "error": str(exc)}
