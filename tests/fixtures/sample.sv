package math_pkg;
endpackage

interface class Processor;
endclass

class BaseProcessor;
endclass

class Payload;
endclass

class Config;
endclass

class Result #(type T = Payload);
  T value;
endclass

class DataProcessor extends BaseProcessor implements Processor;
  Result #(Payload) current;
  rand Config m_cfg;
  protected BaseProcessor m_parent;

  function Result #(Payload) build(Payload input);
    return current;
  endfunction
endclass

module leaf;
endmodule

module top;
  import math_pkg::*;

  function int add(input int a, input int b);
    return a + b;
  endfunction

  task tick;
  endtask

  leaf u_leaf();
endmodule
