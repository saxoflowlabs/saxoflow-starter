module blink(output reg q, input clk);
  always @(posedge clk) q <= ~q;
endmodule
