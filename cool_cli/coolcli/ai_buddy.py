# coolcli/ai_buddy.py

from saxoflow_agenticai.core.model_selector import ModelSelector
from saxoflow_agenticai.core.agent_manager import AgentManager

ACTION_KEYWORDS = {
    # Generation
    "generate rtl": "rtlgen",
    "rtlgen": "rtlgen",
    "generate testbench": "tbgen",
    "tbgen": "tbgen",
    "formal property": "fpropgen",
    "generate formal": "fpropgen",
    "sva": "fpropgen",
    # Simulation, Synthesis, etc.
    "simulate": "sim",
    "simulation": "sim",
    "synth": "synth",
    "synthesis": "synth",
    "debug": "debug",
    "report": "report",
    "pipeline": "fullpipeline",
    # Review
    "review rtl": "rtlreview",
    "check rtl": "rtlreview",
    "review testbench": "tbreview",
    "check testbench": "tbreview",
    "review formal": "fpropreview",
    "review property": "fpropreview",
    "check formal": "fpropreview",
}

def detect_action(message: str):
    """
    Returns (action, keyword) or (None, None) based on message content.
    """
    lowered = message.lower()
    for key, action in ACTION_KEYWORDS.items():
        if key in lowered:
            return action, key
    return None, None

def ask_ai_buddy(
    message, 
    history=None, 
    agent_type="buddy", 
    provider=None, 
    model=None,
    file_to_review=None  # Optional: code to review, for review actions
):
    """
    - Chat for general help
    - Guides & triggers generation actions
    - For review actions, runs review agent (if code provided)
    """
    action, matched = detect_action(message)
    # Handle review requests with direct agent call if file/code is present
    if action in {"rtlreview", "tbreview", "fpropreview"}:
        if not file_to_review:
            return {
                "type": "need_file",
                "message": (
                    f"Please provide the code/file to review for '{matched}'. "
                    "Paste the code or specify the path (e.g., 'review rtl mydesign.v')."
                )
            }
        # Call review agent
        review_agent = AgentManager.get_agent(action)
        review_result = review_agent.run(file_to_review)
        return {
            "type": "review_result",
            "action": action,
            "message": review_result
        }
    # Otherwise, normal chat logic
    llm = ModelSelector.get_model(agent_type=agent_type, provider=provider, model_name=model)
    # Format prompt
    prompt = ""
    if history:
        for turn in history[-5:]:
            prompt += f"User: {turn['user']}\nAssistant: {turn.get('assistant', '')}\n"
    prompt += (
        f"User: {message}\n"
        "Assistant: (Your answer should be factual and cite sources or link resources if possible. "
        "If the user asks for a design action (like generate RTL), first guide them through prerequisites. "
        "After the user confirms they are ready, respond ONLY with the string '__ACTION:{action}__' to trigger the tool.)"
    )
    response = llm.invoke(prompt)
    text = getattr(response, "content", None) or str(response)
    if action and f"__ACTION:{action}__" in text:
        return {"type": "action", "action": action, "message": text}
    else:
        return {"type": "chat", "message": text}
