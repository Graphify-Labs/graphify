// Verilator-style C++ testbench fixture
#include "Vwidget.h"
#include <verilated.h>

int main() {
    Vwidget* dut = new Vwidget;
    dut->eval();
    delete dut;
    return 0;
}
