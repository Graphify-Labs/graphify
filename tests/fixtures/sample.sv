// Fixture for the SystemVerilog extractor (extract_verilog).
// Exercises: package + function, module definition, child-module instantiation,
// and a fully-qualified package reference (pkg::fn).
package math_pkg;
    function automatic logic [7:0] add8(input logic [7:0] a, input logic [7:0] b);
        add8 = a + b;
    endfunction
endpackage

module adder #(parameter int W = 8) (
    input  logic [W-1:0] a,
    input  logic [W-1:0] b,
    output logic [W-1:0] y
);
    assign y = math_pkg::add8(a, b);
endmodule

module top (
    input  logic [7:0] x,
    input  logic [7:0] z,
    output logic [7:0] o
);
    adder #(.W(8)) u_adder (.a(x), .b(z), .y(o));
endmodule
