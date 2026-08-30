#include "sample.hlsli"

Texture2D<float4> SourceTexture : register(t0);
SamplerState LinearSampler : register(s0);
RWTexture2D<float4> OutputTexture : register(u0);

cbuffer $Globals : register(b0)
{
    float Exposure : packoffset(c0.x);
};

[numthreads(8, 8, 1)]
void mainCS(uint3 id : SV_DispatchThreadID)
{
    float4 color = SourceTexture.Load(int3(id.xy, 0));
    OutputTexture[id.xy] = ApplyExposure(color, Exposure);
}
