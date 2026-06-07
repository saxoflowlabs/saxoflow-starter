from __future__ import annotations

from types import SimpleNamespace

import pytest

from saxoflow_agenticai.agents.generators import fprop_gen


class DummyLLM:
    def __init__(self, output: str):
        self.output = output
        self.prompts: list[str] = []

    def invoke(self, prompt: str):
        self.prompts.append(prompt)
        return SimpleNamespace(content=self.output)


VALID_HARNESS = """\
module traffic_controller_formal;
    (* gclk *) reg clk;
    (* anyseq *) reg reset_n;
    reg f_past_valid = 1'b0;

    always @(posedge clk)
        f_past_valid <= 1'b1;

    always @(posedge clk) begin
        if (f_past_valid && !$past(reset_n))
            assert (1'b1);
    end
endmodule
"""


def test_extract_formal_harness_removes_heading_fence_and_prose():
    raw = (
        "assertions\n"
        "```systemverilog\n"
        f"{VALID_HARNESS}"
        "```\n"
        "This harness is ready."
    )

    result = fprop_gen.extract_formal_harness(raw)

    assert result == VALID_HARNESS
    assert not result.startswith("assertions")
    assert "```" not in result
    assert "This harness is ready" not in result


def test_extract_formal_harness_rejects_loose_property_syntax():
    with pytest.raises(ValueError, match="complete module harness"):
        fprop_gen.extract_formal_harness(
            "property p; @(posedge clk) a |-> b; endproperty"
        )


def test_extract_formal_harness_rejects_unguarded_past():
    invalid = """\
module dut_formal;
    (* gclk *) reg clk;
    always @(posedge clk)
        assert ($past(clk));
endmodule
"""
    with pytest.raises(ValueError, match="f_past_valid"):
        fprop_gen.extract_formal_harness(invalid)


def test_run_returns_normalized_harness_and_uses_compatibility_prompt():
    llm = DummyLLM(f"assertions\n```systemverilog\n{VALID_HARNESS}```")
    agent = fprop_gen.FormalPropGenAgent(llm=llm)

    result = agent.run("active-low synchronous reset", "module dut; endmodule")

    assert result == VALID_HARNESS
    assert "Yosys and SymbiYosys" in llm.prompts[0]
    assert "Do not include Markdown fences" in llm.prompts[0]


def test_improve_prompt_includes_previous_harness_and_review():
    llm = DummyLLM(VALID_HARNESS)
    agent = fprop_gen.FormalPropGenAgent(llm=llm)

    result = agent.improve(
        "traffic controller",
        "module traffic_controller; endmodule",
        "module old_formal; endmodule",
        "Cycle-Accuracy Problems: reset is checked too early",
    )

    assert result == VALID_HARNESS
    prompt = llm.prompts[0]
    assert "module old_formal; endmodule" in prompt
    assert "reset is checked too early" in prompt
