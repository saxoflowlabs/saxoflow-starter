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
from saxoflow_agenticai.agents.generators.fprop_gen import FormalPropGenAgent



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


def test_extract_verilog_code_handles_single_backticks_and_quotes():
    llm_output = "`module foo; endmodule`"
    assert extract_verilog_code(llm_output).startswith("module foo")

    llm_output = "'module bar; endmodule'"
    assert extract_verilog_code(llm_output).startswith("module bar")


def test_extract_verilog_code_handles_no_module():
    llm_output = "Random text with no code block or module keyword."
    assert "Random text" in extract_verilog_code(llm_output)


def test_extract_verilog_code_handles_multiple_modules():
    llm_output = """
    ```verilog
    module m1; endmodule
    module m2; endmodule
    ```
    """
    code = extract_verilog_code(llm_output)
    assert "module m1;" in code and "module m2;" in code


def test_extract_verilog_code_escaped_newlines():
    llm_output = "module m;\\nendmodule"
    assert "module m;" in extract_verilog_code(llm_output)
    assert "\nendmodule" in extract_verilog_code(llm_output)


def test_extract_tb_code_handles_backticks_and_quotes():
    out = "`module tb; endmodule`"
    assert "module tb;" in extract_verilog_tb_code(out)
    out = "'module tb2; endmodule'"
    assert "module tb2;" in extract_verilog_tb_code(out)


def test_extract_tb_code_no_module():
    out = "No code at all."
    assert "No code" in extract_verilog_tb_code(out)


def test_extract_tb_code_multiple_modules():
    out = "module t1; endmodule\nmodule t2; endmodule"
    code = extract_verilog_tb_code(out)
    assert "module t1;" in code and "module t2;" in code


def test_extract_tb_code_escaped_newlines():
    out = "module tb;\\nendmodule"
    assert "module tb;" in extract_verilog_tb_code(out)
    assert "\nendmodule" in extract_verilog_tb_code(out)


def test_extract_report_content_handles_AIMessage_obj():
    class Dummy:
        def __init__(self, content):
            self.content = content
    ai_msg = Dummy("Final report content\nAIMessage")
    out = _extract_report_content(ai_msg)
    assert "Final report content" in out


def test_extract_report_content_handles_plain_string():
    raw = "```\nBlock\n```\nSome text\nAIMessage"
    out = _extract_report_content(raw)
    assert "Some text" in out


def test_fpropgen_agent_runs_with_stub(monkeypatch):
    class DummyLLM:
        def __init__(self, resp):
            self.resp = resp
        def invoke(self, prompt):
            return self.resp
    monkeypatch.setattr(FormalPropGenAgent, "__init__", lambda self, llm=None, verbose=False: None)
    agent = FormalPropGenAgent()
    agent.llm = DummyLLM("assert property (p1);")
    fprops = agent.run("spec", "module m; endmodule")
    assert "property" in fprops


def test_fpropgen_agent_improve_runs_with_stub(monkeypatch):
    class DummyLLM:
        def __init__(self, resp):
            self.resp = resp
        def invoke(self, prompt):
            return self.resp
    monkeypatch.setattr(FormalPropGenAgent, "__init__", lambda self, llm=None, verbose=False: None)
    agent = FormalPropGenAgent()
    agent.llm = DummyLLM("assert property (improved);")
    improved = agent.improve("spec", "rtl", "prev", "review")
    assert "improved" in improved
