import os


def prompt(model: str) -> str:
    """Load and return the system prompt from system_prompt.md with templating."""
    prompt_path = os.path.join(os.path.dirname(__file__), "system_prompt.md")
    with open(prompt_path, "r", encoding="utf-8") as f:
        content = f.read().strip()
    
    content = content.replace("{{model}}", model)
    
    return content