#include <metal_stdlib>
using namespace metal;

struct Vec3 {
    float x;
    float y;
    float z;
};

float dot3(const Vec3 a, const Vec3 b) {
    return a.x * b.x + a.y * b.y + a.z * b.z;
}

kernel void saxpy(
    device const float* x [[buffer(0)]],
    device float* y [[buffer(1)]],
    constant float& a [[buffer(2)]],
    uint i [[thread_position_in_grid]]
) {
    y[i] = a * x[i] + y[i];
}
