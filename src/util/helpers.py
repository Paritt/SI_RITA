"""
RITA — Unified helper functions.

Merges everything from the old helping_function.py and v2_helpers.py into
one tidy module.  No LLM calls — only pure-Python + RayStation API utilities.

Sections:
  1. Ollama / LangChain format converters
  2. RayStation data readers  (clinical goals, objectives, ROI names)
  3. Target / OAR classification
  4. Clinical-goal parsing & prescription dose
  5. DVH computation & statistics
  6. ROI creation helpers
  7. High-loss filter (P0)
  8. P2: build adjust JSON from P1 text
"""
from __future__ import annotations  # allow "X | Y" annotations on Python 3.9

import os
import sys
import re
import csv
import json
import ast
import io
import math
import platform
from uuid import uuid4
from io import StringIO

# ── Path setup ──────────────────────────────────────────────────────
# path = ".venv/lib/python3.9/site-packages"

# def setupPath(target_path: str):
#     sys.path.insert(0, target_path)
#     os.environ["SCRIPT_PATH"] = target_path

# setupPath(path)

from typing import List, Any
from langchain_core.messages import AnyMessage, SystemMessage, HumanMessage, ToolMessage

try:
    from raystation import *
except ModuleNotFoundError:
    print("Warning: 'raystation' module not found in helpers.py. Patient-data features will not work.")


# ====================================================================
#  1. Ollama / LangChain format converters
# ====================================================================

def _to_ollama_messages(messages: List[AnyMessage]):
    """Convert LangChain messages to Ollama message dicts."""
    ollama_messages = []
    for message in messages:
        if isinstance(message, SystemMessage):
            role = "system"
        elif isinstance(message, HumanMessage):
            role = "user"
        elif isinstance(message, ToolMessage):
            role = "tool"
        else:
            role = "assistant"
        ollama_messages.append({"role": role, "content": message.content})
    return ollama_messages


def _to_langchain_tool_calls(ollama_tool_calls: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Convert Ollama-style tool_calls to LangChain AIMessage.tool_calls format."""
    normalized: list[dict[str, Any]] = []
    for call in ollama_tool_calls or []:
        function_block = call.get("function", {})
        args = function_block.get("arguments", {})
        if isinstance(args, str):
            try:
                args = json.loads(args)
            except Exception:
                try:
                    args = ast.literal_eval(args)
                except Exception:
                    args = {}
        if not isinstance(args, dict):
            args = {}
        normalized.append({
            "id": call.get("id", f"tool_call_{uuid4().hex[:8]}"),
            "name": function_block.get("name", ""),
            "args": args,
            "type": "tool_call",
        })
    return normalized


def _to_ollama_tools(langchain_tools: list[Any]) -> list[dict[str, Any]]:
    """Convert LangChain tool objects to Ollama tool schema."""
    ollama_tools: list[dict[str, Any]] = []
    for tool_obj in langchain_tools:
        parameters: dict[str, Any] = {
            "type": "object",
            "properties": {},
            "required": [],
        }
        args_schema = getattr(tool_obj, "args_schema", None)
        if args_schema is not None:
            try:
                parameters = args_schema.model_json_schema()
            except Exception:
                try:
                    parameters = args_schema.schema()
                except Exception:
                    pass
        ollama_tools.append({
            "type": "function",
            "function": {
                "name": getattr(tool_obj, "name", "unknown_tool"),
                "description": getattr(tool_obj, "description", "") or "",
                "parameters": parameters,
            },
        })
    return ollama_tools


# ====================================================================
#  2. RayStation data readers
# ====================================================================

def get_clinical_goal_summary() -> str:
    """Return a clinical goal summary in CSV format for the current RayStation plan.

    Columns: Priority, ROI Name, Clinical Goal, Clinical Goal Value, Result
    Result is one of: fulfilled, not fulfilled, N/A.
    """
    try:
        plan = get_current("Plan")
        print(plan)
        if plan is None:
            return "No plan is currently open in RayStation."

        evaluation_functions = plan.TreatmentCourse.EvaluationSetup.EvaluationFunctions
        x = len(evaluation_functions)
        print(f"Number of evaluation functions: {x}")
        rows = []
        for i in range(x):
            try:
                ef = evaluation_functions[i]
                goal_type = ef.PlanningGoal.Type
                priority = ef.PlanningGoal.Priority
                roi_name = ef.ForRegionOfInterest.Name

                if goal_type == "DoseAtAbsoluteVolume":
                    
                    clinical_goal = (
                        f"{ef.PlanningGoal.GoalCriteria} "
                        f"{round(ef.PlanningGoal.PrimaryAcceptanceLevel)} cGy (RBE) dose at "
                        f"{round(ef.PlanningGoal.ParameterValue, 2)} cm\u00b3 volume"
                    )
                    
                    try:
                        clinical_goal_value_string = f"{round(ef.GetClinicalGoalValue())} cGy (RBE)"
                        result = "fulfilled" if ef.EvaluateClinicalGoal(EvaluateUsingSecondaryAcceptanceLevelIfExists=False) else "not fulfilled"
                    except Exception:
                        clinical_goal_value_string = "Not calculate yet"
                        result = "N/A"

                elif goal_type == "DoseAtVolume":
                    clinical_goal = (
                        f"{ef.PlanningGoal.GoalCriteria} "
                        f"{round(ef.PlanningGoal.PrimaryAcceptanceLevel)} cGy (RBE) dose at "
                        f"{round(ef.PlanningGoal.ParameterValue * 100, 2)} % volume"
                    )
                    try:
                        clinical_goal_value_string = f"{round(ef.GetClinicalGoalValue())} cGy (RBE)"
                        result = "fulfilled" if ef.EvaluateClinicalGoal(EvaluateUsingSecondaryAcceptanceLevelIfExists=False) else "not fulfilled"
                    except Exception:
                        clinical_goal_value_string = "Not calculate yet"
                        result = "N/A"

                elif goal_type == "AverageDose":
                    clinical_goal = (
                        f"{ef.PlanningGoal.GoalCriteria} "
                        f"{round(ef.PlanningGoal.PrimaryAcceptanceLevel)} cGy (RBE) average dose"
                    )
                    try:
                        clinical_goal_value_string = f"{round(ef.GetClinicalGoalValue())} cGy (RBE)"
                        result = "fulfilled" if ef.EvaluateClinicalGoal(EvaluateUsingSecondaryAcceptanceLevelIfExists=False) else "not fulfilled"
                    except Exception:
                        clinical_goal_value_string = "Not calculate yet"
                        result = "N/A"

                elif goal_type == "VolumeAtDose":
                    clinical_goal = (
                        f"{ef.PlanningGoal.GoalCriteria} "
                        f"{round(ef.PlanningGoal.PrimaryAcceptanceLevel * 100, 2)} % volume at "
                        f"{round(ef.PlanningGoal.ParameterValue)} cGy (RBE) dose"
                    )
                    try:
                        clinical_goal_value_string = f"{round(ef.GetClinicalGoalValue() * 100, 4)} %"
                        result = "fulfilled" if ef.EvaluateClinicalGoal(EvaluateUsingSecondaryAcceptanceLevelIfExists=False) else "not fulfilled"
                    except Exception:
                        clinical_goal_value_string = "Not calculate yet"
                        result = "N/A"

                elif goal_type == "AbsoluteVolumeAtDose":
                    clinical_goal = (
                        f"{ef.PlanningGoal.GoalCriteria} "
                        f"{round(ef.PlanningGoal.PrimaryAcceptanceLevel, 2)} cm\u00b3 volume at "
                        f"{round(ef.PlanningGoal.ParameterValue)} cGy (RBE) dose"
                    )
                    try:
                        clinical_goal_value_string = f"{round(ef.GetClinicalGoalValue(), 4)} cm\u00b3 "
                        result = "fulfilled" if ef.EvaluateClinicalGoal(EvaluateUsingSecondaryAcceptanceLevelIfExists=False) else "not fulfilled"
                    except Exception:
                        clinical_goal_value_string = "Not calculate yet"
                        result = "N/A"

                elif goal_type == "ConformityIndex":
                    clinical_goal = (
                        f"{ef.PlanningGoal.GoalCriteria} a conformity index of "
                        f"{round(ef.PlanningGoal.PrimaryAcceptanceLevel, 2)} at "
                        f"{round(ef.PlanningGoal.ParameterValue)} cGy (RBE) isodose"
                    )
                    clinical_goal_value_string = "N/A"
                    result = "N/A"

                elif goal_type == "HomogeneityIndex":
                    clinical_goal = (
                        f"{ef.PlanningGoal.GoalCriteria} a homogeneity index of "
                        f"{round(ef.PlanningGoal.PrimaryAcceptanceLevel, 2)} at "
                        f"{round(ef.PlanningGoal.ParameterValue * 100, 2)} % volume"
                    )
                    clinical_goal_value_string = "N/A"
                    result = "N/A"

                else:
                    priority = "N/A"
                    roi_name = "N/A"
                    clinical_goal = "unknown clinical goal"
                    clinical_goal_value_string = "N/A"
                    result = "N/A"

                rows.append((priority, roi_name, clinical_goal, clinical_goal_value_string, result))
            except Exception:
                pass

        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["Priority", "ROI Name", "Clinical Goal", "Clinical Goal Value", "Result"])
        writer.writerows(rows)
        return str(output.getvalue().strip())
    except Exception as e:
        return f"Error accessing RayStation: {str(e)}"


def _safe_getattr(obj, attr_name, default=None):
    return getattr(obj, attr_name, default)


def _build_row(item, item_kind):
    dose_params = _safe_getattr(item, "DoseFunctionParameters", None)
    function_type = _safe_getattr(dose_params, "FunctionType", "")

    if not function_type and _safe_getattr(dose_params, "PercentStdDeviation", None) is not None:
        function_type = "UniformityConstraint"
    elif not function_type and _safe_getattr(dose_params, "HighDoseLevel", None) is not None:
        function_type = "DoseFallOff"

    row = {
        "item_kind": item_kind,
        "tag": _safe_getattr(item, "Tag", ""),
        "roi": _safe_getattr(_safe_getattr(item, "ForRegionOfInterest", None), "Name", ""),
        "function_type": function_type,
        "dose_level_cgy": _safe_getattr(dose_params, "DoseLevel", ""),
        "volume_value": "",
        "volume_unit": "",
        "eud_parameter_a": "",
        "high_dose_level_cgy": _safe_getattr(dose_params, "HighDoseLevel", ""),
        "low_dose_level_cgy": _safe_getattr(dose_params, "LowDoseLevel", ""),
        "low_dose_distance_cm": _safe_getattr(dose_params, "LowDoseDistance", ""),
        "uniformity_percent_std_deviation": _safe_getattr(dose_params, "PercentStdDeviation", ""),
        "weight": _safe_getattr(dose_params, "Weight", ""),
        "function_value": _safe_getattr(
            _safe_getattr(item, "FunctionValue", None), "FunctionValue", "N/A"
        ),
    }

    if function_type in ("MaxDvh", "MinDvh"):
        is_absolute_volume = _safe_getattr(dose_params, "IsAbsoluteVolume", False)
        if is_absolute_volume:
            row["volume_value"] = _safe_getattr(dose_params, "AbsoluteVolume", "")
            row["volume_unit"] = "cc"
        else:
            row["volume_value"] = _safe_getattr(dose_params, "PercentVolume", "")
            row["volume_unit"] = "%"
    elif function_type in ("MaxEud", "MinEud", "TargetEud", "MexEud"):
        row["eud_parameter_a"] = _safe_getattr(dose_params, "EudParameterA", "")

    return row


def get_current_objectives_state() -> str:
    """Return current optimizer objectives/constraints as CSV text."""
    plan = get_current("Plan")
    po = plan.PlanOptimizations[0]

    fieldnames = [
        "item_kind", "tag", "roi", "function_type",
        "dose_level_cgy", "volume_value", "volume_unit",
        "eud_parameter_a", "high_dose_level_cgy",
        "low_dose_level_cgy", "low_dose_distance_cm",
        "uniformity_percent_std_deviation", "weight", "function_value",
    ]

    output = StringIO()
    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()

    for objective in po.Objective.ConstituentFunctions:
        writer.writerow(_build_row(objective, "objective"))
    for constraint in po.Constraints:
        writer.writerow(_build_row(constraint, "constraint"))

    return output.getvalue()


def get_all_roi_names() -> str:
    """Get the names of all ROIs in the current plan (as a string list)."""
    plan = get_current("Plan")
    if plan is None:
        return "No plan is currently open in RayStation."
    ss = plan.BeamSets[0].GetStructureSet()
    roi_names = [r.OfRoi.Name for r in ss.RoiGeometries]
    return str(roi_names)


# ====================================================================
#  3. Target / OAR classification
# ====================================================================

def is_target_roi(roi_name: str) -> bool:
    """Return True if the ROI is a target (PTV, CTV, ITV, GTV)."""
    bs = get_current("BeamSet")
    ss = bs.GetStructureSet()
    try:
        roi_type = ss.RoiGeometries[roi_name].OfRoi.Type
        return roi_type.lower() in ("ptv", "ctv", "itv", "gtv")
    except Exception:
        return False


# ====================================================================
#  4. Clinical-goal parsing & prescription dose
# ====================================================================

_GOAL_RE = {
    "DoseAtVolume": re.compile(
        r"(AtLeast|AtMost)\s+([\d.]+)\s+cGy.*?dose\s+at\s+([\d.]+)\s+%\s+volume"
    ),
    "DoseAtAbsoluteVolume": re.compile(
        r"(AtLeast|AtMost)\s+([\d.]+)\s+cGy.*?dose\s+at\s+([\d.]+)\s+cm"
    ),
    "VolumeAtDose": re.compile(
        r"(AtLeast|AtMost)\s+([\d.]+)\s+%\s+volume\s+at\s+([\d.]+)\s+cGy"
    ),
    "AbsoluteVolumeAtDose": re.compile(
        r"(AtLeast|AtMost)\s+([\d.]+)\s+cm.*?volume\s+at\s+([\d.]+)\s+cGy"
    ),
    "AverageDose": re.compile(
        r"(AtLeast|AtMost)\s+([\d.]+)\s+cGy.*?average\s+dose"
    ),
}


def _parse_goal_text(text: str) -> dict | None:
    """Parse a clinical goal text string into structured fields."""
    for goal_type in [
        "DoseAtAbsoluteVolume", "DoseAtVolume",
        "AbsoluteVolumeAtDose", "VolumeAtDose",
        "AverageDose",
    ]:
        m = _GOAL_RE[goal_type].search(text)
        if not m:
            continue

        criteria = m.group(1)

        if goal_type == "DoseAtVolume":
            return {"goal_type": goal_type, "criteria": criteria,
                    "dose_value_cgy": float(m.group(2)),
                    "volume_percent": float(m.group(3)), "volume_cc": None}
        elif goal_type == "DoseAtAbsoluteVolume":
            return {"goal_type": goal_type, "criteria": criteria,
                    "dose_value_cgy": float(m.group(2)),
                    "volume_percent": None, "volume_cc": float(m.group(3))}
        elif goal_type == "VolumeAtDose":
            return {"goal_type": goal_type, "criteria": criteria,
                    "dose_value_cgy": float(m.group(3)),
                    "volume_percent": float(m.group(2)), "volume_cc": None}
        elif goal_type == "AbsoluteVolumeAtDose":
            return {"goal_type": goal_type, "criteria": criteria,
                    "dose_value_cgy": float(m.group(3)),
                    "volume_percent": None, "volume_cc": float(m.group(2))}
        elif goal_type == "AverageDose":
            return {"goal_type": goal_type, "criteria": criteria,
                    "dose_value_cgy": float(m.group(2)),
                    "volume_percent": None, "volume_cc": None}
    return None


def get_clinical_goals_structured() -> list[dict]:
    """Parse clinical goals CSV into a list of structured dicts.

    Each dict: priority, roi_name, goal_type, criteria, dose_value_cgy,
               volume_percent, volume_cc, is_target, current_value, result
    """
    csv_text = get_clinical_goal_summary()
    reader = csv.DictReader(StringIO(csv_text))
    goals = []
    for row in reader:
        roi_name = row.get("ROI Name", "").strip()
        goal_text = row.get("Clinical Goal", "")
        result = row.get("Result", "").strip()

        if "conformity index" in goal_text.lower() or "homogeneity index" in goal_text.lower():
            continue

        parsed = _parse_goal_text(goal_text)
        if parsed is None:
            continue

        goals.append({
            "priority": int(row.get("Priority", 99)),
            "roi_name": roi_name,
            "goal_type": parsed["goal_type"],
            "criteria": parsed["criteria"],
            "dose_value_cgy": parsed["dose_value_cgy"],
            "volume_percent": parsed["volume_percent"],
            "volume_cc": parsed["volume_cc"],
            "is_target": is_target_roi(roi_name),
            "current_value": row.get("Clinical Goal Value", "").strip(),
            "result": result,
        })
    return goals


def extract_prescription_dose(goals: list[dict]) -> int:
    """Return the prescription dose in cGy."""
    bs = get_current("BeamSet")
    return int(round(bs.Prescription.PrimaryPrescriptionDoseReference.DoseValue))


# ====================================================================
#  5. DVH computation & statistics
# ====================================================================

def _get_clinical_goal_roi_names() -> list[str]:
    """Extract unique ROI names from the clinical goals of the current plan."""
    plan = get_current("Plan")
    eval_funcs = plan.TreatmentCourse.EvaluationSetup.EvaluationFunctions
    seen = set()
    roi_names = []
    for ef in eval_funcs:
        try:
            name = ef.ForRegionOfInterest.Name
            if name not in seen:
                seen.add(name)
                roi_names.append(name)
        except Exception:
            pass
    return roi_names


def _compute_cumulative_dvh(plan_dose, roi_voxel_indices, bin_size: int) -> list[tuple[int, float]]:
    """Compute cumulative DVH as list of (dose_cGy, volume_pct) tuples."""
    roi_dose = [plan_dose[vi] for vi in roi_voxel_indices]
    total_voxels = len(roi_dose)
    if total_voxels == 0:
        return []

    num_of_bins = int(math.ceil(max(plan_dose) / bin_size))
    differential_dvh = [0] * num_of_bins
    for rd in roi_dose:
        bin_number = int(rd / bin_size)
        if bin_number >= num_of_bins:
            bin_number = num_of_bins - 1
        differential_dvh[bin_number] += 1

    cumulative_dvh = [0.0] * num_of_bins
    running_sum = 0
    for i in range(num_of_bins - 1, -1, -1):
        running_sum += differential_dvh[i]
        cumulative_dvh[i] = (running_sum / total_voxels) * 100.0

    return [(i * bin_size, cumulative_dvh[i]) for i in range(num_of_bins)]


def _dvh_statistics(plan, roi_name: str) -> dict:
    """Derive key DVH statistics: Dmin, Dmax, Dmean, D2, D50, D95, D98 (cGy)."""
    d_avg = round(plan.TreatmentCourse.TotalDose.GetDoseStatistic(RoiName=roi_name,DoseType="Average"),2)
    d_min = round(plan.TreatmentCourse.TotalDose.GetDoseStatistic(RoiName=roi_name,DoseType="Min"),2)
    d_max = round(plan.TreatmentCourse.TotalDose.GetDoseStatistic(RoiName=roi_name,DoseType="Max"),2)
    d_2, d_50, d_95, d_98 = [round(d, 2) for d in plan.TreatmentCourse.TotalDose.GetDoseAtRelativeVolumes(RoiName=roi_name,RelativeVolumes=[0.02,0.5,0.95,0.98])]

    return {
        "Dmin": d_min,
        "Dmax": d_max,
        "Dmean": d_avg,
        "D2": d_2,
        "D50": d_50,
        "D95": d_95,
        "D98": d_98,
    }
    
# NOTE: stray module-level scratch code removed — it ran at import time against a
# hardcoded ROI ('PTV_4140') and would crash unless that exact plan was open.
# plan = get_current('Plan')
# d_avg = round(plan.TreatmentCourse.TotalDose.GetDoseStatistic(RoiName='PTV_4140',DoseType="Average"),2)
# d_min = round(plan.TreatmentCourse.TotalDose.GetDoseStatistic(RoiName='PTV_4140',DoseType="Min"),2)
# d_max = round(plan.TreatmentCourse.TotalDose.GetDoseStatistic(RoiName='PTV_4140',DoseType="Max"),2)
# d_2, d_50, d_95, d_98 = [round(d, 2) for d in plan.TreatmentCourse.TotalDose.GetDoseAtRelativeVolumes(RoiName='PTV_4140',RelativeVolumes=[0.02,0.5,0.95,0.98])]

_STAT_RE = re.compile(
    r"Dmin=([\d.]+).*?Dmax=([\d.]+).*?Dmean=([\d.]+)"
    r".*?D98=([\d.]+).*?D95=([\d.]+).*?D50=([\d.]+).*?D2=([\d.]+)",
    re.DOTALL,
)


def parse_dvh_stats_text(stats_text: str) -> dict[str, dict]:
    """Parse the text output of get_dvh_summary() into {roi: {stat: value}}."""
    result = {}
    current_roi = None
    for line in stats_text.splitlines():
        line = line.strip()
        if line.startswith("## "):
            current_roi = line[3:].strip()
        elif current_roi:
            m = _STAT_RE.search(line)
            if m:
                result[current_roi] = {
                    "Dmin": float(m.group(1)), "Dmax": float(m.group(2)),
                    "Dmean": float(m.group(3)), "D98": float(m.group(4)),
                    "D95": float(m.group(5)), "D50": float(m.group(6)),
                    "D2": float(m.group(7)),
                }
    return result


def get_dvh_summary(bin_size: int = 50) -> str:
    """Compute cumulative DVH for all clinical-goal ROIs and return a text summary."""
    plan = get_current("Plan")
    roi_names = _get_clinical_goal_roi_names()

    if platform.python_implementation() == "IronPython":
        plan_dose = [d for d in plan.TreatmentCourse.TotalDose.DoseValues.DoseData]
    else:
        plan_dose = plan.TreatmentCourse.TotalDose.DoseValues.DoseData.flatten()

    sections = []
    for roi in roi_names:
        try:
            dgr = plan.TreatmentCourse.TotalDose.GetDoseGridRoi(RoiName=roi)
            voxel_indices = dgr.RoiVolumeDistribution.VoxelIndices
            roi_dose = [plan_dose[vi] for vi in voxel_indices]
        except Exception as e:
            sections.append(f"## {roi}\nError: {e}")
            continue

        if not roi_dose:
            sections.append(f"## {roi}\nNo dose data available.")
            continue

        dvh = _compute_cumulative_dvh(plan_dose, voxel_indices, bin_size)
        stats = _dvh_statistics(plan, roi)

        lines = [f"## {roi}"]
        lines.append(f"Dmin={stats['Dmin']} cGy | Dmax={stats['Dmax']} cGy | Dmean={stats['Dmean']} cGy")
        lines.append(f"D98={stats['D98']} cGy | D95={stats['D95']} cGy | D50={stats['D50']} cGy | D2={stats['D2']} cGy")
        lines.append("Cumulative DVH (Dose[cGy] -> Volume[%]):")
        for dose_cGy, vol_pct in dvh:
            if vol_pct < 0.01:
                break
            lines.append(f"  {dose_cGy:>5d} cGy -> {vol_pct:6.2f}%")
        sections.append("\n".join(lines))

    if not sections:
        return "No clinical-goal ROIs found or no dose computed."
    return "# DVH Summary for Clinical-Goal ROIs\n" + "\n\n".join(sections)


# New function: output cumulative DVH for a specific ROI
def get_dvh_for_roi(roi_name: str, bin_size: int = 50) -> str:
    """Compute cumulative DVH for a specific ROI and return a text summary."""
    plan = get_current("Plan")
    if plan is None:
        return "No plan is currently open in RayStation."

    if platform.python_implementation() == "IronPython":
        plan_dose = [d for d in plan.TreatmentCourse.TotalDose.DoseValues.DoseData]
    else:
        plan_dose = plan.TreatmentCourse.TotalDose.DoseValues.DoseData.flatten()

    try:
        dgr = plan.TreatmentCourse.TotalDose.GetDoseGridRoi(RoiName=roi_name)
        voxel_indices = dgr.RoiVolumeDistribution.VoxelIndices
        roi_dose = [plan_dose[vi] for vi in voxel_indices]
    except Exception as e:
        return f"## {roi_name}\nError: {e}"

    if not roi_dose:
        return f"## {roi_name}\nNo dose data available."

    dvh = _compute_cumulative_dvh(plan_dose, voxel_indices, bin_size)
    stats = _dvh_statistics(plan, roi_name)

    lines = [f"## {roi_name}"]
    lines.append(f"Dmin={stats['Dmin']} cGy | Dmax={stats['Dmax']} cGy | Dmean={stats['Dmean']} cGy")
    lines.append(f"D98={stats['D98']} cGy | D95={stats['D95']} cGy | D50={stats['D50']} cGy | D2={stats['D2']} cGy")
    lines.append("Cumulative DVH (Dose[cGy] -> Volume[%]):")
    for dose_cGy, vol_pct in dvh:
        if vol_pct < 0.01:
            break
        lines.append(f"  {dose_cGy:>5d} cGy -> {vol_pct:6.2f}%")
    return "\n".join(lines)


# ====================================================================
#  6. ROI creation helpers
# ====================================================================

def find_body_roi_name(roi_names_str: str) -> str:
    """Find the Body or External ROI from a ROI name list string."""
    try:
        names = ast.literal_eval(roi_names_str)
    except Exception:
        names = []

    for name in names:
        if name.lower() in ("external", "body"):
            return name
    for name in names:
        if "body" in name.lower() or "external" in name.lower():
            return name
    return "Body"


def create_body_minus_target_roi(
    body_roi_name: str,
    target_roi_name: str,
    margin_cm: float = 0.3,
) -> str:
    """Create Body-[Target]+margin ROI via RayStation algebra. Returns new ROI name."""
    case = get_current("Case")
    examination = get_current("Examination")
    new_name = f"Body-{target_roi_name}+{margin_cm}"

    try:
        roi = case.PatientModel.RegionsOfInterest[new_name]
    except Exception:
        roi = case.PatientModel.CreateRoi(
            Name=new_name, Color="White", Type="Control",
            TissueName=None, RbeCellTypeName=None, RoiMaterial=None,
        )

    _zero = {
        "Type": "Expand",
        "Superior": 0, "Inferior": 0,
        "Anterior": 0, "Posterior": 0,
        "Right": 0, "Left": 0,
    }

    roi.CreateAlgebraGeometry(
        Examination=examination, Algorithm="Auto",
        ExpressionA={
            "Operation": "Union",
            "SourceRoiNames": [body_roi_name],
            "MarginSettings": _zero,
        },
        ExpressionB={
            "Operation": "Union",
            "SourceRoiNames": [target_roi_name],
            "MarginSettings": {
                "Type": "Expand",
                "Superior": margin_cm, "Inferior": margin_cm,
                "Anterior": margin_cm, "Posterior": margin_cm,
                "Right": margin_cm, "Left": margin_cm,
            },
        },
        ResultOperation="Subtraction",
        ResultMarginSettings=_zero,
    )
    return new_name


def parse_dose_from_roi_name(roi_name: str) -> int | None:
    """Extract prescription dose in cGy from a ROI name.

    Rules (applied in order):
      1. 'cgy' anywhere in the name  → adjacent number is already in cGy.
      2. 'gy' (but not 'cgy') in name → adjacent number is in Gy, multiply ×100.
      3. No unit found → inspect all number tokens:
           4-digit number  → treat as cGy
           ≤2-digit number → treat as Gy (×100)
           3-digit ignored (ambiguous).
    Returns None if no dose can be confidently determined.
    """
    name_lower = roi_name.lower()

    # Rule 1 — explicit cGy
    if "cgy" in name_lower:
        m = re.search(r"(\d+)\s*cgy", name_lower)
        if m:
            return int(m.group(1))
        # number anywhere in name (fallback)
        m = re.search(r"(\d+)", roi_name)
        if m:
            return int(m.group(1))

    # Rule 2 — explicit Gy (but not cGy)
    elif "gy" in name_lower:
        m = re.search(r"(\d+)\s*gy", name_lower)
        if m:
            return int(m.group(1)) * 100

    # Rule 3 — no unit: guess from digit count
    else:
        for num_str in re.findall(r"\d+", roi_name):
            n = int(num_str)
            if len(num_str) == 4 and n > 0:
                return n              # e.g. 6000 → 6000 cGy
            if len(num_str) <= 2 and n > 0:
                return n * 100        # e.g. 60 → 6000 cGy

    return None


def create_target_nooverlap_roi(
    target_roi: str,
    higher_targets: list[str],
    margin_cm: float = 0.3,
) -> str:
    """Create '{target_roi}_OvlpFree' = target minus (union of higher_targets + margin).

    The resulting ROI covers only the non-overlapping portion of the target,
    so optimizer functions placed on it do not conflict with higher-dose regions.
    Name includes the parent target so the P1 LLM can link it to clinical goals.
    """
    case = get_current("Case")
    examination = get_current("Examination")
    new_name = f"{target_roi}_OvlpFree"

    try:
        roi = case.PatientModel.RegionsOfInterest[new_name]
    except Exception:
        roi = case.PatientModel.CreateRoi(
            Name=new_name, Color="Yellow", Type="Control",
            TissueName=None, RbeCellTypeName=None, RoiMaterial=None,
        )

    _zero = {
        "Type": "Expand",
        "Superior": 0, "Inferior": 0,
        "Anterior": 0, "Posterior": 0,
        "Right": 0, "Left": 0,
    }
    _margin = {
        "Type": "Expand",
        "Superior": margin_cm, "Inferior": margin_cm,
        "Anterior": margin_cm, "Posterior": margin_cm,
        "Right": margin_cm, "Left": margin_cm,
    }

    roi.CreateAlgebraGeometry(
        Examination=examination, Algorithm="Auto",
        ExpressionA={
            "Operation": "Union",
            "SourceRoiNames": [target_roi],
            "MarginSettings": _zero,
        },
        ExpressionB={
            "Operation": "Union",
            "SourceRoiNames": higher_targets,
            "MarginSettings": _margin,
        },
        ResultOperation="Subtraction",
        ResultMarginSettings=_zero,
    )
    return new_name


# ====================================================================
#  7. High-loss filter (P0)
# ====================================================================

def filter_high_loss_functions(objectives_csv: str) -> str:
    """Return human-readable summary of high-loss (fv > 1e-5) functions.

    Returns "ALL_SATISFIED" if nothing exceeds the threshold.
    """
    reader = csv.DictReader(StringIO(objectives_csv))
    lines = []
    for row in reader:
        fv_raw = row.get("function_value", "N/A").strip()
        if fv_raw in ("N/A", ""):
            continue
        try:
            fv = float(fv_raw)
        except ValueError:
            continue
        if fv <= 1e-5:
            continue

        roi = row.get("roi", "")
        role = "TARGET" if is_target_roi(roi) else "OAR"
        detail_parts = [
            f"tag={row.get('tag', '')}",
            f"roi={roi} ({role})",
            f"function_type={row.get('function_type', '')}",
            f"function_value={fv:.4e}",
        ]
        for col in [
            "dose_level_cgy", "volume_value", "volume_unit",
            "eud_parameter_a", "high_dose_level_cgy",
            "low_dose_level_cgy", "low_dose_distance_cm", "weight",
        ]:
            val = row.get(col, "").strip()
            if val:
                detail_parts.append(f"{col}={val}")
        lines.append(", ".join(detail_parts))

    return "\n".join(lines) if lines else "ALL_SATISFIED"


# ====================================================================
#  8. P2: build adjust JSON from P1 text
# ====================================================================

_ADJUST_SCHEMA = {
    "MaxDose":     ["function_type", "tag", "dose_level", "weight", "is_constraint"],
    "MinDose":     ["function_type", "tag", "dose_level", "weight", "is_constraint"],
    "MaxDvh":      ["function_type", "tag", "dose_level", "is_absolute_volume", "volume_value", "weight", "is_constraint"],
    "MinDvh":      ["function_type", "tag", "dose_level", "is_absolute_volume", "volume_value", "weight", "is_constraint"],
    "MaxEud":      ["function_type", "tag", "dose_level", "eud_parameter_a", "weight", "is_constraint"],
    "MinEud":      ["function_type", "tag", "dose_level", "eud_parameter_a", "weight", "is_constraint"],
    "TargetEud":   ["function_type", "tag", "dose_level", "eud_parameter_a", "weight", "is_constraint"],
    "UniformDose": ["function_type", "tag", "dose_level", "weight", "is_constraint"],
    "DoseFallOff": ["function_type", "tag", "high_dose_level", "low_dose_level", "low_dose_distance", "weight", "is_constraint"],
}

_CSV_TO_JSON = {
    "dose_level_cgy": "dose_level",
    "volume_value": "volume_value",
    "volume_unit": None,
    "eud_parameter_a": "eud_parameter_a",
    "high_dose_level_cgy": "high_dose_level",
    "low_dose_level_cgy": "low_dose_level",
    "low_dose_distance_cm": "low_dose_distance",
    "weight": "weight",
}

_JSON_TO_CSV = {v: k for k, v in _CSV_TO_JSON.items() if v is not None}


def _normalize_change_key(key: str) -> str:
    """Normalize a parameter name to the canonical JSON field name."""
    key = key.strip().lower()
    alias = {
        "dose_level_cgy": "dose_level",
        "high_dose_level_cgy": "high_dose_level",
        "low_dose_level_cgy": "low_dose_level",
        "low_dose_distance_cm": "low_dose_distance",
    }
    return alias.get(key, key)


def _parse_p1_lines(p1_text: str) -> list[tuple[str, str, dict]]:
    """Parse P1 plain-text into list of (tag, function_type, changes_dict).

    Tolerates markdown bullets, numbering, extra whitespace, blank lines.
    """
    results = []
    for raw_line in p1_text.strip().splitlines():
        line = raw_line.strip()
        if not line:
            continue
        line = re.sub(r"^[\-\*>#]\s*", "", line)
        line = re.sub(r"^\d+[.)]\s*", "", line)
        line = line.strip()

        if "|" not in line:
            continue
        parts = [p.strip() for p in line.split("|")]
        if len(parts) < 3:
            continue

        tag = parts[0].strip()
        func_type = parts[1].strip()
        if not tag or not func_type:
            continue

        changes: dict[str, str] = {}
        for kv in parts[2].split(","):
            kv = kv.strip()
            if "=" not in kv:
                continue
            k, v = kv.split("=", 1)
            changes[_normalize_change_key(k)] = v.strip()

        results.append((tag, func_type, changes))
    return results


def build_adjust_json(p1_text: str, objectives_csv: str, auto_tighten_zero_oar: bool = True) -> dict:
    """Parse P1 plain-text + current objectives CSV → adjust_function JSON.

    Parameters
    ----------
    auto_tighten_zero_oar : bool
        If True, OAR objectives with function_value==0.0 that P1 did not
        mention are automatically tightened by 20%.  Set False to disable.
    """
    reader = csv.DictReader(StringIO(objectives_csv))
    current: dict[str, dict] = {}
    for row in reader:
        current[row.get("tag", "")] = row

    parsed_lines = _parse_p1_lines(p1_text)

    ZERO_VALUE_OVERSHOOT = 0.2  # 20% extra tightening for functions with function_value==0.00
    adjust_list = []
    adjusted_tags = set()
    # 1. Build adjustments from P1 output (with overshoot logic)
    for tag, func_type, changes in parsed_lines:
        row = current.get(tag, {})
        if not row:
            print(f"[P2][WARN] tag '{tag}' not found in current objectives — skipping.")
            continue

        entry: dict = {"function_type": func_type, "tag": tag}
        adjusted_tags.add(tag)

        schema = _ADJUST_SCHEMA.get(func_type, [])
        if not schema:
            print(f"[P2][WARN] unknown function_type '{func_type}' for tag '{tag}' — skipping.")
            continue

        for field in schema:
            if field in ("function_type", "tag"):
                continue
            if field == "is_constraint":
                entry["is_constraint"] = (row.get("item_kind", "objective").strip().lower() == "constraint")
                continue
            if field == "is_absolute_volume":
                entry["is_absolute_volume"] = (row.get("volume_unit", "%").strip().lower() == "cc")
                continue

            csv_col = _JSON_TO_CSV.get(field, field)

            if field in changes:
                entry[field] = _safe_float(changes[field])
            elif csv_col in row and row[csv_col].strip():
                entry[field] = _safe_float(row[csv_col])

        adjust_list.append(entry)

    # 2. For all OARs with function_value==0.00 not already adjusted, add auto-tighten adjustment
    if not auto_tighten_zero_oar:
        return {
            "add_function": [],
            "adjust_function": adjust_list,
            "delete_function": [],
            "num_optimization_time": 2,
        }

    for tag, row in current.items():
        if tag in adjusted_tags:
            continue
        is_oar = not is_target_roi(row.get("roi", ""))
        fv_raw = row.get("function_value", "N/A")
        try:
            fv = float(fv_raw)
        except Exception:
            fv = None
        if not is_oar or fv != 0.0:
            continue
        func_type = row.get("function_type", "")
        schema = _ADJUST_SCHEMA.get(func_type, [])
        if not schema:
            continue
        entry = {"function_type": func_type, "tag": tag}
        for field in schema:
            if field in ("function_type", "tag"):
                continue
            if field == "is_constraint":
                entry["is_constraint"] = (row.get("item_kind", "objective").strip().lower() == "constraint")
                continue
            if field == "is_absolute_volume":
                entry["is_absolute_volume"] = (row.get("volume_unit", "%").strip().lower() == "cc")
                continue
            csv_col = _JSON_TO_CSV.get(field, field)
            val = row.get(csv_col, "")
            try:
                val_f = float(val)
            except Exception:
                continue
            # Always tighten by OVERSHOOT%
            if field in ("dose_level", "high_dose_level", "low_dose_level", "volume_value"):
                val_f = val_f * (1 - ZERO_VALUE_OVERSHOOT)
            entry[field] = round(val_f, 2)
        adjust_list.append(entry)

    return {
        "add_function": [],
        "adjust_function": adjust_list,
        "delete_function": [],
        "num_optimization_time": 2,
    }


def _safe_float(val) -> float:
    """Convert to float, returning 0.0 on failure."""
    try:
        return float(val)
    except (ValueError, TypeError):
        return 0.0
