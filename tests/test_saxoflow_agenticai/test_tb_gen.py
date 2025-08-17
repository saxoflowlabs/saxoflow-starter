# from __future__ import annotations

# """
# Tests for saxoflow_agenticai.agents.generators.tb_gen

# Goals
# -----
# - Preserve behavior while maximizing line/branch coverage.
# - Hermetic: no network; FS only via tmp_path.
# - Exercise: extraction heuristics, optional guidance, prompt loading/compose,
#   agent run/improve flows, legacy newline fix, _invoke_llm branches, tools.

# All tests explain intent in docstrings for maintainability.
# """

# import types
# from pathlib import Path
# from typing import Any

# import pytest


# # ------------------------------
# # Local doubles / helpers
# # ------------------------------

# class DummyLLM:
#     """Minimal LLM double; records prompts and returns a configured result."""
#     def __init__(self, result: Any):
#         self.result = result
#         self.seen: list[str] = []

#     def invoke(self, prompt: str) -> Any:
#         self.seen.append(prompt)
#         return self.result


# class DummyPrompt:
#     """PromptTemplate stand-in exposing .format(**kwargs) like LangChain."""
#     def __init__(self, fmt: str):
#         self.fmt = fmt

#     def format(self, **kwargs) -> str:
#         return self.fmt.format(**kwargs)


# def _fresh_module():
#     """Reload SUT to avoid global state leaking across tests."""
#     import importlib
#     return importlib.reload(
#         importlib.import_module("saxoflow_agenticai.agents.generators.tb_gen")
#     )


# # ------------------------------
# # extract_verilog_tb_code
# # ------------------------------

# @pytest.mark.parametrize(
#     "raw, expected_contains",
#     [
#         # Code fences with explicit language
#         ("```verilog\nmodule a; endmodule\n```", "module a; endmodule"),
#         ("```systemverilog\nmodule a; endmodule\n```", "module a; endmodule"),
#         # Stray single backticks at line boundaries
#         ("`module b; endmodule`", "module b; endmodule"),
#         # content="..." wrappers
#         ('content="module c; endmodule"', "module c; endmodule"),
#         # “Here is …” (case-insensitive) prefix
#         ("Here is the TB:\nmodule d; endmodule", "module d; endmodule"),
#         # Multiple modules → joined with a blank line
#         ("module m1; endmodule\n====\nmodule m2; endmodule", "module m1; endmodule\n\nmodule m2; endmodule"),
#         # Fallback: find first 'module' and include the rest
#         ("intro\ntext\nmodule e; endmodule\ntrail", "module e; endmodule\ntrail"),
#         # No 'module' → trimmed plain text
#         ("```no module here```", "no module here"),
#         # Escaped newlines become real
#         ("module x;\\nendmodule\\n", "module x;\nendmodule\n"),
#         # Smart quotes normalized
#         ('module f; string s = “hi”; endmodule', 'string s = "hi";'),
#     ],
# )
# def test_extract_verilog_tb_code_cases(raw, expected_contains):
#     """Verify robust extraction across common LLM output nuisances."""
#     sut = _fresh_module()
#     out = sut.extract_verilog_tb_code(raw)
#     assert expected_contains in out


# # ------------------------------
# # Guidance + prompt loaders
# # ------------------------------

# def test__maybe_read_guidance_success_and_warn(tmp_path, caplog):
#     """
#     _maybe_read_guidance: returns content if file exists, else warns and returns empty.
#     """
#     sut = _fresh_module()
#     pdir = tmp_path / "prompts"
#     pdir.mkdir()
#     ok = pdir / "tb_guidelines.txt"
#     ok.write_text("GUIDE", encoding="utf-8")

#     # Point module to temp prompts dir
#     sut._PROMPTS_DIR = pdir

#     # Success path (exists)
#     text_ok = sut._maybe_read_guidance("tb_guidelines.txt", "TB guidelines")
#     assert text_ok == "GUIDE"

#     # Missing → warning + empty
#     with caplog.at_level("WARNING"):
#         text_missing = sut._maybe_read_guidance("nope.txt", "TB guidelines")
#     assert text_missing == ""
#     assert any("Optional TB guidelines file not found" in rec.message for rec in caplog.records)


# def test__load_prompt_from_pkg_success_and_fail(tmp_path):
#     """
#     _load_prompt_from_pkg: reads existing file; raises FileNotFoundError otherwise.
#     """
#     sut = _fresh_module()
#     pdir = tmp_path / "prompts"
#     pdir.mkdir()
#     base = pdir / "tbgen_prompt.txt"
#     base.write_text("BASE", encoding="utf-8")

#     sut._PROMPTS_DIR = pdir
#     assert sut._load_prompt_from_pkg("tbgen_prompt.txt") == "BASE"

#     with pytest.raises(FileNotFoundError):
#         sut._load_prompt_from_pkg("missing.txt")


# def test__build_tb_prompt_variants(monkeypatch):
#     """
#     _build_tb_prompt: validates ordering and marker blocks when guidance present/absent.
#     """
#     sut = _fresh_module()

#     # Parametrize via monkeypatching internal reader
#     def reader(filename: str, label: str) -> str:  # noqa: ARG001
#         if "guidelines" in filename:
#             return "G"
#         if "constructs" in filename:
#             return "C"
#         return ""

#     monkeypatch.setattr(sut, "_maybe_read_guidance", reader, raising=True)
#     out = sut._build_tb_prompt("BODY")
#     # Order: guidelines → constructs → body; markers present
#     assert "[TESTBENCH GUIDELINES" in out and "<<BEGIN_TB_GUIDELINES>>" in out
#     assert "[TESTBENCH CONSTRUCTS" in out and "<<BEGIN_TB_CONSTRUCTS>>" in out
#     assert out.strip().endswith("BODY")

#     # No guidance at all
#     monkeypatch.setattr(sut, "_maybe_read_guidance", lambda *_: "", raising=True)
#     out2 = sut._build_tb_prompt("B2")
#     assert out2 == "B2"


# # ------------------------------
# # TBGenAgent.run / improve
# # ------------------------------

# def test_tbgenagent_run_happy_path(monkeypatch):
#     """
#     run(): formats composed prompt, invokes LLM, extracts clean TB code.
#     """
#     sut = _fresh_module()
#     # Keep composition deterministic (no file reads)
#     monkeypatch.setattr(
#         sut, "_tbgen_prompt_template",
#         DummyPrompt("S={spec};R={rtl_code};T={top_module_name}"),
#         raising=True,
#     )

#     # LLM returns fenced content
#     class R:
#         content = "```verilog\nmodule a_tb; endmodule\n```"

#     dummy = DummyLLM(R())
#     monkeypatch.setattr(sut.ModelSelector, "get_model", lambda **_: dummy, raising=True)

#     ag = sut.TBGenAgent(verbose=True)
#     out = ag.run("add", "rtl", "top")
#     # Prompt variables rendered
#     assert "S=add;R=rtl;T=top" in dummy.seen[0]
#     assert out.strip() == "module a_tb; endmodule"


# def test_tbgenagent_improve_happy_path(monkeypatch):
#     """
#     improve(): uses improve template and returns extracted TB code.
#     """
#     sut = _fresh_module()
#     monkeypatch.setattr(
#         sut, "_tbgen_improve_prompt_template",
#         DummyPrompt("S={spec};P={prev_tb_code};V={review};R={rtl_code};T={top_module_name}"),
#         raising=True,
#     )

#     class R:
#         content = "Here is the improved TB:\n```verilog\nmodule b_tb; endmodule\n```"

#     dummy = DummyLLM(R())
#     monkeypatch.setattr(sut.ModelSelector, "get_model", lambda **_: dummy, raising=True)

#     ag = sut.TBGenAgent()
#     out = ag.improve("s", "oldtb", "fix", "rtl", "top")
#     assert "S=s;P=oldtb;V=fix;R=rtl;T=top" in dummy.seen[0]
#     assert out.strip() == "module b_tb; endmodule"


# def test_tbgenagent_run_legacy_newline_fix(monkeypatch):
#     """
#     Legacy newline fix: if extractor returns only '\\n' (no real newline), agent unescapes.
#     We monkeypatch extractor to force that branch.
#     """
#     sut = _fresh_module()
#     monkeypatch.setattr(sut, "_tbgen_prompt_template", DummyPrompt("X={spec}"), raising=True)
#     # Force extractor to produce only escaped newlines
#     monkeypatch.setattr(sut, "extract_verilog_tb_code", lambda _raw: "module x;\\nendmodule", raising=True)
#     dummy = DummyLLM("ignored")
#     monkeypatch.setattr(sut.ModelSelector, "get_model", lambda **_: dummy, raising=True)

#     out = sut.TBGenAgent().run("s", "r", "t")
#     assert "module x;\nendmodule" in out


# def test_tbgenagent_improve_legacy_newline_fix(monkeypatch):
#     """
#     Same legacy unescape path for improve().
#     """
#     sut = _fresh_module()
#     monkeypatch.setattr(sut, "_tbgen_improve_prompt_template", DummyPrompt("X"), raising=True)
#     monkeypatch.setattr(sut, "extract_verilog_tb_code", lambda _raw: "module y;\\nendmodule", raising=True)
#     dummy = DummyLLM("ignored")
#     monkeypatch.setattr(sut.ModelSelector, "get_model", lambda **_: dummy, raising=True)

#     out = sut.TBGenAgent().improve("s", "p", "v", "r", "t")
#     assert "module y;\nendmodule" in out


# # ------------------------------
# # _invoke_llm branches
# # ------------------------------

# def test__invoke_llm_content_text_str_and_error(monkeypatch):
#     """
#     _invoke_llm prefers .content, then .text, else str(result). Exceptions are wrapped.
#     """
#     sut = _fresh_module()
#     agent = sut.TBGenAgent(llm=DummyLLM(types.SimpleNamespace(content="C")))

#     assert agent._invoke_llm("p1") == "C"        # .content
#     agent.llm = DummyLLM(types.SimpleNamespace(text="T"))
#     assert agent._invoke_llm("p2") == "T"        # .text
#     agent.llm = DummyLLM(object())
#     assert isinstance(agent._invoke_llm("p3"), str)  # str(result)

#     class Boom:
#         def invoke(self, _):  # noqa: D401
#             raise ValueError("boom")

#     agent.llm = Boom()
#     with pytest.raises(RuntimeError) as ei:
#         agent._invoke_llm("p4")
#     assert "LLM invocation failed in TBGenAgent" in str(ei.value)


# # ------------------------------
# # Tool wrappers
# # ------------------------------

# def test_tool_wrappers_call_agent(monkeypatch):
#     """
#     tbgen_tool / tbgen_improve_tool should instantiate TBGenAgent and delegate correctly.
#     """
#     sut = _fresh_module()
#     calls = {"run": [], "improve": []}

#     class FakeAgent:
#         def run(self, spec, rtl_code, top_module_name):  # noqa: D401
#             calls["run"].append((spec, rtl_code, top_module_name))
#             return "RUN"
#         def improve(self, spec, prev_tb_code, review, rtl_code, top_module_name):  # noqa: D401
#             calls["improve"].append((spec, prev_tb_code, review, rtl_code, top_module_name))
#             return "IMP"

#     # Lambdas in tool defs resolve TBGenAgent at call time (global lookup), so patch works.
#     monkeypatch.setattr(sut, "TBGenAgent", FakeAgent, raising=True)

#     assert sut.tbgen_tool.func("s", "r", "t") == "RUN"
#     assert sut.tbgen_improve_tool.func("s", "p", "v", "r", "t") == "IMP"
#     assert calls["run"] == [("s", "r", "t")]
#     assert calls["improve"] == [("s", "p", "v", "r", "t")]
