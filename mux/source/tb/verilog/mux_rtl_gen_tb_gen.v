module tb_mux2x1;

    // Inputs
    reg a;
    reg b;
    reg sel;

    // Outputs
    wire y;

    // Instantiate the DUT
    mux2x1 uut (
        .a(a),
        .b(b),
        .sel(sel),
        .y(y)
    );

    initial begin
        // Dump waveforms
        $dumpfile("tb.vcd");
        $dumpvars(0, tb_mux2x1);

        // Initialize Inputs
        a = 0;
        b = 0;
        sel = 0;

        // Apply test vectors
        #10 sel = 0; a = 0; b = 0; #10;
        #10 sel = 0; a = 0; b = 1; #10;
        #10 sel = 0; a = 1; b = 0; #10;
        #10 sel = 0; a = 1; b = 1; #10;
        #10 sel = 1; a = 0; b = 0; #10;
        #10 sel = 1; a = 0; b = 1; #10;
        #10 sel = 1; a = 1; b = 0; #10;
        #10 sel = 1; a = 1; b = 1; #10;

        // End simulation
        $finish;
    end

    initial begin
        // Monitor output
        $monitor("Time = %0t : a = %b, b = %b, sel = %b, y = %b", $time, a, b, sel, y);
    end

endmodule