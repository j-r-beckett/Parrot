import os
from datetime import datetime
import pytz


def prompt(model: str, recent_interactions: str) -> str:
    """Load and return the system prompt from system_prompt.md with templating."""
    prompt_path = os.path.join(os.path.dirname(__file__), "system_prompt.md")
    with open(prompt_path, "r", encoding="utf-8") as f:
        content = f.read().strip()

    # Get current date in Central timezone
    central_tz = pytz.timezone("America/Chicago")
    now = datetime.now(central_tz)
    current_date = now.strftime("%A, %B %d, %Y")

    content = content.replace("{{model}}", model)
    content = content.replace("{{currentDate}}", current_date)
    content = content.replace("{{recent_conversations}}", recent_interactions)

    return content
