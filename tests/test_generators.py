"""
Tests for generators in the agentic AI package.

These tests focus on the static utility functions used to extract code
from LLM outputs and ensure that generator agents return cleaned
results when provided with dummy language models.  The actual LLM
interaction is replaced by stubs to avoid network calls.
"""

from saxoflow_agenticai.agents.generators.rtl_gen import extract_verilog_code, RTLGenAgent
from saxoflow_agenticai.agents.generators.tb_gen import extract_verilog_tb_code, TBGenAgent
from saxoflow_agenticai.agents.generators.report_agent import _extract_report_content, ReportAgent


def test_extract_verilog_code_from_markdown():
    llm_output = """
    Here is the generated code:
    ```verilog
    module test(input a, output b);
      assign b = a;
    endmodule
    ```
    """
    code = extract_verilog_code(llm_output)
    # Should contain just the module definition without code fences
    assert code.startswith("module test")
    assert code.strip().endswith("endmodule")


def test_extract_tb_code_simple():
    llm_output = """
    ```systemverilog
    module tb;
      initial begin
        $display("Hello");
      end
    endmodule
    ```
    """
    code = extract_verilog_tb_code(llm_output)
    assert "module tb" in code
    assert code.strip().endswith("endmodule")


def test_report_extracts_content():
    raw = {
        "content": "``\nSome markdown``\nReport text\nAIMessage"
    }
    clean = _extract_report_content(raw)
    assert "Report text" in clean


def test_rtlgen_agent_runs_with_stub(monkeypatch):
    """RTLGenAgent.run should return extracted Verilog code when llm returns a markdown block."""
    class DummyLLM:
        def __init__(self, resp):
            self.resp = resp
        def invoke(self, prompt):
            return self.resp
    fake_resp = """
    ```verilog
    module m;
    endmodule
    ```
    """
    monkeypatch.setattr(RTLGenAgent, "__init__", lambda self, llm=None, verbose=False: None)
    agent = RTLGenAgent()
    agent.llm = DummyLLM(fake_resp)
    code = agent.run("spec")
    assert "module m" in code


def test_tbgen_agent_runs_with_stub(monkeypatch):
    """TBGenAgent.run should return extracted testbench code when llm returns a code block."""
    class DummyLLM:
        def __init__(self, resp):
            self.resp = resp
        def invoke(self, prompt):
            return self.resp
    fake_resp = """
    ```systemverilog
    module tb;
    endmodule
    ```
    """
    monkeypatch.setattr(TBGenAgent, "__init__", lambda self, llm=None, verbose=False: None)
    agent = TBGenAgent()
    agent.llm = DummyLLM(fake_resp)
    code = agent.run("spec", "module m; endmodule", "m")
    assert "module tb" in code