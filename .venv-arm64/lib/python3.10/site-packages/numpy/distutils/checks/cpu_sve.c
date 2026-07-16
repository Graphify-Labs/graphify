#include <arm_sve.h>

int accumulate(svint64_t a, svint64_t b) {
    svbool_t p = svptrue_b64();
    return svaddv(p, svmla_z(p, a, a, b));
}

int main(void)
{
    svbool_t p = svptrue_b64();
    svint64_t a = svdup_s64(1);
    svint64_t b = svdup_s64(2);
    return accumulate(a, b);
}
