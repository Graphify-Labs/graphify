#version 450

// Regenerate sample.spv with:
// glslangValidator -V -S frag -g sample.glsl -o sample.spv

layout(set = 0, binding = 0) uniform sampler2D SourceTexture;
layout(location = 0) in vec2 input_uv;
layout(location = 0) out vec4 output_color;
layout(constant_id = 0) const float Exposure = 1.0;

vec4 ApplyExposure(vec4 color)
{
    return color * Exposure;
}

void main()
{
    output_color = ApplyExposure(texture(SourceTexture, input_uv));
}
