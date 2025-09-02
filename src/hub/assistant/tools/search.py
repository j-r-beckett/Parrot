from pydantic_ai import Agent
from pydantic_ai.tools import RunContext
from pydantic_ai.builtin_tools import WebSearchTool
from assistant.dependencies import AssistantDependencies
from assistant.tool_wrapper import safe_tool

# Search-specific system prompt
SEARCH_SYSTEM_PROMPT = """You are a web search assistant. Find accurate, current information and present it clearly.

SEARCH APPROACH:
1. Use web search to find reliable, authoritative sources
2. Look for recent, credible information
3. Cross-reference multiple sources when possible
4. Focus on factual, specific answers

RESPONSE FORMAT:
- Provide direct, factual answers
- Include specific numbers, dates, or data when relevant
- Keep responses concise but complete
- Don't include search process details or preambles
- Format information cleanly for easy reading"""

# Create the search sub-agent
search_agent = Agent(
    "anthropic:claude-sonnet-4-20250514",
    deps_type=type(None),  # No dependencies needed for search agent
    system_prompt=SEARCH_SYSTEM_PROMPT,
    builtin_tools=[WebSearchTool()]
)


def register_search_tool(agent: Agent[AssistantDependencies, str]) -> None:
    """Register search tool on the agent."""

    @agent.tool
    @safe_tool
    async def web_search(ctx: RunContext[AssistantDependencies], query: str) -> str:
        """Search the web for information by delegating to a specialized search agent."""
        ctx.deps.logger.info(f"Search tool called with query: {query}")
        
        # Delegate to the search sub-agent
        result = await search_agent.run(
            query,
            usage=ctx.usage  # Pass usage for tracking
        )
        
        ctx.deps.logger.info(f"Search sub-agent returned {len(result.output)} characters")
        ctx.deps.logger.info(f"Search result: {result.output}")
        
        return result.output