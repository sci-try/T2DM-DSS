import json
import sys

# ======================
# Country configuration
# ======================

COUNTRIES = {
    "TR": {"frc": True, "label": "Turkey", "tr_bmi_threshold": 35},
    "IQ": {"frc": True, "label": "Iraq"},
}

# Glucose: mmol/L → mg/dL (clinical conversion for FPG gate)
FPG_MMOL_TO_MG_DL = 18.018

# ──────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────

def boolv(x):
    if isinstance(x, bool):
        return x
    if x is None:
        return False
    if isinstance(x, (int, float)):
        return x != 0
    if isinstance(x, str):
        s = x.strip().lower()
        if s in {"true", "1", "yes", "y", "on"}:
            return True
        if s in {"false", "0", "no", "n", "off", "", "none", "null"}:
            return False
    return bool(x)


def num(x):
    try:
        return float(x)
    except Exception:
        return None


def fpg_mg_dl_from_inputs(inputs):
    """Return FPG in mg/dL, or None if not provided. Converts mmol/L using FPG_MMOL_TO_MG_DL."""
    raw = num(inputs.get("fpg"))
    if raw is None:
        return None
    unit = str(inputs.get("fpg_unit") or "mg_dl").strip().lower().replace(" ", "")
    if unit in ("mmol_l", "mmol/l", "mmol"):
        return raw * FPG_MMOL_TO_MG_DL
    return raw


def add_tr_frc_reimbursement_note(country, profile, bmi, comments):
    if country == "TR" and bmi is not None and bmi < profile.get("tr_bmi_threshold", 35):
        comments.append(
            "Turkey: reimbursement for FRC may be limited when BMI < 35; "
            "treatment may be out-of-pocket depending on local access conditions."
        )


# ══════════════════════════════════════════════════════════════════════════════
#  IRAQ STANDING NOTES
# ══════════════════════════════════════════════════════════════════════════════

IQ_GLP1_NOTE = (
    "GLP-1 RA choice should be guided by patient-specific considerations: "
    "established CVD, CKD, desired weight benefit, access and cost (affordability)."
)
IQ_BI_NOTE = (
    "Basal insulin: 2nd-generation basal insulins (e.g. degludec, glargine U-300) "
    "are preferred over older generations due to lower hypoglycaemia risk."
)
IQ_PREMIX_NOTE = (
    "\u266f Complex insulin regimens (such as premix insulins) may be used as "
    "alternatives if other options are not accessible locally."
)
IQ_IRREGULAR_MEALS_NOTE = (
    "Irregular meal patterns: premixed insulin is not recommended; prefer "
    "fixed-ratio combination (FRC) strategies where applicable."
)
IQ_SIMPLE_REGIMEN_NOTE = (
    "Simpler regimens are prioritised before complex insulin strategies."
)
IQ_BI_SECOND_GEN_ELDERLY_CKD = (
    "Prefer 2nd-generation basal insulins especially in elderly and CKD "
    "patients (lower hypoglycaemia risk)."
)
IQ_FRC_IRAQ_PRAGMATIC = (
    "In Iraq, FRC provides a pragmatic and simplified way to deliver "
    "GLP-1 RA therapy."
)
IQ_COMPLEX_INSULIN_RESERVED = (
    "Complex insulin regimens (premix or basal-bolus) should be reserved for "
    "cases where simpler strategies fail or are unavailable."
)
IQ_FRC_IRAQ_MOST_FEASIBLE = (
    "In Iraq, FRC provides the most feasible access to GLP-1 RA therapy."
)
IQ_BE_AWARE_PREMIX = (
    "! Be aware!: Premix agents cause higher hypoglycaemia risk, require "
    "regular meals with greater rigidity, which can reduce adherence compared "
    "with simpler schedules."
)
IQ_MONOTHERAPY_LA_UNAVAILABLE = (
    "(When monotherapy LA GLP-1 RA is not accessible, or not tolerated.)"
)

IQ_THERAPY_BASAL_FIRST = (
    "Start basal insulin & titration — 2nd-generation basal, titrate up to "
    "0.5 U/kg/day"
)
IQ_THERAPY_BASAL_FIRST_BMI_UNKNOWN = IQ_THERAPY_BASAL_FIRST + " (BMI unknown)"
IQ_THERAPY_BASAL_FIRST_PENDING_LABS = IQ_THERAPY_BASAL_FIRST + " (pending laboratory confirmation)"


def _iq_la_glp1_available(inputs):
    """
    True when monotherapy long-acting GLP-1 RA is available (`iq_glp1_ra_access`).
    FRC (basal + GLP-1 fixed-ratio) is not gated by this flag — assumed feasible.
    """
    v = inputs.get("iq_glp1_ra_access")
    if v is None:
        return False
    if isinstance(v, str) and v.strip() == "":
        return False
    return boolv(v)


def _iq_base_comments(irregular_meal_patterns_yes):
    """
    Standing Iraq footnotes. FRC assumed available — use FRC-preferring irregular note.
    """
    out = [IQ_GLP1_NOTE, IQ_BI_NOTE]
    if irregular_meal_patterns_yes:
        out.append(IQ_IRREGULAR_MEALS_NOTE)
    else:
        out.append(IQ_PREMIX_NOTE)
    return out


# ══════════════════════════════════════════════════════════════════════════════
#  IRAQ ALGORITHM
# ══════════════════════════════════════════════════════════════════════════════

def _above_target_str(diff):
    """
    Human-readable description of how far HbA1c is above target.
    Uses 'above target' language — no 'gap' terminology.
    """
    return f"HbA1c is {diff:.1f}% above target"


def _recommend_iq(inputs, diff, bmi, target_unmet, comments):
    """
    Iraq-specific routing.
    `diff`         – float or None  (hba1c − effective_target)
    `bmi`          – float or None
    `target_unmet` – bool
    `comments`     – list (extended here with standing Iraq footnotes)
    """

    on_basal_only    = boolv(inputs.get("on_basal_only"))
    on_glp1_alone    = boolv(inputs.get("on_glp1_alone"))
    on_bi_glp1       = boolv(inputs.get("on_bi_glp1"))
    on_bi_glp1_rapid = boolv(inputs.get("on_bi_glp1_rapid"))
    on_bb            = boolv(inputs.get("on_basal_bolus"))
    on_premix        = boolv(inputs.get("on_premix"))
    irregular        = boolv(inputs.get("irregular_meal_patterns"))
    la_ok            = _iq_la_glp1_available(inputs)

    comments.extend(_iq_base_comments(irregular))

    def result(therapy, why, next_steps):
        return {
            "therapy": therapy,
            "why": why,
            "next_steps": next_steps,
            "comments": comments,
        }

    # ── Step 3: BI(max)+GLP-1+Rapid still unmet ─────────────────────────────
    if on_bi_glp1_rapid and target_unmet:
        why_core = [
            "HbA1c target remains unmet on BI (max dose) + GLP-1 RA "
            "+ rapid-acting insulin.",
            "Optimise basal–bolus with GLP-1 RA component; prioritise adherence "
            "and technique before further complexity (Iraq algorithm step 3).",
            "If HbA1c and/or postprandial glucose control remain inadequate, "
            "work systematically on adherence (meals–injection alignment, "
            "SMBG/CGM linkage, education, follow-up cadence).",
        ]
        if irregular:
            why_irr = why_core + [
                "Irregular meal patterns: premixed insulin is not recommended.",
            ]
            return result(
                therapy="Continue / optimise basal-bolus with GLP-1 RA; address adherence",
                why=why_irr,
                next_steps=[
                    "Optimise basal dose and stepwise rapid-acting insulin before "
                    "each main meal as appropriate.",
                    "Reassess HbA1c in 3 months after regimen optimisation.",
                    "Ensure structured SMBG or CGM where available.",
                    "If HbA1c or prandial control is still inadequate, address "
                    "adherence barriers before escalating complexity.",
                ],
            )
        return result(
            therapy="Continue / optimise basal-bolus with GLP-1 RA; address adherence",
            why=why_core,
            next_steps=[
                "Optimise basal dose and stepwise rapid-acting insulin before "
                "each main meal as appropriate.",
                "Reassess HbA1c in 3 months after regimen optimisation.",
                "Ensure structured SMBG or CGM where available.",
                "If HbA1c or prandial control is still inadequate, address "
                "adherence barriers before escalating complexity.",
            ],
        )

    # ── Step 2: BI+GLP-1 still unmet → add rapid ───────────────────────────
    if on_bi_glp1 and target_unmet:
        why_rapid = [
            "HbA1c target remains unmet on BI + GLP-1 RA combination.",
            "Iraq algorithm: intensify by maximising basal insulin dose "
            "and adding rapid-acting insulin.",
        ]
        ns_rapid = [
            "Titrate basal insulin to its maximum tolerated / labelled dose.",
            "Add rapid-acting insulin starting with the largest meal "
            "(basal-plus approach); stepwise addition to further meals as needed.",
            "Titrate prandial dose on postprandial glucose readings.",
            "Reassess HbA1c in 3 months.",
        ]
        if not la_ok:
            why_rapid.append(
                "Because monotherapy LA GLP-1 RA is not accessible, continue GLP-1 RA "
                "delivery via FRC and treat this step as stepwise prandial coverage."
            )
        return result(
            therapy="BI (max dose) + GLP-1 RA + Rapid-acting insulin",
            why=why_rapid,
            next_steps=ns_rapid,
        )

    # ── GLP-1 alone unmet → BI + GLP-1 RA first (then rapid on next step) ───
    if on_glp1_alone and target_unmet:
        if not la_ok:
            why_g = [
                "HbA1c target remains unmet on GLP-1 RA monotherapy.",
                "Monotherapy LA GLP-1 RA is not available for routing; escalate using "
                "fixed-ratio combination (FRC), assumed available.",
            ]
            if irregular:
                why_g.append(
                    "Irregular meal patterns: premixed insulin is not recommended."
                )
            return result(
                therapy="BI + GLP-1 RA (FRC)",
                why=why_g,
                next_steps=[
                    "Switch to FRC (basal + GLP-1 fixed ratio) per local label.",
                    IQ_MONOTHERAPY_LA_UNAVAILABLE,
                    "Titrate according to local label and glucose response.",
                    "Reassess HbA1c in 3 months; if still above target, escalate to "
                    "BI (max dose) + GLP-1 RA + rapid-acting insulin.",
                ],
            )
        return result(
            therapy="BI + GLP-1 RA (FRC or separately)",
            why=[
                "HbA1c target remains unmet on GLP-1 RA monotherapy.",
                "Iraq algorithm: escalate to BI + GLP-1 RA before adding "
                "prandial rapid-acting insulin; FRC or separate injections "
                "(no preference enforced). Basal insulin can be added alongside "
                "continued GLP-1 RA injections, or switching to FRC is an equivalent lane.",
            ],
            next_steps=[
                "Option A — Add basal insulin alongside continued separate GLP-1 RA injections.",
                "Option B — Switch to FRC (basal + GLP-1 fixed ratio) where suitable.",
                "Titrate according to local label and glucose response.",
                "Reassess HbA1c in 3 months; if still above target, escalate to "
                "BI (max dose) + GLP-1 RA + rapid-acting insulin.",
            ],
        )

    # ── Step 1: basal-only still unmet → BI + GLP-1 RA ──────────────────────
    if on_basal_only and target_unmet:
        why_base = []
        ns_ladd = []

        def _failure_lead_sentence():
            if bmi is not None and bmi <= 30:
                return (
                    "HbA1c target remains unmet on basal insulin alone despite "
                    "maximal titration."
                )
            return (
                "HbA1c target remains unmet on basal insulin alone despite "
                "appropriate titration."
            )

        if not la_ok:
            why_base = [
                _failure_lead_sentence(),
                "Monotherapy LA GLP-1 RA not used for access routing; "
                "escalate via FRC (assumed available).",
            ]
            if irregular:
                why_base.append(
                    "Irregular meal patterns: premixed insulin is not recommended."
                )
            ns_ladd = [
                "Switch to or initiate FRC (basal + GLP-1 fixed ratio).",
                IQ_MONOTHERAPY_LA_UNAVAILABLE,
                "Titrate according to local label and glucose response.",
                "Reassess HbA1c in 3 months.",
            ]
            return result(
                therapy="BI + GLP-1 RA (FRC)",
                why=why_base,
                next_steps=ns_ladd,
            )

        why_base = [
            _failure_lead_sentence(),
            "Iraq algorithm: escalate to BI + GLP-1 RA combination; FRC or "
            "separate injections (no preference enforced).",
        ]
        if bmi is not None and bmi > 30:
            why_base.append(
                "BMI and weight considerations favor GLP-1 RA–based combinations."
            )
        return result(
            therapy="BI + GLP-1 RA (FRC or separately)",
            why=why_base,
            next_steps=[
                "Option A — Switch to FRC (basal + GLP-1 fixed ratio) where suitable.",
                "Option B — Add GLP-1 RA as a separate injection alongside "
                "current basal insulin.",
                "Titrate according to local label and glucose response.",
                "Reassess HbA1c in 3 months.",
            ],
        )

    # ── First injectable — diff-based ────────────────────────────────────────
    if diff is not None:

        # HbA1c less than 2% above target
        if diff < 2.0:

            if bmi is not None and bmi <= 30:
                ns_basal = [
                    "Titrate to fasting glucose target.",
                ]
                if la_ok:
                    ns_basal.append(
                        "Reassess HbA1c in 3 months; if still above target, escalate to "
                        "BI + GLP-1 RA (FRC or separately)."
                    )
                else:
                    ns_basal.append(
                        "Reassess HbA1c in 3 months; if still above target, escalate to "
                        "BI + GLP-1 RA via FRC (monotherapy LA GLP-1 RA not required)."
                    )
                return result(
                    therapy=IQ_THERAPY_BASAL_FIRST,
                    why=[
                        _above_target_str(diff) + ", which is less than 2% above target.",
                        "BMI \u2264 30 kg/m\u00b2: basal insulin is the recommended "
                        "first injectable (Iraq algorithm, step 0).",
                        IQ_SIMPLE_REGIMEN_NOTE,
                        IQ_BI_SECOND_GEN_ELDERLY_CKD,
                    ],
                    next_steps=ns_basal,
                )

            if bmi is not None and bmi > 30:
                if not la_ok:
                    return result(
                        therapy="Start BI + GLP-1 RA (FRC)",
                        why=[
                            _above_target_str(diff) + ", which is less than 2% above target.",
                            "BMI > 30 kg/m\u00b2: without monotherapy LA GLP-1 RA access, "
                            "initiate combined BI + GLP-1 RA via FRC (Iraq algorithm, step 0).",
                            IQ_FRC_IRAQ_PRAGMATIC,
                        ],
                        next_steps=[
                            "Initiate BI + GLP-1 RA via FRC per local label; "
                            "titrate to fasting and overall glycaemic targets.",
                            "Reassess HbA1c in 3 months; escalate per algorithm if needed.",
                        ],
                    )
                why_glp1 = [
                    _above_target_str(diff) + ", which is less than 2% above target.",
                    "BMI > 30 kg/m\u00b2: GLP-1 RA monotherapy is preferred first; "
                    "escalate GLP-1 RA and add basal insulin toward prandial coverage as needed; "
                    "without monotherapy LA access the pathway would be FRC then stepwise "
                    "rapid-acting insulin (Iraq algorithm, step 0).",
                    "BMI and weight considerations favor GLP-1 RA–based combinations.",
                    IQ_FRC_IRAQ_PRAGMATIC,
                    IQ_COMPLEX_INSULIN_RESERVED,
                ]
                if irregular:
                    why_glp1.append(
                        "Irregular meal patterns: prioritise meal-structured strategies; "
                        "premix is not recommended at this step."
                    )
                return result(
                    therapy="Start GLP-1 RA monotherapy OR Start BI + GLP-1 RA (FRC or separately)",
                    why=why_glp1,
                    next_steps=[
                        "First choice: start GLP-1 RA monotherapy; titrate per label.",
                        "If still uncontrolled — add basal insulin or start FRC.",
                        "Reassess HbA1c in 3 months; if still above target, escalate "
                        "to BI (max) + GLP-1 RA + rapid-acting insulin.",
                    ],
                )

            # BMI unknown
            comments.append(
                "BMI not provided; conservative basal-insulin-first choice used."
                + (
                    " If BMI > 30, GLP-1 RA monotherapy (with monotherapy LA access) or "
                    "BI + GLP-1 RA (FRC or separately) may be preferred."
                    if la_ok
                    else " If BMI > 30, initiate BI + GLP-1 RA via FRC when monotherapy "
                    "LA GLP-1 RA is unavailable; confirm BMI and access."
                )
            )
            return result(
                therapy=IQ_THERAPY_BASAL_FIRST_BMI_UNKNOWN,
                why=[
                    _above_target_str(diff) + ", which is less than 2% above target.",
                    "BMI is unavailable; conservative basal-insulin-first approach used.",
                    IQ_SIMPLE_REGIMEN_NOTE,
                    IQ_BI_SECOND_GEN_ELDERLY_CKD,
                ],
                next_steps=[
                    "Confirm BMI to refine the choice.",
                    "Titrate to fasting glucose target.",
                    "Reassess HbA1c in 3 months.",
                ],
            )

        # HbA1c 2% or more above target

        if bmi is not None and bmi <= 30:
            if not la_ok:
                if irregular:
                    return result(
                        therapy="Start BI + GLP-1 RA (FRC)",
                        why=[
                            _above_target_str(diff) + ", which is 2% or more above target.",
                            "BMI \u2264 30 kg/m\u00b2: combination BI + GLP-1 RA is recommended "
                            "from initiation (Iraq algorithm, step 0).",
                            "Monotherapy LA GLP-1 RA not used for routing; "
                            "FRC is the incretin-containing option (assumed available).",
                            "Irregular meal patterns: premix agents are not recommended.",
                        ],
                        next_steps=[
                            "Start BI + GLP-1 RA via FRC — typically once daily from a single pen.",
                            "Reassess HbA1c in 3 months; if still above target, escalate "
                            "to BI (max) + GLP-1 RA + rapid-acting insulin.",
                        ],
                    )
                return result(
                    therapy="Start BI + GLP-1 RA (FRC)",
                    why=[
                        _above_target_str(diff) + ", which is 2% or more above target.",
                        "BMI \u2264 30 kg/m\u00b2: generally BI + GLP-1 RA via FRC is recommended "
                        "from initiation (Iraq algorithm, step 0).",
                        "Monotherapy LA GLP-1 RA not used for routing; "
                        "FRC delivers GLP-1 RA with basal insulin in one pathway.",
                    ],
                    next_steps=[
                        "Start BI + GLP-1 RA via FRC — typically once daily from a single pen.",
                        "Premix may be used if FRC is not available.",
                        "Reassess HbA1c in 3 months; if still above target, escalate "
                        "to BI (max) + GLP-1 RA + rapid-acting insulin.",
                    ],
                )
            if irregular:
                return result(
                    therapy="Start BI + GLP-1 RA (FRC or separately)",
                    why=[
                        _above_target_str(diff) + ", which is 2% or more above target.",
                        "BMI \u2264 30 kg/m\u00b2: combination BI + GLP-1 RA is recommended "
                        "from initiation (Iraq algorithm, step 0).",
                        "Irregular meal patterns: premix agents are not recommended.",
                    ],
                    next_steps=[
                        "Start BI + GLP-1 RA via FRC or as separate injections — "
                        "no default preference between FRC and separate LA GLP-1 RA when both are usable.",
                        "Reassess HbA1c in 3 months; if still above target, escalate "
                        "to BI (max) + GLP-1 RA + rapid-acting insulin.",
                    ],
                )
            return result(
                therapy="Start BI + GLP-1 RA (FRC or separately) \u2014 or premix agents\u266f",
                why=[
                    _above_target_str(diff) + ", which is 2% or more above target.",
                    "BMI \u2264 30 kg/m\u00b2: combination BI + GLP-1 RA is recommended "
                    "from initiation; premix agents are an alternative only when other options "
                    "are not accessible (Iraq algorithm, step 0).",
                    IQ_BE_AWARE_PREMIX,
                ],
                next_steps=[
                    "Start BI + GLP-1 RA via FRC or as separate basal + GLP-1 RA injections.",
                    "FRC may be chosen as an alternative to separate BI + GLP-1 RA injections where suitable.",
                    "Complex insulin regimens (such as premix) may be used as alternatives "
                    "when other options are not accessible.",
                    "Reassess HbA1c in 3 months; if still above target, escalate "
                    "to BI (max) + GLP-1 RA + rapid-acting insulin.",
                ],
            )

        if bmi is not None and bmi > 30:
            if not la_ok:
                if irregular:
                    return result(
                        therapy="Start BI + GLP-1 RA (FRC)",
                        why=[
                            _above_target_str(diff) + ", which is 2% or more above target.",
                            "BMI > 30 kg/m\u00b2: combination BI + GLP-1 RA is recommended "
                            "from initiation (Iraq algorithm, step 0).",
                            "Monotherapy LA GLP-1 RA not used for routing; "
                            "FRC is the incretin-containing option (assumed available).",
                            "Irregular meal patterns: premix agents are not recommended.",
                        ],
                        next_steps=[
                            "Start BI + GLP-1 RA via FRC per local label.",
                            IQ_FRC_IRAQ_MOST_FEASIBLE,
                            "Reassess HbA1c in 3 months; if still above target, escalate "
                            "to BI (max) + GLP-1 RA + rapid-acting insulin.",
                        ],
                    )
                return result(
                    therapy="Start BI + GLP-1 RA (FRC)",
                    why=[
                        _above_target_str(diff) + ", which is 2% or more above target.",
                        "BMI > 30 kg/m\u00b2: BI + GLP-1 RA via FRC from initiation; "
                        "premix is not used in this obesity-first-injectable pathway "
                        "(Iraq algorithm, step 0).",
                        IQ_FRC_IRAQ_MOST_FEASIBLE,
                    ],
                    next_steps=[
                        "Start BI + GLP-1 RA via FRC per local label.",
                        "Titrate according to fasting and overall glycaemic targets.",
                        "Reassess HbA1c in 3 months; if still above target, escalate "
                        "to BI (max) + GLP-1 RA + rapid-acting insulin.",
                    ],
                )
            return result(
                therapy="Start BI + GLP-1 RA (FRC or separately)",
                why=[
                    _above_target_str(diff) + ", which is 2% or more above target.",
                    "BMI > 30 kg/m\u00b2: combination BI + GLP-1 RA is recommended "
                    "from initiation with monotherapy LA GLP-1 RA access; FRC is "
                    "not preferred over separate injections (Iraq algorithm, step 0).",
                ],
                next_steps=[
                    "Start separate basal insulin + GLP-1 RA injections, or start FRC — "
                    "FRC may be chosen as an alternative to separate BI + GLP-1 RA where suitable.",
                    "Reassess HbA1c in 3 months; if still above target, escalate "
                    "to BI (max) + GLP-1 RA + rapid-acting insulin.",
                ],
            )

        # BMI unknown, 2% or more above target
        comments.append(
            (
                "BMI not provided; BI + GLP-1 RA via FRC recommended when HbA1c is "
                "2% or more above target; monotherapy LA GLP-1 RA not required for FRC "
                "(Iraq algorithm)."
            )
            if not la_ok
            else (
                "BMI not provided; BI + GLP-1 RA combination recommended "
                "when HbA1c is 2% or more above target (Iraq algorithm)."
            )
        )
        if not la_ok:
            return result(
                therapy="Start BI + GLP-1 RA (FRC)",
                why=[
                    _above_target_str(diff) + ", which is 2% or more above target.",
                    "BMI unavailable; without monotherapy LA GLP-1 RA access, start FRC; "
                    "premix may be used only if FRC is not available.",
                    IQ_FRC_IRAQ_MOST_FEASIBLE,
                ],
                next_steps=[
                    "Confirm BMI to refine the choice.",
                    "Start BI + GLP-1 RA via FRC.",
                    "Premix may be used if FRC is not available.",
                    "Reassess HbA1c in 3 months.",
                ],
            )
        return result(
            therapy="Start BI + GLP-1 RA (FRC or separately)",
            why=[
                _above_target_str(diff) + ", which is 2% or more above target.",
                "BMI unavailable; combination BI + GLP-1 RA recommended "
                "across all BMI categories at this level; FRC is not inherently "
                "preferred over separate injections when monotherapy LA GLP-1 RA access exists.",
            ],
            next_steps=[
                "Confirm BMI to refine the choice.",
                "Start separate basal insulin + GLP-1 RA injections, or start FRC — "
                "FRC may be chosen as an alternative to separate BI + GLP-1 RA where suitable.",
                "Reassess HbA1c in 3 months.",
            ],
        )

    # ── HbA1c missing — BMI fallback ─────────────────────────────────────────
    comments.append(
        "HbA1c not provided; routing based on BMI only."
    )

    if bmi is not None and bmi > 30:
        if not la_ok:
            return result(
                therapy="Start BI + GLP-1 RA (FRC)",
                why=[
                    "Current HbA1c unavailable; routing based on BMI only.",
                    "BMI > 30 kg/m\u00b2: combined BI + GLP-1 RA is initiated via FRC when "
                    "monotherapy LA GLP-1 RA access is unavailable (Iraq algorithm).",
                    IQ_FRC_IRAQ_MOST_FEASIBLE,
                ],
                next_steps=[
                    "Obtain current HbA1c and individualised target to confirm routing.",
                    "Start BI + GLP-1 RA via FRC per local label.",
                    "Reassess HbA1c in 3 months.",
                ],
            )
        return result(
            therapy="Start GLP-1 RA monotherapy OR Start BI + GLP-1 RA (FRC or separately)",
            why=[
                "Current HbA1c unavailable; routing based on BMI only.",
                "BMI > 30 kg/m\u00b2: GLP-1 RA–containing strategy preferred; access allows "
                "monotherapy LA GLP-1 RA or combined therapy (Iraq algorithm).",
            ],
            next_steps=[
                "Obtain current HbA1c and individualised target to confirm routing.",
                "Start GLP-1 RA monotherapy or BI + GLP-1 RA (FRC or separately).",
                "Reassess HbA1c in 3 months.",
            ],
        )

    return result(
        therapy=IQ_THERAPY_BASAL_FIRST_PENDING_LABS,
        why=[
            "Current HbA1c unavailable; routing based on BMI only.",
            "BMI \u2264 30 kg/m\u00b2 or unknown: conservative basal-insulin-first approach.",
            IQ_SIMPLE_REGIMEN_NOTE,
            IQ_BI_SECOND_GEN_ELDERLY_CKD,
        ],
        next_steps=[
            "Obtain current HbA1c and individualised target to confirm routing.",
            "Titrate to fasting glucose target.",
            "Reassess HbA1c in 3 months.",
        ],
    )


# ══════════════════════════════════════════════════════════════════════════════
#  MAIN ROUTER
# ══════════════════════════════════════════════════════════════════════════════

def recommend(inputs):
    country = inputs.get("country")
    if country not in COUNTRIES:
        return {
            "therapy": "Unsupported country",
            "why": ["This engine currently supports only Turkey (TR) and Iraq (IQ)."],
            "next_steps": ["Provide one of: TR, IQ."],
            "comments": [],
        }

    profile = COUNTRIES[country]

    hba1c        = num(inputs.get("hba1c"))
    hba1c_target = num(inputs.get("hba1c_target"))
    bmi          = num(inputs.get("bmi"))

    # Turkey legacy regimen flags
    on_basal  = boolv(inputs.get("on_basal_insulin"))
    on_bb     = boolv(inputs.get("on_basal_bolus"))
    on_premix = boolv(inputs.get("on_premix"))
    on_frc    = boolv(inputs.get("on_frc"))
    on_rapid  = boolv(inputs.get("on_rapid_added"))

    symptoms_catabolic     = boolv(inputs.get("symptoms_catabolic"))
    recurrent_hypoglycemia = boolv(inputs.get("recurrent_hypoglycemia"))
    ppg_uncontrolled       = boolv(inputs.get("ppg_uncontrolled"))
    irregular_meal_patterns = boolv(inputs.get("irregular_meal_patterns"))

    fpg_mg_dl = fpg_mg_dl_from_inputs(inputs)

    effective_target = hba1c_target
    if effective_target is None and hba1c is not None:
        effective_target = 7.0

    if hba1c is not None and effective_target is not None:
        target_unmet = hba1c > effective_target
        diff = hba1c - effective_target
    else:
        target_unmet = False
        diff = None

    frc = profile["frc"]

    comments = []
    if hba1c is not None and hba1c_target is None:
        comments.append(
            "HbA1c target was not provided; default target of 7.0% was used."
        )

    # ── Shared gate: severe hyperglycaemia ───────────────────────────────────
    severe_hba1c = hba1c is not None and hba1c >= 10
    severe_fpg = fpg_mg_dl is not None and fpg_mg_dl > 300
    severe = symptoms_catabolic or severe_hba1c or severe_fpg
    if severe:
        why_severe = [
            "One or more severe hyperglycaemia criteria are met: rapid "
            "insulin-based control is needed."
        ]
        detail = []
        if symptoms_catabolic:
            detail.append("catabolic symptoms")
        if severe_hba1c:
            detail.append("HbA1c \u2265 10%")
        if severe_fpg:
            detail.append("FPG > 300 mg/dL (after unit conversion if entered in mmol/L)")
        if detail:
            why_severe.append("Triggers: " + "; ".join(detail) + ".")
        if severe_fpg and fpg_mg_dl is not None:
            comments.append(
                f"FPG used for gate: {fpg_mg_dl:.0f} mg/dL (equivalent after conversion)."
            )
        return {
            "therapy": "Start / intensify insulin (severe hyperglycaemia)",
            "why": why_severe,
            "next_steps": [
                "Initiate or intensify insulin with close monitoring.",
                "Reassess regimen after initial stabilisation.",
            ],
            "comments": comments,
        }

    # ── Iraq branch ───────────────────────────────────────────────────────────
    if country == "IQ":
        return _recommend_iq(inputs, diff, bmi, target_unmet, comments)

    # ── Turkey (original logic, unchanged) ───────────────────────────────────

    # On FRC + rapid + unmet
    if on_frc and on_rapid and target_unmet:
        if irregular_meal_patterns:
            return {
                "therapy": "Intensify to basal-bolus regimen",
                "why": [
                    "HbA1c target remains unmet despite FRC plus rapid-acting insulin.",
                    "Further intensification is warranted.",
                    "Irregular meal patterns: premixed insulin is not recommended.",
                ],
                "next_steps": [
                    "Basal-bolus: continue basal insulin + add rapid-acting insulin "
                    "before additional meals.",
                    "Reassess HbA1c in 3 months.",
                    "Ensure SMBG or CGM where available.",
                ],
                "comments": comments,
            }
        return {
            "therapy": "Intensify to basal-bolus regimen OR premixed insulin",
            "why": [
                "HbA1c target remains unmet despite FRC plus rapid-acting insulin.",
                "Further intensification is warranted.",
            ],
            "next_steps": [
                "Basal-bolus: continue basal insulin + add rapid-acting insulin "
                "before additional meals.",
                "Premixed insulin: consider when a simpler multidose insulin "
                "regimen is preferable.",
                "Reassess HbA1c in 3 months.",
                "Ensure SMBG or CGM where available.",
            ],
            "comments": comments,
        }

    # On FRC + unmet
    if on_frc and target_unmet:
        comments.append(
            "Adding rapid-acting insulin to FRC may be off-label depending "
            "on local label and market."
        )
        return {
            "therapy": "Add rapid-acting insulin to FRC",
            "why": [
                "HbA1c target remains unmet on FRC.",
                "Prandial coverage may be needed as the next intensification step.",
            ],
            "next_steps": [
                "Start with 1 prandial injection at the largest meal.",
                "If needed, intensify stepwise to additional meals.",
                "Reassess HbA1c in 3 months.",
                "Review local label / internal policy — this approach may be off-label.",
            ],
            "comments": comments,
        }

    # On BB or premix + recurrent hypo
    if (on_bb or on_premix) and recurrent_hypoglycemia:
        if frc:
            add_tr_frc_reimbursement_note(country, profile, bmi, comments)
            return {
                "therapy": "Consider switch to FRC for simplification",
                "why": [
                    "Recurrent hypoglycaemia on basal-bolus or premixed insulin "
                    "supports simplification."
                ],
                "next_steps": [
                    "Review current insulin doses and switching approach.",
                    "Initiate FRC and titrate according to local label.",
                    "Reassess glucose patterns after switch.",
                ],
                "comments": comments,
            }

    # On basal + unmet or PPG uncontrolled
    if on_basal and (target_unmet or ppg_uncontrolled):
        if frc:
            add_tr_frc_reimbursement_note(country, profile, bmi, comments)
            why = []
            if target_unmet:
                why.append("HbA1c remains above target on basal insulin.")
            if ppg_uncontrolled:
                why.append(
                    "Postprandial glucose remains uncontrolled on basal insulin."
                )
            why.append(
                "FRC can address both fasting and postprandial glucose "
                "in one injectable strategy."
            )
            return {
                "therapy": "Switch basal insulin to FRC",
                "why": why,
                "next_steps": [
                    "Stop basal-only strategy and initiate FRC.",
                    "Titrate according to local label and glucose response.",
                    "Reassess HbA1c and postprandial control in 3 months.",
                ],
                "comments": comments,
            }

    # First injectable — diff-based
    if diff is not None:
        if diff < 2.0:
            if bmi is not None and bmi <= 30:
                return {
                    "therapy": "Start basal insulin",
                    "why": [
                        "HbA1c is {:.1f}% above target, which is less than "
                        "2% above target.".format(diff),
                        "BMI \u2264 30 kg/m\u00b2: basal insulin is the preferred "
                        "initial injectable choice.",
                    ],
                    "next_steps": [
                        "Initiate basal insulin and titrate to fasting glucose target.",
                        "Reassess HbA1c in 3 months.",
                    ],
                    "comments": comments,
                }
            if bmi is not None and bmi > 30:
                add_tr_frc_reimbursement_note(country, profile, bmi, comments)
                comments.append(
                    "Optional non-reimbursed consideration: monotherapy GLP-1 RA "
                    "may be discussed if feasible out-of-pocket."
                )
                return {
                    "therapy": "Start FRC",
                    "why": [
                        "HbA1c is {:.1f}% above target, which is less than "
                        "2% above target.".format(diff),
                        "BMI > 30 kg/m\u00b2: FRC is preferred as the reimbursed "
                        "incretin-containing path.",
                    ],
                    "next_steps": [
                        "Initiate FRC and titrate according to local label.",
                        "Reassess HbA1c in 3 months.",
                    ],
                    "comments": comments,
                }
            comments.append(
                "BMI not provided; recommendation made conservatively. "
                "If BMI > 30, FRC may be preferred."
            )
            return {
                "therapy": "Start basal insulin",
                "why": [
                    "HbA1c is {:.1f}% above target, which is less than "
                    "2% above target.".format(diff),
                    "BMI is unavailable; conservative basal-insulin-first "
                    "choice used.",
                ],
                "next_steps": [
                    "Confirm BMI if possible.",
                    "Initiate basal insulin and titrate to fasting glucose target.",
                    "Reassess HbA1c in 3 months.",
                ],
                "comments": comments,
            }

        # 2% or more above target
        add_tr_frc_reimbursement_note(country, profile, bmi, comments)
        comments.append(
            "Optional non-reimbursed consideration: GLP-1 RA-based strategy "
            "may be discussed if feasible out-of-pocket."
        )
        return {
            "therapy": "Start FRC",
            "why": [
                "HbA1c is {:.1f}% above target, which is 2% or more "
                "above target.".format(diff),
                "FRC is preferred as the reimbursed combination path "
                "from initiation.",
            ],
            "next_steps": [
                "Initiate FRC and titrate according to local label.",
                "Reassess HbA1c in 3 months.",
            ],
            "comments": comments,
        }

    # HbA1c missing fallback
    if bmi is not None and bmi > 30:
        add_tr_frc_reimbursement_note(country, profile, bmi, comments)
        comments.append(
            "Optional non-reimbursed consideration: monotherapy GLP-1 RA "
            "may be discussed if feasible out-of-pocket."
        )
        return {
            "therapy": "Start FRC",
            "why": [
                "Current HbA1c is not available; routing based on BMI only.",
                "BMI > 30 kg/m\u00b2: FRC is preferred.",
            ],
            "next_steps": [
                "Initiate FRC and titrate according to local label.",
                "Define individualised HbA1c target for follow-up.",
            ],
            "comments": comments,
        }

    if bmi is not None and bmi <= 30:
        return {
            "therapy": "Start basal insulin",
            "why": [
                "Current HbA1c is not available; routing based on BMI only.",
                "BMI \u2264 30 kg/m\u00b2: basal insulin is the preferred "
                "conservative choice.",
            ],
            "next_steps": [
                "Initiate basal insulin and titrate to fasting glucose target.",
                "Define individualised HbA1c target for follow-up.",
            ],
            "comments": comments,
        }

    comments.append(
        "Recommendation made conservatively because current HbA1c and BMI "
        "were not fully available. If BMI > 30, FRC may be preferred."
    )
    return {
        "therapy": "Start basal insulin",
        "why": [
            "Current HbA1c and BMI are not sufficiently available; "
            "conservative basal-insulin-first approach used.",
        ],
        "next_steps": [
            "Confirm BMI and current HbA1c if possible.",
            "Initiate basal insulin and titrate to fasting glucose target.",
        ],
        "comments": comments,
    }


def recommend_json(js_inputs_json: str) -> str:
    inputs = json.loads(js_inputs_json)
    return json.dumps(recommend(inputs), ensure_ascii=False)


# ══════════════════════════════════════════════════════════════════════════════
#  SELF-TEST
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    TEST_CASES = [
        # Shared gate
        {
            "label": "TR | severe (HbA1c 10.5)",
            "inputs": {"country": "TR", "hba1c": 10.5, "bmi": 33},
        },
        {
            "label": "IQ | severe (catabolic)",
            "inputs": {"country": "IQ", "hba1c": 9.8, "bmi": 29,
                       "symptoms_catabolic": True,
                       "iq_glp1_ra_access": True},
        },
        {
            "label": "TR | severe (FPG > 300 mg/dL)",
            "inputs": {"country": "TR", "hba1c": 8.0, "bmi": 28,
                       "fpg": 310, "fpg_unit": "mg_dl"},
        },
        {
            "label": "IQ | severe (FPG mmol/L converted)",
            "inputs": {"country": "IQ", "hba1c": 8.0, "bmi": 28,
                       "fpg": 16.7, "fpg_unit": "mmol_l",
                       "iq_glp1_ra_access": True},
        },
        # IQ first injectable
        {
            "label": "IQ | <2% above target, BMI<=30 -> Basal",
            "inputs": {"country": "IQ", "hba1c": 7.8,
                       "hba1c_target": 7.0, "bmi": 28,
                       "iq_glp1_ra_access": True},
        },
        {
            "label": "IQ | <2% above target, BMI>30 -> GLP-1 RA or BI+GLP-1",
            "inputs": {"country": "IQ", "hba1c": 8.5,
                       "hba1c_target": 7.0, "bmi": 34,
                       "iq_glp1_ra_access": True},
        },
        {
            "label": "IQ | >=2% above target, BMI<=30 -> BI+GLP-1 or Premix",
            "inputs": {"country": "IQ", "hba1c": 9.5,
                       "hba1c_target": 7.0, "bmi": 27,
                       "iq_glp1_ra_access": True},
        },
        {
            "label": "IQ | >=2% above target, BMI>30 -> BI+GLP-1",
            "inputs": {"country": "IQ", "hba1c": 9.5,
                       "hba1c_target": 7.0, "bmi": 33,
                       "iq_glp1_ra_access": True},
        },
        # IQ without monotherapy LA GLP-1 RA access (la_ok false)
        {
            "label": "IQ | >=2% above, BMI<=30, no LA monotherapy access -> primarily FRC",
            "inputs": {"country": "IQ", "hba1c": 9.5,
                       "hba1c_target": 7.0, "bmi": 27,
                       "iq_glp1_ra_access": False},
        },
        {
            "label": "IQ | <2% above, BMI>30, no LA monotherapy access -> BI+GLP-1 (FRC) start",
            "inputs": {"country": "IQ", "hba1c": 8.5,
                       "hba1c_target": 7.0, "bmi": 34,
                       "iq_glp1_ra_access": False},
        },
        {
            "label": "IQ | on basal only unmet, no LA monotherapy access -> BI+GLP-1 (FRC)",
            "inputs": {"country": "IQ", "hba1c": 8.2,
                       "hba1c_target": 7.0, "bmi": 28,
                       "on_basal_only": True,
                       "iq_glp1_ra_access": False},
        },
        # IQ intensification ladder
        {
            "label": "IQ | on basal only, unmet -> BI+GLP-1",
            "inputs": {"country": "IQ", "hba1c": 8.2,
                       "hba1c_target": 7.0, "bmi": 28,
                       "on_basal_only": True,
                       "iq_glp1_ra_access": True},
        },
        {
            "label": "IQ | on GLP-1 alone, unmet -> BI+GLP-1",
            "inputs": {"country": "IQ", "hba1c": 8.4,
                       "hba1c_target": 7.0, "bmi": 35,
                       "on_glp1_alone": True,
                       "iq_glp1_ra_access": True},
        },
        {
            "label": "IQ | on GLP-1 alone unmet, no LA monotherapy access -> BI+GLP-1 (FRC)",
            "inputs": {"country": "IQ", "hba1c": 8.4,
                       "hba1c_target": 7.0, "bmi": 35,
                       "on_glp1_alone": True,
                       "iq_glp1_ra_access": False},
        },
        {
            "label": "IQ | on BI+GLP-1, unmet -> BI(max)+GLP-1+Rapid",
            "inputs": {"country": "IQ", "hba1c": 8.6,
                       "hba1c_target": 7.0, "bmi": 31,
                       "on_bi_glp1": True,
                       "iq_glp1_ra_access": True},
        },
        {
            "label": "IQ | on BI(max)+GLP-1+Rapid, unmet -> optimise adherence, no premix",
            "inputs": {"country": "IQ", "hba1c": 9.0,
                       "hba1c_target": 7.0, "bmi": 31,
                       "on_bi_glp1_rapid": True,
                       "iq_glp1_ra_access": True},
        },
        {
            "label": "IQ | >=2% above, BMI<=30, irregular meals -> BI+GLP-1 no premix",
            "inputs": {"country": "IQ", "hba1c": 9.5,
                       "hba1c_target": 7.0, "bmi": 27,
                       "irregular_meal_patterns": True,
                       "iq_glp1_ra_access": True},
        },
        {
            "label": "TR | FRC+rapid unmet, irregular -> basal-bolus only",
            "inputs": {"country": "TR", "hba1c": 8.5,
                       "hba1c_target": 7.0, "bmi": 30,
                       "on_basal_insulin": False,
                       "on_frc": True, "on_rapid_added": True,
                       "irregular_meal_patterns": True},
        },
        # IQ no target provided
        {
            "label": "IQ | no target, default 7.0, >=2% above, BMI>30",
            "inputs": {"country": "IQ", "hba1c": 9.1, "bmi": 33,
                       "iq_glp1_ra_access": True},
        },
        {
            "label": "IQ | omit iq_glp1_ra_access -> la_ok false; Start FRC (<2% BMI>30)",
            "inputs": {"country": "IQ", "hba1c": 8.5,
                       "hba1c_target": 7.0, "bmi": 34},
        },
        # Turkey
        {
            "label": "TR | BB + recurrent hypo -> FRC",
            "inputs": {"country": "TR", "hba1c": 7.8, "bmi": 32,
                       "on_basal_bolus": True,
                       "recurrent_hypoglycemia": True},
        },
        {
            "label": "TR | basal + PPG uncontrolled -> FRC",
            "inputs": {"country": "TR", "hba1c": 7.1,
                       "hba1c_target": 7.0, "bmi": 29,
                       "on_basal_insulin": True,
                       "ppg_uncontrolled": True},
        },
        {
            "label": "TR | first, <2% above target, BMI>30 -> FRC + note",
            "inputs": {"country": "TR", "hba1c": 8.2,
                       "hba1c_target": 7.0, "bmi": 32},
        },
        {
            "label": "TR | first, >=2% above target -> FRC",
            "inputs": {"country": "TR", "hba1c": 9.4,
                       "hba1c_target": 7.0, "bmi": 27},
        },
    ]

    sep = "-" * 72
    for tc in TEST_CASES:
        r = recommend(tc["inputs"])
        print(sep)
        print(f"TEST       : {tc['label']}")
        print(f"Therapy    : {r['therapy']}")
        print(f"Why        : {r['why']}")
        print(f"Next steps : {r['next_steps']}")
        if r.get("comments"):
            print(f"Comments   : {r['comments']}")
    print(sep)
