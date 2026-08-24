from pathlib import Path

from graphify.extract import _get_extractor, extract
from graphify.extractors.spirv import extract_spirv
from graphify.extractors.shader import extract_glsl, extract_hlsl, extract_slang


def _node(result: dict, label: str) -> dict:
    return next(node for node in result["nodes"] if node["label"] == label)


def _edges(result: dict, relation: str) -> list[dict]:
    return [edge for edge in result["edges"] if edge["relation"] == relation]


def test_shader_dispatch_is_case_insensitive() -> None:
    assert _get_extractor(Path("x.HLSL")) is extract_hlsl
    assert _get_extractor(Path("x.HLSLI")) is extract_hlsl
    assert _get_extractor(Path("x.GLSL")) is extract_glsl
    assert _get_extractor(Path("x.SLANG")) is extract_slang
    assert _get_extractor(Path("x.SPV")) is extract_spirv


def test_hlsl_reflects_resources_entry_io_calls_and_include(tmp_path: Path) -> None:
    include = tmp_path / "common.hlsli"
    include.write_text("void helper() {}", encoding="utf-8")
    shader = tmp_path / "main.hlsl"
    shader.write_text(
        '''#include "common.hlsli"
[[vk::binding(1, 2)]] Texture2D<float4> gTex : register(t0, space1);
SamplerState gSampler : register(s0);
RWTexture2D<float4> gOut : register(u0);
cbuffer Params : register(b0) { float4 tint; row_major float4x4 transform; };
struct Input { float2 uv : TEXCOORD0; };
[numthreads(8, 4, 1)] void mainCS(uint3 id : SV_DispatchThreadID) {
    gOut[id.xy] = gTex.SampleLevel(gSampler, id.xy, 0);
    helper();
}
void helper() {}
''',
        encoding="utf-8",
    )

    result = extract_hlsl(shader)

    texture = _node(result, "gTex")["metadata"]["shader"]
    assert texture["resource_kind"] == "texture"
    assert {binding["kind"] for binding in texture["bindings"]} == {"register", "vulkan"}
    assert _node(result, "Params")["metadata"]["shader"]["kind"] == "uniform_buffer"
    assert sum(node["label"] == "Params" for node in result["nodes"]) == 1
    assert {"tint", "transform"} <= {node["label"] for node in result["nodes"]}
    assert _node(result, "mainCS()")["metadata"]["shader"]["thread_group_size"] == [8, 4, 1]
    assert any(edge.get("target_file") == str(include.resolve()) for edge in _edges(result, "imports_from"))
    assert any(edge["relation"] == "calls" for edge in result["edges"])
    assert {edge["relation"] for edge in result["edges"]} >= {"stage_input", "uses"}


def test_glsl_reflects_layout_blocks_specialization_and_compute_io(tmp_path: Path) -> None:
    shader = tmp_path / "main.glsl"
    shader.write_text(
        """#version 460
layout(set=0,binding=1) uniform sampler2D tex;
layout(set=0,binding=2,rgba16f) writeonly uniform image2D outputImage;
layout(std140,set=1,binding=0) uniform Params { vec4 tint; } params;
layout(constant_id=3) const int MODE = 0;
layout(location=0) in vec2 uv;
layout(location=0) out vec4 color;
layout(local_size_x=8, local_size_y=8, local_size_z=1) in;
vec4 shade(vec2 p) { return texture(tex, p); }
void main() { color = shade(uv); imageStore(outputImage, ivec2(0), color); }
""",
        encoding="utf-8",
    )

    result = extract_glsl(shader)

    main = _node(result, "main()")["metadata"]["shader"]
    assert main["stage"] == "compute"
    assert main["thread_group_size"] == [8, 8, 1]
    assert _node(result, "MODE")["metadata"]["shader"]["kind"] == "specialization_constant"
    params = _node(result, "params")["metadata"]["shader"]
    assert params["layout"]["std140"] is True
    assert params["bindings"] == [{"kind": "descriptor", "set": 1, "binding": 0}]
    assert {edge["relation"] for edge in result["edges"]} >= {"calls", "uses", "stage_input", "stage_output"}


def test_slang_reflects_modules_interfaces_generics_and_parameter_blocks(tmp_path: Path) -> None:
    (tmp_path / "Common.slang").write_text("module Common;", encoding="utf-8")
    (tmp_path / "part.slang").write_text("implementing Demo;", encoding="utf-8")
    shader = tmp_path / "Demo.slang"
    shader.write_text(
        '''module Demo;
import Common;
__exported import PublicAPI;
__include "part.slang";
interface ILight { associatedtype Sample; float3 eval(float3 p); }
struct Light<T : ILight> : ILight { float3 eval(float3 p) { return p; } }
struct Material { Texture2D<float4> tex; SamplerState sampler; };
[[vk::binding(0, 1)]] ParameterBlock<Material> material;
[require(spvShaderClockKHR)]
[shader("compute")]
[numthreads(4, 2, 1)]
void mainCS(uint3 id : SV_DispatchThreadID) { helper(id); }
void helper(uint3 id) { material.tex.SampleLevel(material.sampler, id.xy, 0); }
''',
        encoding="utf-8",
    )

    result = extract_slang(shader)

    assert _node(result, "ILight")["metadata"]["shader"]["kind"] == "interface"
    assert _node(result, "Light")["metadata"]["shader"]["generics"] == ["T : ILight"]
    assert _node(result, "material")["metadata"]["shader"]["resource_kind"] == "parameter_block"
    entry = _node(result, "mainCS()")["metadata"]["shader"]
    assert entry["stage"] == "compute"
    assert entry["capabilities"] == ["spvShaderClockKHR"]
    assert any(edge["relation"] == "implements" for edge in result["edges"])
    assert any(edge["relation"] == "re_exports" for edge in result["edges"])
    assert sum(edge["relation"] == "imports_from" for edge in result["edges"]) >= 2
    assert {edge["relation"] for edge in result["edges"]} >= {"calls", "uses", "stage_input"}


def test_error_subtrees_and_comments_do_not_create_shader_nodes(tmp_path: Path) -> None:
    shader = tmp_path / "partial.hlsl"
    shader.write_text(
        "// Texture2D<float4> fake;\nvoid broken( { Ghost value; }\nvoid valid() {}\n",
        encoding="utf-8",
    )

    result = extract_hlsl(shader)

    assert result["parse_errors"]["count"] >= 1
    assert _node(result, "partial.hlsl")["metadata"]["shader"]["reflection_partial"] is True
    assert not any(node["label"] in {"fake", "Ghost", "value"} for node in result["nodes"])


def test_cross_file_shader_calls_require_include_evidence(tmp_path: Path) -> None:
    helper = tmp_path / "helper.hlsli"
    helper.write_text("float helper() { return 1; }", encoding="utf-8")
    caller = tmp_path / "caller.hlsl"

    def calls(result: dict) -> set[tuple[str, str]]:
        labels = {node["id"]: node["label"] for node in result["nodes"]}
        return {
            (labels[edge["source"]], labels[edge["target"]])
            for edge in result["edges"] if edge["relation"] == "calls"
        }

    caller.write_text("float mainNoImport() { return helper(); }", encoding="utf-8")
    result = extract([caller, helper], cache_root=tmp_path, root=tmp_path, parallel=False)
    assert ("mainNoImport()", "helper()") not in calls(result)

    caller.write_text(
        '#include "helper.hlsli"\nfloat mainWithImport() { return helper(); }',
        encoding="utf-8",
    )
    result = extract([caller, helper], cache_root=tmp_path, root=tmp_path, parallel=False)
    assert ("mainWithImport()", "helper()") in calls(result)


def test_hlsl_semantic_entry_overloads_resource_arrays_and_use_lines(tmp_path: Path) -> None:
    shader = tmp_path / "graphics.hlsl"
    shader.write_text(
        """Texture2D<float4> first, textures[2];
SamplerState samp;
AppendStructuredBuffer<float4> appended;
ConsumeStructuredBuffer<float4> consumed;
float4 adjust(float2 uv) { return float4(uv, 0, 1); }
float4 adjust(float2 uv, float scale) { return float4(uv * scale, 0, 1); }
float4 mainPS(float2 uv : TEXCOORD0) : SV_Target0 {
    appended.Append(consumed.Consume());
    return adjust(uv, 1.0) + textures[1].SampleLevel(samp, uv, 0);
}
""",
        encoding="utf-8",
    )

    result = extract_hlsl(shader)
    main = _node(result, "mainPS()")["metadata"]["shader"]
    assert main["kind"] == "entry_point"
    assert main["stage"] == "unknown"
    assert {edge["relation"] for edge in result["edges"]} >= {"stage_input", "stage_output"}

    assert _node(result, "textures")["metadata"]["shader"]["layout"]["array_dimensions"] == ["2"]
    assert _node(result, "appended")["metadata"]["shader"]["access"] == "write"
    assert _node(result, "consumed")["metadata"]["shader"]["access"] == "read"

    overloads = [node for node in result["nodes"] if node["label"] == "adjust()"]
    assert len(overloads) == 2
    assert len({node["id"] for node in overloads}) == 2
    assert {node["metadata"]["shader"]["arity"] for node in overloads} == {1, 2}
    arity_two = next(node["id"] for node in overloads if node["metadata"]["shader"]["arity"] == 2)
    assert any(edge["relation"] == "calls" and edge["target"] == arity_two for edge in result["edges"])

    labels = {node["id"]: node["label"] for node in result["nodes"]}
    use_lines = {
        labels[edge["target"]]: edge["source_location"]
        for edge in result["edges"]
        if edge["relation"] == "uses"
    }
    assert use_lines["appended"] == "L8"
    assert use_lines["consumed"] == "L8"
    assert use_lines["textures"] == "L9"


def test_hlsl_attribute_offsets_remain_byte_aligned_after_unicode(tmp_path: Path) -> None:
    shader = tmp_path / "unicode.hlsl"
    shader.write_text(
        "// " + "Ж" * 200 + "\n[numthreads(8, 4, 1)] void mainCS(uint3 id : SV_DispatchThreadID) {}\n",
        encoding="utf-8",
    )

    entry = _node(extract_hlsl(shader), "mainCS()")["metadata"]["shader"]
    assert entry["kind"] == "entry_point"
    assert entry["thread_group_size"] == [8, 4, 1]


def test_glsl_interface_blocks_multiple_declarators_and_readonly_ssbo(tmp_path: Path) -> None:
    shader = tmp_path / "blocks.glsl"
    shader.write_text(
        """#version 460
layout(location=0) in VS_OUT { vec2 uv; } fs_in;
layout(location=0) out FS_OUT { vec4 color; } fs_out;
layout(std430,set=0,binding=0) readonly buffer Data { float values[]; } data[2];
layout(set=0,binding=1) uniform sampler2D tex0, tex1;
void main() { fs_out.color = texture(tex1, fs_in.uv) + vec4(data[0].values[0]); }
""",
        encoding="utf-8",
    )

    result = extract_glsl(shader)
    assert _node(result, "fs_in")["metadata"]["shader"]["kind"] == "stage_io_block"
    assert _node(result, "fs_out")["metadata"]["shader"]["kind"] == "stage_io_block"
    assert {edge["relation"] for edge in result["edges"]} >= {"stage_input", "stage_output"}
    assert _node(result, "tex1")["metadata"]["shader"]["resource_kind"] == "sampler"

    data = _node(result, "data")["metadata"]["shader"]
    assert data["access"] == "read"
    assert data["layout"]["array_dimensions"] == ["2"]
    labels = {node["id"]: node["label"] for node in result["nodes"]}
    assert any(edge["relation"] == "uses" and labels[edge["target"]] == "data" for edge in result["edges"])


def test_slang_recovers_parameter_block_and_generic_call(tmp_path: Path) -> None:
    shader = tmp_path / "parameter.slang"
    shader.write_text(
        """struct Material { Texture2D<float4> tex; };
ParameterBlock<Material> material;
T identity<T>(T value) { return value; }
[shader("compute")]
[numthreads(1, 1, 1)]
void mainCS(uint3 id : SV_DispatchThreadID) {
    int value = identity<int>(1);
    material.tex.Load(int3(id.xy, 0));
}
""",
        encoding="utf-8",
    )

    result = extract_slang(shader)
    assert _node(result, "material")["metadata"]["shader"]["resource_kind"] == "parameter_block"
    identity = _node(result, "identity()")
    assert any(edge["relation"] == "calls" and edge["target"] == identity["id"] for edge in result["edges"])
    labels = {node["id"]: node["label"] for node in result["nodes"]}
    assert any(edge["relation"] == "uses" and labels[edge["target"]] == "material" for edge in result["edges"])


def test_shader_cross_file_calls_follow_reexports_and_nested_includes(tmp_path: Path) -> None:
    a = tmp_path / "a.hlsl"
    b = tmp_path / "b.hlsli"
    c = tmp_path / "c.hlsli"
    a.write_text(
        '#include "b.hlsli"\nfloat4 main(float2 uv : TEXCOORD0) : SV_Target { return from_nested(uv); }\n',
        encoding="utf-8",
    )
    b.write_text('#include "c.hlsli"\n', encoding="utf-8")
    c.write_text("float4 from_nested(float2 uv) { return float4(uv, 0, 1); }\n", encoding="utf-8")

    common = tmp_path / "Common.slang"
    main = tmp_path / "Main.slang"
    common.write_text("void from_export() {}\n", encoding="utf-8")
    main.write_text(
        '__exported import Common;\n[shader("compute")]\nvoid mainCS() { from_export(); }\n',
        encoding="utf-8",
    )

    result = extract([a, b, c, common, main], cache_root=tmp_path, root=tmp_path, parallel=False)
    labels = {node["id"]: node["label"] for node in result["nodes"]}
    call_pairs = {
        (labels[edge["source"]], labels[edge["target"]])
        for edge in result["edges"]
        if edge["relation"] == "calls"
    }
    assert ("main()", "from_nested()") in call_pairs
    assert ("mainCS()", "from_export()") in call_pairs


def test_hlsl_recovers_dollar_prefixed_decompiler_cbuffer(tmp_path: Path) -> None:
    shader = tmp_path / "globals.hlsl"
    shader.write_text(
        "cbuffer $Globals : register(b0) { float Exposure : packoffset(c0.x); };",
        encoding="utf-8",
    )

    result = extract_hlsl(shader)

    globals_node = _node(result, "$Globals")["metadata"]["shader"]
    assert globals_node["kind"] == "uniform_buffer"
    assert globals_node["bindings"] == [{"kind": "register", "register": "b0"}]
    assert _node(result, "Exposure")["metadata"]["shader"]["layout"]["packoffset"] == "c0.x"
