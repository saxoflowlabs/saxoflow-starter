`timescale 1ns/1ps

module top_tb;
    logic [7:0] a, b;
    logic [7:0] sum;

    // Instantiate the adder
    adder uut (
        .a(a),
        .b(b),
        .sum(sum)
    );

    // VCD waveform dump for GTKWave
    initial begin
        $dumpfile("top_tb.vcd");
        $dumpvars(0, top_tb);

        // Test vectors
        a = 8'd0;   b = 8'd0;    #10;
        a = 8'd5;   b = 8'd10;   #10;
        a = 8'd50;  b = 8'd25;   #10;
        a = 8'd128; b = 8'd128;  #10;
        a = 8'd255; b = 8'd1;    #10;
        a = 8'd100; b = 8'd155;  #10;
        $finish;
    end
endmodule
