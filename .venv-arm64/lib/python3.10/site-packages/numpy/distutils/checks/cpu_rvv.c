#ifndef __riscv_vector
  #error RVV not supported
#endif

#include <riscv_vector.h>

int main(void)
{
    size_t vlmax = __riscv_vsetvlmax_e32m1();
    vuint32m1_t a = __riscv_vmv_v_x_u32m1(0, vlmax);
    vuint32m1_t b = __riscv_vadd_vv_u32m1(a, a, vlmax);
    return __riscv_vmv_x_s_u32m1_u32(b);
}
