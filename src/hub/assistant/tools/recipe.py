from pydantic_ai import Agent
from pydantic_ai.tools import RunContext
from pydantic_ai.builtin_tools import WebSearchTool
from assistant.dependencies import AssistantDependencies
from assistant.tool_wrapper import safe_tool

# Recipe-specific system prompt
RECIPE_SYSTEM_PROMPT = """You are a recipe research assistant. Find recipes from reliable cooking sources. You should view multiple recipes in your search, but return the single reciple that best matches the query.

SEARCH PRIORITY:
1. Always start with Serious Eats
2. If no satisfactory results, expand to other well-known food sites: altonbrown.com, King Arthur Baking (for baking only), recipetineats.com

WHAT TO INCLUDE:
- Ingredients (reproduced verbatim from the original recipe)
- Directions (reproduced verbatim from the original recipe)  
- Total time (reproduced verbatim from the original recipe)
"""

# Create the recipe sub-agent
recipe_agent = Agent(
    "anthropic:claude-sonnet-4-20250514",
    deps_type=type(None),  # No dependencies needed for recipe agent
    system_prompt=RECIPE_SYSTEM_PROMPT,
    builtin_tools=[WebSearchTool()],
)


def register_recipe_tool(agent: Agent[AssistantDependencies, str]) -> None:
    """Register recipe tool on the agent."""

    @agent.tool
    @safe_tool
    async def get_recipe(ctx: RunContext[AssistantDependencies], prompt: str) -> str:
        """Get a recipe for a specific dish by delegating to a specialized recipe agent."""
        ctx.deps.logger.info(f"Recipe tool called with prompt: {prompt}")
        
        # Delegate to the recipe sub-agent
        result = await recipe_agent.run(
            prompt,
            usage=ctx.usage,  # Pass usage for tracking
        )
        
        ctx.deps.logger.info(f"Recipe sub-agent returned {len(result.output)} characters")
        ctx.deps.logger.info(f"Recipe result: {result.output}")
        
        return result.output
