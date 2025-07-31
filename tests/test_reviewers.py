"""
Tests for reviewer agents and extraction helpers.

The review agents clean up and structure LLM feedback into well defined
sections.  These tests feed representative raw outputs into the
extractors and check that the resulting strings contain expected
headings and that blank or missing sections default to "None".  We
also stub out the LLM for the agents to test their fallback logic.
"""

import re
from unittest import mock

from saxoflow_agenticai.agents.reviewers.rtl_review import extract_structured_rtl_review, RTLReviewAgent
from saxoflow_agenticai.agents.reviewers.tb_review import extract_structured_review, TBReviewAgent
from saxoflow_agenticai.agents.reviewers.fprop_review import extract_structured_formal_review, FormalPropReviewAgent
from saxoflow_agenticai.agents.reviewers.debug_agent import extract_structured_debug_report, DebugAgent


def test_extract_structured_rtl_review_formats_sections():
    raw = """
    Syntax Issues:
    - none

    Logic Issues:
    - Use blocking assignments

    Overall Comments:
    Looks good
    """
    structured = extract_structured_rtl_review(raw)
    # Each canonical heading should appear
    assert "Syntax Issues:" in structured
    assert "Logic Issues: Use blocking assignments" in structured
    # Unknown headings should default to None
    assert "Port Declaration Issues: None" in structured


def test_extract_structured_tb_review_formats_sections():
    raw = """
    Instantiation Issues: Missing module instantiation
    Coverage Gaps: none
    Overall Comments: Good
    """
    structured = extract_structured_review(raw)
    assert "Instantiation Issues: Missing module instantiation" in structured
    # Non mentioned headings default to None
    assert "Stimulus Issues: None" in structured
    assert "Overall Comments: Good" in structured


def test_extract_structured_formal_review_formats_sections():
    raw = """
    Missing Properties: none
    Assertion Naming Suggestions: Use descriptive names
    """
    structured = extract_structured_formal_review(raw)
    assert "Missing Properties: None" in structured
    assert "Assertion Naming Suggestions: Use descriptive names" in structured
    # Other headings default to None
    assert "Scope & Coverage Issues: None" in structured


def test_extract_structured_debug_report_formats_sections():
    raw = """
    Problems identified: unconnected port
    Explanation: The port 'clk' is not driven.
    Suggested Fixes: Connect the clock port.
    Suggested Agent for Correction: RTLGenAgent
    """
    structured = extract_structured_debug_report(raw)
    assert "Problems identified: unconnected port" in structured
    assert "Suggested Agent for Correction: RTLGenAgent" in structured


def test_reviewer_agents_with_stub(monkeypatch):
    """Reviewer agents should return fallback text when LLM returns empty string."""
    class DummyLLM:
        def invoke(self, prompt):
            return ""
    # RTLReviewAgent
    monkeypatch.setattr(RTLReviewAgent, "__init__", lambda self, llm=None, verbose=False: None)
    agent = RTLReviewAgent()
    agent.llm = DummyLLM()
    review = agent.run("spec", "module m; endmodule")
    assert "Syntax Issues: None" in review
    # TBReviewAgent
    monkeypatch.setattr(TBReviewAgent, "__init__", lambda self, llm=None, verbose=False: None)
    tba = TBReviewAgent()
    tba.llm = DummyLLM()
    tbreview = tba.run("spec", "module m; endmodule", "m", "module tb; endmodule")
    assert "Instantiation Issues" in tbreview
    # FormalPropReviewAgent
    monkeypatch.setattr(FormalPropReviewAgent, "__init__", lambda self, llm=None, verbose=False: None)
    fpa = FormalPropReviewAgent()
    fpa.llm = DummyLLM()
    fprev = fpa.run("spec", "module m; endmodule", "property p; endproperty")
    assert "Missing Properties" in fprev
    # DebugAgent
    monkeypatch.setattr(DebugAgent, "__init__", lambda self, llm=None, verbose=False: None)
    dba = DebugAgent()
    dba.llm = DummyLLM()
    report, agents = dba.run("module m; endmodule", "module tb; endmodule")
    assert isinstance(report, str)
    assert agents == ["RTLGenAgent", "TBGenAgent"]