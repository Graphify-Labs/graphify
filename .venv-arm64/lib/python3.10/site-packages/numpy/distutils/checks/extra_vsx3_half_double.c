/**
 * Assembler may not fully support the following VSX3 scalar
 * instructions, even though compilers report VSX3 support.
 */
int main(void)
{
    unsigned short bits = 0xFF;
    double f;
    __asm__ __volatile__("xscvhpdp %x0,%x1" : "=wa"(f) : "wa"(bits));
    __asm__ __volatile__ ("xscvdphp %x0,%x1" : "=wa" (bits) : "wa" (f));
    return bits;
}
