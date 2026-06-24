#include <cstdio>
#include <vector>

struct Vec3 {
    float x;
    float y;
    float z;
};

__device__ float dot(const Vec3& a, const Vec3& b) {
    return a.x * b.x + a.y * b.y + a.z * b.z;
}

__global__ void saxpy(int n, float a, const float* x, float* y) {
    int i = blockIdx.x * blockDim.x + threadIdx.x;
    if (i < n) {
        y[i] = a * x[i] + y[i];
    }
}

float host_norm(const Vec3& v) {
    return dot(v, v);
}

int main() {
    Vec3 v{1.0f, 2.0f, 3.0f};
    float n = host_norm(v);
    saxpy<<<1, 256>>>(256, 2.0f, nullptr, nullptr);
    return 0;
}
