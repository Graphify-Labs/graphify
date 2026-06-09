interface apb_if (input logic clk);
    logic        psel;
    logic [31:0] pwdata;
    modport master (output psel, output pwdata);
    modport slave  (input  psel, input  pwdata);
endinterface
