module tb;
    // Clock and reset
    reg clk;
    reg reset;
    // DUT inputs
    reg [3:0] A;
    reg [3:0] B;
    reg       carry_in;
    reg       enable;
    // DUT outputs
    wire [3:0] sum;
    wire       carry_out;
    wire       overflow;
    wire       zero_flag;
    wire       result_valid;

    // Error counter
    integer error_count;
    integer i;

    // Clock generation (period = 10 time units)
    initial begin
        clk = 0;
        forever #5 clk = ~clk;
    end

    // Instantiate DUT
    four_bit_adder dut (
        .clk         (clk),
        .reset       (reset),
        .A           (A),
        .B           (B),
        .carry_in    (carry_in),
        .enable      (enable),
        .sum         (sum),
        .carry_out   (carry_out),
        .overflow    (overflow),
        .zero_flag   (zero_flag),
        .result_valid(result_valid)
    );

    // Dump waveform
    initial begin
        $dumpfile("tb.vcd");
        $dumpvars(0, tb);
    end

    // Test stimulus
    initial begin
        error_count = 0;

        // Apply reset
        reset = 1'b1;
        enable = 1'b0;
        A = 4'd0;
        B = 4'd0;
        carry_in = 1'b0;
        #12;               // hold reset for > one clock
        @(posedge clk);
        reset = 1'b0;

        // Helper task to apply a vector and check results
        // Parameters: a, b, cin, exp_sum, exp_cout, exp_ovf, exp_zero, exp_valid
        // Called after enable is asserted for one cycle
        // Checks are performed after the clock edge settles (#1)
        // ---------------------------------------------------------
        // Simple addition without carry
        A = 4'd3; B = 4'd4; carry_in = 1'b0; enable = 1'b1;
        @(posedge clk); #1;
        if (sum !== 4'd7)        $display("ERROR: sum mismatch. Expected 7, got %0d", sum), error_count = error_count + 1;
        if (carry_out !== 1'b0) $display("ERROR: carry_out mismatch. Expected 0, got %b", carry_out), error_count = error_count + 1;
        if (overflow !== 1'b0)  $display("ERROR: overflow mismatch. Expected 0, got %b", overflow), error_count = error_count + 1;
        if (zero_flag !== 1'b0) $display("ERROR: zero_flag mismatch. Expected 0, got %b", zero_flag), error_count = error_count + 1;
        if (result_valid !== 1'b1) $display("ERROR: result_valid mismatch. Expected 1, got %b", result_valid), error_count = error_count + 1;
        enable = 1'b0;

        // Addition with carry propagation
        A = 4'd9; B = 4'd6; carry_in = 1'b1; enable = 1'b1;
        @(posedge clk); #1;
        if (sum !== 4'd0)        $display("ERROR: sum mismatch. Expected 0, got %0d", sum), error_count = error_count + 1;
        if (carry_out !== 1'b1) $display("ERROR: carry_out mismatch. Expected 1, got %b", carry_out), error_count = error_count + 1;
        if (overflow !== 1'b0)  $display("ERROR: overflow mismatch. Expected 0, got %b", overflow), error_count = error_count + 1;
        if (zero_flag !== 1'b1) $display("ERROR: zero_flag mismatch. Expected 1, got %b", zero_flag), error_count = error_count + 1;
        if (result_valid !== 1'b1) $display("ERROR: result_valid mismatch. Expected 1, got %b", result_valid), error_count = error_count + 1;
        enable = 1'b0;

        // Signed overflow (e.g., 7 + 7 = 14 -> overflow for signed 4-bit)
        A = 4'b0111; B = 4'b0111; carry_in = 1'b0; enable = 1'b1;
        @(posedge clk); #1;
        if (sum !== 4'b1110)    $display("ERROR: sum mismatch. Expected 1110, got %b", sum), error_count = error_count + 1;
        if (overflow !== 1'b1)  $display("ERROR: overflow mismatch. Expected 1, got %b", overflow), error_count = error_count + 1;
        if (zero_flag !== 1'b0) $display("ERROR: zero_flag mismatch. Expected 0, got %b", zero_flag), error_count = error_count + 1;
        enable = 1'b0;

        // Maximum values (15 + 15)
        A = 4'd15; B = 4'd15; carry_in = 1'b0; enable = 1'b1;
        @(posedge clk); #1;
        if (sum !== 4'b1110)    $display("ERROR: sum mismatch. Expected 1110, got %b", sum), error_count = error_count + 1;
        if (carry_out !== 1'b1) $display("ERROR: carry_out mismatch. Expected 1, got %b", carry_out), error_count = error_count + 1;
        if (overflow !== 1'b1)  $display("ERROR: overflow mismatch. Expected 1, got %b", overflow), error_count = error_count + 1;
        if (zero_flag !== 1'b0) $display("ERROR: zero_flag mismatch. Expected 0, got %b", zero_flag), error_count = error_count + 1;
        enable = 1'b0;

        // Zero result verification (0 + 0)
        A = 4'd0; B = 4'd0; carry_in = 1'b0; enable = 1'b1;
        @(posedge clk); #1;
        if (sum !== 4'd0)        $display("ERROR: sum mismatch. Expected 0, got %0d", sum), error_count = error_count + 1;
        if (carry_out !== 1'b0) $display("ERROR: carry_out mismatch. Expected 0, got %b", carry_out), error_count = error_count + 1;
        if (zero_flag !== 1'b1) $display("ERROR: zero_flag mismatch. Expected 1, got %b", zero_flag), error_count = error_count + 1;
        if (overflow !== 1'b0)  $display("ERROR: overflow mismatch. Expected 0, got %b", overflow), error_count = error_count + 1;
        enable = 1'b0;

        // Back-to-back operations without deasserting reset (should ignore)
        reset = 1'b1;
        A = 4'd5; B = 4'd2; carry_in = 1'b0; enable = 1'b1;
        @(posedge clk);
        reset = 1'b0;
        @(posedge clk); #1;
        if (result_valid !== 1'b1) $display("ERROR: result_valid after reset release. Expected 1, got %b", result_valid), error_count = error_count + 1;
        enable = 1'b0;

        // Disable operation (enable=0) – result_valid should be 0
        A = 4'd8; B = 4'd1; carry_in = 1'b0; enable = 1'b0;
        @(posedge clk); #1;
        if (result_valid !== 1'b0) $display("ERROR: result_valid when enable=0. Expected 0, got %b", result_valid), error_count = error_count + 1;

        // Summary
        if (error_count == 0)
            $display("ALL TESTS PASSED");
        else
            $display("TESTS FAILED WITH %0d ERRORS", error_count);

        $finish;
    end
endmodule