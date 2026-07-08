import sys
import os

# ── Path setup ──────────────────────────────────────────────────────
path = ".venv/lib/python3.9/site-packages"

def setupPath(path):
    """Set the path and environment"""
    sys.path.insert(0, path)
    os.environ["SCRIPT_PATH"] = path

setupPath(path)
# ────────────────────────────────────────────────────────────────────

from langchain_core.tools import tool
from raystation import *

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