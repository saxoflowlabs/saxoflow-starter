module tb_mux2x1;

    reg a;
    reg b;
    reg sel;
    wire y;

    // Instantiate the DUT
    mux2x1 uut (
        .a(a),
        .b(b),
        .sel(sel),
        .y(y)
    );

    initial begin
        $dumpfile("tb.vcd");
        $dumpvars(0, tb_mux2x1);
    end

    initial begin
        // Test all combinations of inputs
        integer i;
        for (i = 0; i < 8; i = i + 1) begin
            {a, b, sel} = i[2:0];
            #10;
            $display("Time: %0d, a: %b, b: %b, sel: %b, y: %b", $time, a, b, sel, y);
        end
        #10;
        $finish;
    end

endmodule