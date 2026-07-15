from typing import Optional
from langchain_core.tools import tool
try:
    from connect import *
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

# ====================================================================
#  Planning tools
#  RayStation API usage adapted from the Pareto-Project scripts
#  (add_goal_funtion_and_optimize.py, export_clinical_goal_data.py).
# ====================================================================

# Function types handled by add_optimization_function, grouped by how their
# DoseFunctionParameters are set.
_DOSE_ONLY_TYPES = ("MaxDose", "MinDose", "UniformDose")
_DVH_TYPES = ("MaxDvh", "MinDvh")
_EUD_TYPES = ("MaxEud", "MinEud", "TargetEud")


def _goal_description(eval_func) -> str:
    """Human-readable one-line description of a clinical goal (e.g. 'Dmean <= 2600 cGy')."""
    pg = eval_func.PlanningGoal
    goal_type = pg.Type
    parameter = pg.ParameterValue
    acceptance = pg.PrimaryAcceptanceLevel
    criteria = pg.GoalCriteria
    sign = ">=" if criteria == "AtLeast" else "<=" if criteria == "AtMost" else "?"

    if goal_type == "AverageDose":
        return f"Dmean {sign} {acceptance:.0f} cGy"
    if goal_type == "DoseAtAbsoluteVolume":
        return f"D{parameter:.2f}cc {sign} {acceptance:.0f} cGy"
    if goal_type == "VolumeAtDose":
        return f"V{parameter:.0f}cGy {sign} {acceptance * 100:.1f}%"
    if goal_type == "DoseAtVolume":
        return f"D{parameter * 100:.1f}% {sign} {acceptance:.0f} cGy"
    if goal_type == "AbsoluteVolumeAtDose":
        return f"V{parameter:.0f}cGy {sign} {acceptance:.2f} cc"
    return f"{goal_type} {sign} {acceptance}"


def _is_goal_met(value: float, acceptance: float, criteria: str) -> bool:
    if criteria == "AtLeast":
        return value >= acceptance
    if criteria == "AtMost":
        return value <= acceptance
    return False


@tool
def add_optimization_function(
    roi_name: str,
    function_type: str,
    dose_cgy: float,
    volume_percent: Optional[float] = None,
    weight: float = 1.0,
    is_constraint: bool = False,
    is_absolute_volume: bool = False,
    eud_parameter_a: Optional[float] = None,
) -> str:
    """Add a new optimization objective or constraint function to an ROI in the current plan.

    Use this when the user wants to introduce a NEW planning goal for a structure —
    e.g. "add a max dose of 4000 cGy to the rectum" or "put a min dose objective on the PTV".

    Args:
        roi_name: Name of the ROI (target or organ-at-risk) the function applies to.
        function_type: One of 'MaxDose', 'MinDose', 'UniformDose', 'MaxDvh', 'MinDvh',
            'MaxEud', 'MinEud', 'TargetEud'.
        dose_cgy: Dose level for the function, in cGy.
        volume_percent: Volume for DVH-type functions (MaxDvh/MinDvh) — percent by default,
            or cc if is_absolute_volume is True. Ignored for other types.
        weight: Optimization weight / importance (higher = more emphasis). Ignored for constraints.
        is_constraint: True to add as a hard constraint instead of a weighted objective.
        is_absolute_volume: For DVH functions, interpret volume_percent as an absolute volume (cc).
        eud_parameter_a: The 'a' parameter for EUD-type functions (default 1).
    """
    try:
        plan = get_current("Plan")
        po = plan.PlanOptimizations[0]
        o = po.AddOptimizationFunction(
            FunctionType=function_type, RoiName=roi_name, IsConstraint=is_constraint
        )
        o.Tag = f"{roi_name}_{function_type}"
        p = o.DoseFunctionParameters

        if function_type in _DOSE_ONLY_TYPES:
            p.DoseLevel = dose_cgy
        elif function_type in _DVH_TYPES:
            p.DoseLevel = dose_cgy
            if is_absolute_volume:
                p.IsAbsoluteVolume = True
                p.AbsoluteVolume = volume_percent or 0
            else:
                p.IsAbsoluteVolume = False
                p.PercentVolume = volume_percent or 0
        elif function_type in _EUD_TYPES:
            p.DoseLevel = dose_cgy
            p.EudParameterA = eud_parameter_a if eud_parameter_a is not None else 1
        else:
            o.DeleteFunction()
            return (
                f"Unsupported function_type '{function_type}'. Supported: "
                f"{', '.join(_DOSE_ONLY_TYPES + _DVH_TYPES + _EUD_TYPES)}."
            )

        if not is_constraint:
            p.Weight = weight

        vol_note = "" if volume_percent is None or function_type not in _DVH_TYPES else (
            f" at {volume_percent}{'cc' if is_absolute_volume else '%'} volume"
        )
        kind = "constraint" if is_constraint else f"objective (weight={weight})"
        return f"Added {function_type} of {dose_cgy:.0f} cGy to '{roi_name}'{vol_note} as a {kind}."
    except Exception as e:
        return f"Error adding optimization function to '{roi_name}': {e}"


@tool
def adjust_optimization_function(
    roi_name: str,
    function_type: Optional[str] = None,
    dose_cgy: Optional[float] = None,
    volume_percent: Optional[float] = None,
    weight: Optional[float] = None,
) -> str:
    """Adjust an EXISTING optimization function on an ROI — change its dose, volume, or weight.

    Use this when the user wants to tweak a goal that already exists rather than add a new one —
    e.g. "lower the rectum max dose to 3800 cGy" or "increase the weight on the PTV min dose".
    Only the fields to change need to be provided; leave the rest empty to keep them unchanged.

    Args:
        roi_name: Name of the ROI whose optimization function should be adjusted.
        function_type: Which function type to adjust on that ROI (e.g. 'MaxDose'), needed only
            if the ROI has more than one optimization function.
        dose_cgy: New dose level in cGy, if changing it.
        volume_percent: New volume for DVH-type functions, if changing it.
        weight: New optimization weight, if changing it.
    """
    try:
        plan = get_current("Plan")
        po = plan.PlanOptimizations[0]

        matches = []
        for f in po.Objective.ConstituentFunctions:
            roi_obj = getattr(f, "ForRegionOfInterest", None)
            f_roi = getattr(roi_obj, "Name", "")
            params = getattr(f, "DoseFunctionParameters", None)
            f_type = getattr(params, "FunctionType", "")
            if f_roi == roi_name and (function_type is None or f_type == function_type):
                matches.append((f, params, f_type))

        if not matches:
            return f"No optimization function found on ROI '{roi_name}'" + (
                f" with type '{function_type}'." if function_type else "."
            )
        if len(matches) > 1:
            types = ", ".join(sorted({t for _, _, t in matches}))
            return (
                f"ROI '{roi_name}' has multiple optimization functions ({types}). "
                f"Specify function_type to choose which one to adjust."
            )

        _, params, f_type = matches[0]
        changed = []
        if dose_cgy is not None:
            params.DoseLevel = dose_cgy
            changed.append(f"dose={dose_cgy:.0f} cGy")
        if volume_percent is not None:
            if getattr(params, "IsAbsoluteVolume", False):
                params.AbsoluteVolume = volume_percent
            else:
                params.PercentVolume = volume_percent
            changed.append(f"volume={volume_percent}")
        if weight is not None:
            params.Weight = weight
            changed.append(f"weight={weight}")

        if not changed:
            return f"No changes specified for the {f_type} function on '{roi_name}'."
        return f"Adjusted {f_type} function on '{roi_name}': {', '.join(changed)}."
    except Exception as e:
        return f"Error adjusting optimization function on '{roi_name}': {e}"


@tool
def optimize_plan(reset_first: bool = False) -> str:
    """Run (or re-run) the optimization for the current plan using its defined objective functions.

    Use this AFTER adding or adjusting optimization functions, to actually compute/update the dose.

    Args:
        reset_first: If True, reset the optimization before running (start from scratch instead
            of continuing from the current result).
    """
    try:
        plan = get_current("Plan")
        po = plan.PlanOptimizations[0]
        if reset_first:
            po.ResetOptimization()
        po.RunOptimization()
        return "Optimization complete." + (" (reset before running)" if reset_first else "")
    except Exception as e:
        return f"Error running optimization: {e}"


@tool
def get_dose_statistics(roi_name: str, relative_volume_percent: Optional[float] = None) -> str:
    """Get dose statistics for an ROI from the current plan's dose.

    Use this to evaluate or report how the current dose looks for a structure — e.g.
    "what is the mean dose to the PTV" or "what is D95 of the rectum". Returns Dmin, Dmax, Dmean,
    and (if a relative volume is given) the dose at that volume (Dx%).

    Args:
        roi_name: Name of the ROI to compute statistics for.
        relative_volume_percent: Optional relative volume (%) at which to report dose
            (e.g. 95 for D95%). Leave empty for the overall min/max/mean statistics.
    """
    try:
        plan = get_current("Plan")
        dose = plan.TreatmentCourse.TotalDose
        d_min = dose.GetDoseStatistic(RoiName=roi_name, DoseType="Min")
        d_max = dose.GetDoseStatistic(RoiName=roi_name, DoseType="Max")
        d_mean = dose.GetDoseStatistic(RoiName=roi_name, DoseType="Average")
        result = (
            f"ROI '{roi_name}': Dmin={d_min:.1f} cGy, "
            f"Dmax={d_max:.1f} cGy, Dmean={d_mean:.1f} cGy"
        )
        if relative_volume_percent is not None:
            d_x = dose.GetDoseAtRelativeVolumes(
                RoiName=roi_name, RelativeVolumes=[relative_volume_percent / 100.0]
            )[0]
            result += f", D{relative_volume_percent:g}%={d_x:.1f} cGy"
        return result
    except Exception as e:
        return f"Error getting dose statistics for '{roi_name}': {e}"


@tool
def get_clinical_goals() -> str:
    """Read all clinical goals for the current plan and report each one's value and PASS/FAIL status.

    Use this when the user asks how the plan is doing against its clinical goals, which goals
    pass or fail, or to evaluate/review the current plan.
    """
    try:
        plan = get_current("Plan")
        eval_funcs = plan.TreatmentCourse.EvaluationSetup.EvaluationFunctions

        rows = []
        n_pass = 0
        for ef in eval_funcs:
            pg = ef.PlanningGoal
            roi_obj = getattr(ef, "ForRegionOfInterest", None)
            roi = getattr(roi_obj, "Name", "N/A")
            value = ef.GetClinicalGoalValue()
            met = _is_goal_met(value, pg.PrimaryAcceptanceLevel, pg.GoalCriteria)
            n_pass += 1 if met else 0
            rows.append((pg.Priority, roi, "PASS" if met else "FAIL",
                         _goal_description(ef), value))

        if not rows:
            return "No clinical goals are defined for the current plan."

        rows.sort(key=lambda r: (r[0], r[1]))
        lines = [
            f"[{status}] (P{priority}) {roi}: {desc}  — achieved {value:.2f}"
            for priority, roi, status, desc, value in rows
        ]
        header = f"Clinical goals: {n_pass}/{len(rows)} passing"
        return header + "\n" + "\n".join(lines)
    except Exception as e:
        return f"Error reading clinical goals: {e}"


@tool
def list_roi_names() -> str:
    """List the regions of interest (ROIs / structures) in the current patient's plan, with their type.

    Use this to discover the exact structure names before adding/adjusting optimization functions or
    getting dose statistics — e.g. when the user says "the rectum" you can confirm the ROI is named
    'Rectum'. Types indicate targets (Ptv/Ctv/Gtv) vs organs-at-risk (OrganAtRisk), etc.
    """
    try:
        ss = get_current("BeamSet").GetStructureSet()
        rows = [(g.OfRoi.Name, g.OfRoi.Type, g.HasContours()) for g in ss.RoiGeometries]
        lines = [f"- {n} ({t})" + ("" if c else "  [no contours]") for n, t, c in rows]
    except Exception:
        # Fall back to ROI definitions if no beam set / structure set is available.
        try:
            pm = get_current("Case").PatientModel
            lines = [f"- {r.Name} ({r.Type})" for r in pm.RegionsOfInterest]
        except Exception as e:
            return f"Error listing ROIs: {e}"
    if not lines:
        return "No ROIs found in the current case."
    return "ROIs in the current plan:\n" + "\n".join(lines)


@tool
def get_optimization_functions() -> str:
    """List the current plan's optimization functions with their parameters and current loss value.

    Use this to inspect the optimizer state and drive iterative tuning: functions with the HIGHEST
    loss are the ones contributing most error, so adjust those (via `adjust_optimization_function`)
    and re-run `optimize_plan`. Loss = the function's FunctionValue after the last optimization
    (higher = worse; call `optimize_plan` first if losses look stale). Functions are listed
    highest-loss first.
    """
    try:
        plan = get_current("Plan")
        po = plan.PlanOptimizations[0]
        items = list(po.Objective.ConstituentFunctions) + list(po.Constraints)
        if not items:
            return "No optimization functions are defined for the current plan."

        entries = []  # (loss_numeric_for_sort, text)
        for it in items:
            dp = getattr(it, "DoseFunctionParameters", None)
            ftype = getattr(dp, "FunctionType", "") or ""
            roi = getattr(getattr(it, "ForRegionOfInterest", None), "Name", "")
            dose = getattr(dp, "DoseLevel", "")
            weight = getattr(dp, "Weight", "")
            fv = getattr(getattr(it, "FunctionValue", None), "FunctionValue", None)

            vol = ""
            if ftype in ("MaxDvh", "MinDvh"):
                if getattr(dp, "IsAbsoluteVolume", False):
                    vol = f", {getattr(dp, 'AbsoluteVolume', '')}cc"
                else:
                    vol = f", {getattr(dp, 'PercentVolume', '')}%"

            loss_num = fv if isinstance(fv, (int, float)) else -1.0
            loss_str = f"{fv:.4g}" if isinstance(fv, (int, float)) else "N/A"
            entries.append((
                loss_num,
                f"- {roi}: {ftype} {dose} cGy{vol} (weight={weight}, loss={loss_str})",
            ))

        entries.sort(key=lambda e: e[0], reverse=True)
        return "Optimization functions (highest loss first):\n" + "\n".join(t for _, t in entries)
    except Exception as e:
        return f"Error reading optimization functions: {e}"


tools = [
    get_patient_name,
    get_patient_date_of_birth,
    get_patient_gender,
    get_patient_id,
    list_roi_names,
    add_optimization_function,
    adjust_optimization_function,
    optimize_plan,
    get_dose_statistics,
    get_optimization_functions,
    get_clinical_goals,
]
available_functions = {tool.name: tool for tool in tools}