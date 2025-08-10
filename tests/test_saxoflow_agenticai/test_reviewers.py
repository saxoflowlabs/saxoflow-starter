# """
# Tests for reviewer agents and extraction helpers.

# The review agents clean up and structure LLM feedback into well defined
# sections.  These tests feed representative raw outputs into the
# extractors and check that the resulting strings contain expected
# headings and that blank or missing sections default to "None".  We
# also stub out the LLM for the agents to test their fallback logic.
# """

# import re
# from unittest import mock

# from saxoflow_agenticai.agents.reviewers.rtl_review import extract_structured_rtl_review, RTLReviewAgent
# from saxoflow_agenticai.agents.reviewers.tb_review import extract_structured_review, TBReviewAgent
# from saxoflow_agenticai.agents.reviewers.fprop_review import extract_structured_formal_review, FormalPropReviewAgent
# from saxoflow_agenticai.agents.reviewers.debug_agent import extract_structured_debug_report, DebugAgent


# def test_extract_structured_rtl_review_formats_sections():
#     raw = """
#     Syntax Issues:
#     - none

#     Logic Issues:
#     - Use blocking assignments

#     Overall Comments:
#     Looks good
#     """
#     structured = extract_structured_rtl_review(raw)
#     # Each canonical heading should appear
#     assert "Syntax Issues:" in structured
#     assert "Logic Issues: Use blocking assignments" in structured
#     # Unknown headings should default to None
#     assert "Port Declaration Issues: None" in structured


# def test_extract_structured_tb_review_formats_sections():
#     raw = """
#     Instantiation Issues: Missing module instantiation
#     Coverage Gaps: none
#     Overall Comments: Good
#     """
#     structured = extract_structured_review(raw)
#     assert "Instantiation Issues: Missing module instantiation" in structured
#     # Non mentioned headings default to None
#     assert "Stimulus Issues: None" in structured
#     assert "Overall Comments: Good" in structured


# def test_extract_structured_formal_review_formats_sections():
#     raw = """
#     Missing Properties: none
#     Assertion Naming Suggestions: Use descriptive names
#     """
#     structured = extract_structured_formal_review(raw)
#     assert "Missing Properties: None" in structured
#     assert "Assertion Naming Suggestions: Use descriptive names" in structured
#     # Other headings default to None
#     assert "Scope & Coverage Issues: None" in structured


# def test_extract_structured_debug_report_formats_sections():
#     raw = """
#     Problems identified: unconnected port
#     Explanation: The port 'clk' is not driven.
#     Suggested Fixes: Connect the clock port.
#     Suggested Agent for Correction: RTLGenAgent
#     """
#     structured = extract_structured_debug_report(raw)
#     assert "Problems identified: unconnected port" in structured
#     assert "Suggested Agent for Correction: RTLGenAgent" in structured


# def test_reviewer_agents_with_stub(monkeypatch):
#     """Reviewer agents should return fallback text when LLM returns empty string."""
#     class DummyLLM:
#         def invoke(self, prompt):
#             return ""
#     # RTLReviewAgent
#     monkeypatch.setattr(RTLReviewAgent, "__init__", lambda self, llm=None, verbose=False: None)
#     agent = RTLReviewAgent()
#     agent.llm = DummyLLM()
#     review = agent.run("spec", "module m; endmodule")
#     assert "Syntax Issues: None" in review
#     # TBReviewAgent
#     monkeypatch.setattr(TBReviewAgent, "__init__", lambda self, llm=None, verbose=False: None)
#     tba = TBReviewAgent()
#     tba.llm = DummyLLM()
#     tbreview = tba.run("spec", "module m; endmodule", "m", "module tb; endmodule")
#     assert "Instantiation Issues" in tbreview
#     # FormalPropReviewAgent
#     monkeypatch.setattr(FormalPropReviewAgent, "__init__", lambda self, llm=None, verbose=False: None)
#     fpa = FormalPropReviewAgent()
#     fpa.llm = DummyLLM()
#     fprev = fpa.run("spec", "module m; endmodule", "property p; endproperty")
#     assert "Missing Properties" in fprev
#     # DebugAgent
#     monkeypatch.setattr(DebugAgent, "__init__", lambda self, llm=None, verbose=False: None)
#     dba = DebugAgent()
#     dba.llm = DummyLLM()
#     report, agents = dba.run("module m; endmodule", "module tb; endmodule")
#     assert isinstance(report, str)
#     assert agents == ["RTLGenAgent", "TBGenAgent"]


# def test_extractors_strip_markdown_and_metadata():
#     raw = """
#     ```verilog
#     module foo;
#     endmodule
#     ```
#     AIMessage(content=Some feedback)
#     Syntax Issues: None
#     Logic Issues: Use nonblocking
#     """
#     out = extract_structured_rtl_review(raw)
#     assert "AIMessage" not in out
#     assert "Syntax Issues:" in out
#     assert "Logic Issues: Use nonblocking" in out


# def test_headings_case_and_order():
#     raw = """
#     logic issues: some logic problem
#     Syntax Issues: something wrong
#     """
#     out = extract_structured_rtl_review(raw)
#     # Should be canonical order, case-insensitive match
#     lines = out.split("\n\n")
#     assert lines[0].startswith("Syntax Issues:")
#     assert lines[1].startswith("Logic Issues:")


# def test_duplicate_headings_and_extra_content():
#     raw = """
#     Syntax Issues: foo
#     Syntax Issues: bar
#     Logic Issues: one
#     Logic Issues: two
#     """
#     out = extract_structured_rtl_review(raw)
#     # Only the first occurrence should be used, or both merged; check non-empty, at least one is present
#     assert "Syntax Issues:" in out
#     assert "foo" in out or "bar" in out
#     assert "Logic Issues:" in out


# def test_extract_review_content_handles_dict():
#     # Used by agents for OpenAI format
#     result = {"content": "Syntax Issues: None"}
#     val = RTLReviewAgent.__init__  # Only type check, not execution
#     assert extract_structured_rtl_review(result["content"]).startswith("Syntax Issues:")


# def test_debug_agent_multiple_agents(monkeypatch):
#     class DummyLLM:
#         def invoke(self, prompt):
#             return (
#                 "Problems identified: foo\n"
#                 "Suggested Agent for Correction: RTLGenAgent, TBGenAgent"
#             )
#     monkeypatch.setattr(DebugAgent, "__init__", lambda self, llm=None, verbose=False: None)
#     agent = DebugAgent()
#     agent.llm = DummyLLM()
#     report, agents = agent.run("rtl", "tb")
#     assert "Problems identified: foo" in report
#     assert set(agents) == {"RTLGenAgent", "TBGenAgent"}


# def test_debug_agent_missing_agent(monkeypatch):
#     class DummyLLM:
#         def invoke(self, prompt):
#             return "Problems identified: foo"
#     monkeypatch.setattr(DebugAgent, "__init__", lambda self, llm=None, verbose=False: None)
#     agent = DebugAgent()
#     agent.llm = DummyLLM()
#     report, agents = agent.run("rtl", "tb")
#     assert "Problems identified: foo" in report
#     assert agents == ["RTLGenAgent", "TBGenAgent"]  # Fallback to default
