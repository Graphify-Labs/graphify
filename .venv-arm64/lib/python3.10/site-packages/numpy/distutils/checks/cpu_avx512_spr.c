#if defined(DETECT_FEATURES) && defined(__INTEL_COMPILER)
    /*
     * Unlike GCC and CLANG, Intel Compiler exposes all supported intrinsics,
     * whether or not the build options for those features are specified.
     * Therefore, we must test #definitions of CPU features when option native/host
     * is enabled via `--cpu-baseline` or through env var `CFLAGS` otherwise
     * the test will be broken and leads to enable all possible features.
     */
    #if !defined(__AVX512FP16__)
        #error "HOST/ARCH doesn't support Sapphire Rapids AVX512FP16 features"
    #endif
#endif

#include <immintrin.h>

int main(int argc, char **argv)
{
/* clang has a bug regarding our spr coode, see gh-23730. */
#if __clang__
#error
#endif
    __m512h a = _mm512_loadu_ph((void*)argv[argc-1]);
    __m512h temp = _mm512_fmadd_ph(a, a, a);
    _mm512_storeu_ph((void*)(argv[argc-1]), temp);
    return 0;
}
