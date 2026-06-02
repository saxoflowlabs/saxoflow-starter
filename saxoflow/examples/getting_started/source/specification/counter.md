# Counter Specification

Build a 4-bit synchronous up-counter.

Inputs:

- `clk`: rising-edge clock.
- `rst_n`: active-low reset.
- `en`: count enable.

Output:

- `count`: current 4-bit counter value.

Behavior:

- Reset drives `count` to zero.
- When enabled, `count` increments by one on each rising clock edge.
- When disabled, `count` holds its current value.
