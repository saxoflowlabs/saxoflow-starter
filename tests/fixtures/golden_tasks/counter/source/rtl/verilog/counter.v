module counter(input wire clk, input wire rst, output reg [3:0] value);
  always @(posedge clk) begin
    if (rst) begin
      value <= 4'd0;
    end else begin
      value <= value + 4'd1;
    end
  end
endmodule
