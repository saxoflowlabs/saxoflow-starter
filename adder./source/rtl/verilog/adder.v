module adder (
    input  wire [3:0] a,
    input  wire [3:0] b,
    output wire [4:0] sum
);

    // Combinational addition of two 4‑bit operands.
    // The result width is 5 bits to capture carry out.
    assign sum = a + b;

endmodule