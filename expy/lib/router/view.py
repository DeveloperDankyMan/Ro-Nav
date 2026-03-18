# placeholder for future template rendering
import os
import re
import html

class ViewEngine:
    def __init__(self, base_path="views"):
        self.base_path = base_path

    def render(self, template_name, context=None):
        context = context or {}

        file_path = os.path.join(self.base_path, template_name)

        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Template '{template_name}' not found")

        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()

        # Replace {{ variable }} with escaped values
        def replace_var(match):
            key = match.group(1).strip()
            value = context.get(key, "")
            return html.escape(str(value))

        content = re.sub(r"{{\s*(.*?)\s*}}", replace_var, content)

        return content
