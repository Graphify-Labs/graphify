#include <metal_stdlib>
using namespace metal;

struct Vec3 {
    float x;
    float y;
    float z;
};

float dot3(Vec3 a, Vec3 b) {
    return a.x * b.x + a.y * b.y + a.z * b.z;
}

kernel void saxpy(
    device const float* x [[buffer(0)]],
    device float* y [[buffer(1)]],
    constant float& a [[buffer(2)]],
    uint id [[thread_position_in_grid]]
) {
    y[id] = a * x[id] + y[id];
}
