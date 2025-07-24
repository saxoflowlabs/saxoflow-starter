module mux2x1 #(
    // No parameters needed for this design
    // Add parameters if necessary for configurability
) (
    input  wire a,  // 1-bit input
    input  wire b,  // 1-bit input
    input  wire sel, // 1-bit select signal
    output wire y    // 1-bit output
);

// Description: Selects between input 'a' and 'b' based on 'sel'
assign y = sel ? b : a;

endmodule