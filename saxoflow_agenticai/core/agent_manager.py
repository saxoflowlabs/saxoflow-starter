from saxoflow_agenticai.agents.generators.rtl_gen import RTLGenAgent
from saxoflow_agenticai.agents.generators.tb_gen import TBGenAgent
from saxoflow_agenticai.agents.generators.fprop_gen import FormalPropGenAgent
from saxoflow_agenticai.agents.generators.report_agent import ReportAgent

from saxoflow_agenticai.agents.reviewers.rtl_review import RTLReviewAgent
from saxoflow_agenticai.agents.reviewers.tb_review import TBReviewAgent
from saxoflow_agenticai.agents.reviewers.fprop_review import FormalPropReviewAgent
from saxoflow_agenticai.agents.reviewers.debug_agent import DebugAgent

from saxoflow_agenticai.core.model_selector import ModelSelector
from saxoflow_agenticai.core.llm_factory import get_llm_from_config  # You must implement this as above

class AgentManager:
    """
    Factory for agent instances by string key.
    Picks LLM from config if not supplied.
    Supported agent keys:
        - "rtlgen", "tbgen", "fpropgen", "report"
        - "rtlreview", "tbreview", "fpropreview", "debug"
    """
    AGENT_MAP = {
        "rtlgen": RTLGenAgent,
        "tbgen": TBGenAgent,
        "fpropgen": FormalPropGenAgent,
        "report": ReportAgent,
        "rtlreview": RTLReviewAgent,
        "tbreview": TBReviewAgent,
        "fpropreview": FormalPropReviewAgent,
        "debug": DebugAgent,
    }

    @staticmethod
    def get_agent(agent_name: str, verbose: bool = False, llm=None, **kwargs):
        """
        Retrieve an agent instance by name.
        If llm is not provided, loads correct LLM for agent_name from config.
        """
        cls = AgentManager.AGENT_MAP.get(agent_name)
        if not cls:
            raise ValueError(f"Unknown agent: {agent_name}")

        if llm is None:
            config = ModelSelector.load_config()
            llm = get_llm_from_config(agent_name, config)
        # log_to_file is not passed: all agents now use verbose+llm only
        agent = cls(verbose=verbose, llm=llm, **kwargs)
        return agent

    @staticmethod
    def all_agent_names():
        """Return all valid agent keys."""
        return list(AgentManager.AGENT_MAP.keys())
