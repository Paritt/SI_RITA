from langchain_core.tools import tool

@tool
def add(a: float, b: float) -> float:
  """Add two numbers"""
  """
  Args:
    a: The first number
    b: The second number

  Returns:
    The sum of the two numbers
  """
  return a + b

@tool
def multiply(a: float, b: float) -> float:
  """Multiply two numbers"""
  """
  Args:
    a: The first number
    b: The second number

  Returns:
    The product of the two numbers
  """
  return a * b

@tool
def subtract(a: float, b: float) -> float:
  """Subtract two numbers"""
  """
  Args:
    a: The first number
    b: The second number

  Returns:
    The difference of the two numbers
  """
  return a - b

@tool
def divide(a: float, b: float) -> float:
  """Divide two numbers"""
  """
  Args:
    a: The first number
    b: The second number

  Returns:
    The quotient of the two numbers
  """
  return a / b



tools = [add, multiply, subtract, divide]
available_functions = {tool.name: tool for tool in tools}