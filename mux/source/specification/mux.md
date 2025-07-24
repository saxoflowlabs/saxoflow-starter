### Module Specification: 2x1 Multiplexer 

 Module Name : `mux2x1`

 Functionality :
A 2x1 multiplexer selects one of two input signals based on a single-bit select signal and routes it to the output.

---

###  Interface Specification 

| Signal Name | Direction | Width | Description                                      |
| ----------- | --------- | ----- | ------------------------------------------------ |
| `a`         | Input     | 1 bit | First input to the multiplexer                   |
| `b`         | Input     | 1 bit | Second input to the multiplexer                  |
| `sel`       | Input     | 1 bit | Select line: selects between `a` and `b`         |
| `y`         | Output    | 1 bit | Output: reflects the selected input (`a` or `b`) |

---

###  Behavioral Description 

  When `sel = 0`, output `y` should reflect the value of input `a`.
  When `sel = 1`, output `y` should reflect the value of input `b`.

---

###  Testbench Requirements 

  Exhaustively test all input combinations of `a`, `b`, and `sel`.
  Include waveform observation (e.g., using `$dumpfile` and `$dumpvars` if using Icarus Verilog).
  Ensure the output `y` is asserted correctly for each case.
  Optional: Add delays or use `initial`/`always` blocks to drive inputs over time.
