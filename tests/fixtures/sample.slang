module Sample;

interface ICurve
{
    float3 apply(float3 color);
}

struct LinearCurve : ICurve
{
    float3 apply(float3 color)
    {
        return color;
    }
};

struct Params
{
    float exposure;
};

ParameterBlock<Params> gParams;

[shader("compute")]
[numthreads(8, 8, 1)]
void mainCS(uint3 id : SV_DispatchThreadID)
{
}
