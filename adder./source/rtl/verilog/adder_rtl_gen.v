module four_bit_adder (
    input  wire        clk,
    input  wire        reset,        // asynchronous active-high reset
    input  wire [3:0]  A,
    input  wire [3:0]  B,
    input  wire        carry_in,
    input  wire        enable,
    output reg  [3:0]  sum,
    output reg         carry_out,
    output reg         overflow,
    output reg         zero_flag,
    output reg         result_valid
);

    // Propagate and generate signals
    wire [3:0] p;   // propagate
    wire [3:0] g;   // generate
    assign p = A ^ B;
    assign g = A & B;

    // Carry look‑ahead chain (combinational)
    wire [4:0] carry;
    assign carry[0] = carry_in;
    assign carry[1] = g[0] | (p[0] & carry[0]);
    assign carry[2] = g[1] | (p[1] & g[0]) | (p[1] & p[0] & carry[0]);
    assign carry[3] = g[2] | (p[2] & g[1]) | (p[2] & p[1] & g[0]) |
                     (p[2] & p[1] & p[0] & carry[0]);
    assign carry[4] = g[3] | (p[3] & g[2]) | (p[3] & p[2] & g[1]) |
                     (p[3] & p[2] & p[1] & g[0]) |
                     (p[3] & p[2] & p[1] & p[0] & carry[0]);

    // Combinational results
    wire [3:0] sum_comb;
    assign sum_comb   = A ^ B ^ carry[3:0];
    wire        overflow_comb;
    assign overflow_comb = carry[3] ^ carry[4];
    wire        zero_comb;
    assign zero_comb = (sum_comb == 4'b0000);

    // Sequential output registers
    always @(posedge clk or posedge reset) begin
        if (reset) begin
            sum          <= 4'b0000;
            carry_out    <= 1'b0;
            overflow     <= 1'b0;
            zero_flag    <= 1'b0;
            result_valid <= 1'b0;
        end else if (enable) begin
            sum          <= sum_comb;
            carry_out    <= carry[4];
            overflow     <= overflow_comb;
            zero_flag    <= zero_comb;
            result_valid <= 1'b1;
        end else begin
            result_valid <= 1'b0;
        end
    end

endmodule