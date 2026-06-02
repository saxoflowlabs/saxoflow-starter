`timescale 1ns/1ps

module counter_tb;

reg clk = 1'b0;
reg rst_n = 1'b0;
reg en = 1'b0;
wire [3:0] count;

counter dut (
    .clk(clk),
    .rst_n(rst_n),
    .en(en),
    .count(count)
);

always #5 clk = ~clk;

initial begin
    $dumpfile("counter_tb.vcd");
    $dumpvars(0, counter_tb);

    #12 rst_n = 1'b1;
    en = 1'b1;
    repeat (5) @(posedge clk);

    en = 1'b0;
    repeat (2) @(posedge clk);

    $finish;
end

endmodule
