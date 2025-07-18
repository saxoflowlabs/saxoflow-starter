`timescale 1ns/1ps

// Simple 8-bit Adder
module adder (
    input  logic [7:0] a,
    input  logic [7:0] b,
    output logic [7:0] sum
);
    assign sum = a + b;
endmodule
