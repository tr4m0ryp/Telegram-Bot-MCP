"""MCP prompts for generating bot-facing content."""

from .app import mcp


@mcp.prompt()
def create_welcome_message(bot_name: str, features: str) -> str:
    """Create a personalized welcome message for the bot."""
    return (
        f'Create a warm, engaging welcome message for a Telegram bot named "{bot_name}".\n\n'
        f"The bot has these features: {features}\n\n"
        "The message should:\n"
        "- Be welcoming and friendly\n"
        "- Explain what the bot can do\n"
        "- Be formatted in HTML for Telegram\n"
        "- Include basic usage instructions\n\n"
        "Keep it concise but informative."
    )


@mcp.prompt()
def generate_help_content(available_commands: str) -> str:
    """Generate comprehensive help content for the bot."""
    return (
        "Create detailed help documentation for a Telegram bot with these commands: "
        f"{available_commands}\n\n"
        "The help content should:\n"
        "- List all available commands with descriptions\n"
        "- Provide usage examples\n"
        "- Include tips for effective use\n"
        "- Be well-formatted with HTML\n\n"
        "Make it comprehensive but easy to understand for users."
    )
