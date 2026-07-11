from langchain_core.tools import tool
try:
    from raystation import *
except ModuleNotFoundError:
    print("Warning: 'raystation' module not found in raystation_tool.py. Patient-data tools will not work.")

@tool
def get_patient_name() -> str:
    """Get the current patient name"""
    patient = get_current("Patient")
    info = patient.Name
    return info

@tool
def get_patient_date_of_birth() -> str:
    """Get the current patient date of birth in day-month-year format"""
    patient = get_current("Patient")
    info = patient.DateOfBirth
    return f"Patient Date of Birth in day-month-year hh:mm:ss format: {info}"

@tool
def get_patient_gender() -> str:
    """Get the current patient gender"""
    patient = get_current("Patient")
    info = patient.Gender
    return f"Patient Gender: {info}"

@tool
def get_patient_id() -> str:
    """Get the current patient ID"""
    patient = get_current("Patient")
    info = patient.PatientID
    return info

tools = [get_patient_name, get_patient_date_of_birth, get_patient_gender, get_patient_id]
available_functions = {tool.name: tool for tool in tools}