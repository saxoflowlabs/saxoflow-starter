module blink_tb;
  reg clk = 0;
  wire q;
  blink dut(q, clk);

  always #5 clk = ~clk;

  initial begin
    $dumpfile("dump.vcd");
    $dumpvars(0, blink_tb);
    #100 $finish;
  end
endmodule
