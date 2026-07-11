from langchain_core.tools import tool

@tool
def count_characters(s: str) -> int:
    """Count the number of characters in a string"""
    """
    Args:
        s: The string to count

    Returns:
        The number of characters in the string
    """
    return len(s)

@tool
def get_current_time() -> str:
    """Get the current date and time"""
    """
    Returns:
        The current date and time as a string
    """
    from datetime import datetime
    year = datetime.now().year
    month = datetime.now().month
    day = datetime.now().day
    time = datetime.now().time().isoformat()
    weekday = datetime.now().strftime("%A")
    return f"Current date (YYYY-MM-DD) Weekday and time: {year}-{month:02d}-{day:02d} ({weekday}) {time}"


tools = [count_characters, get_current_time]
available_functions = {tool.name: tool for tool in tools}