# saxoflow_agenticai/core/prompt_manager.py
from jinja2 import Environment, FileSystemLoader, TemplateNotFound
import os

class PromptManager:
    def __init__(self, template_dir=None):
        """
        Initialize Jinja environment for prompt templates.
        :param template_dir: Optionally specify an explicit directory (for testing or custom setups).
        """
        if template_dir:
            self.template_dir = template_dir
        else:
            base_path = os.path.dirname(os.path.dirname(__file__))  # .../core/ -> .../
            self.template_dir = os.path.join(base_path, 'prompts')
        self.env = Environment(loader=FileSystemLoader(self.template_dir))

    def render(self, template_file, context):
        """
        Render the specified template with context.
        :param template_file: Name of the template file.
        :param context: Dictionary for prompt rendering.
        :return: Rendered string.
        """
        try:
            template = self.env.get_template(template_file)
            return template.render(context)
        except TemplateNotFound:
            raise FileNotFoundError(f"Prompt template '{template_file}' not found in '{self.template_dir}'.")

