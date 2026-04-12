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
IQ_IRREGULAR_MEALS_NOTE_NO_GLP1 = (
    "Irregular meal patterns: premixed insulin is not recommended; prefer "
    "basal-bolus (basal + prandial rapid-acting insulin)."
)


def _iq_glp1_available(inputs):
    """
    True only when iq_glp1_ra_access is explicitly affirmative.
    Missing key, None, empty string, or False → no GLP-1 / FRC access.
    """
    v = inputs.get("iq_glp1_ra_access")
    if v is None:
        return False
    if isinstance(v, str) and v.strip() == "":
        return False
    return boolv(v)


def _iq_base_comments(irregular_meal_patterns_yes, glp1_ok=True):
    """
    If irregular_meal_patterns_yes: omit generic premix footnote; add irregular note.
    If not glp1_ok: omit IQ_GLP1_NOTE.
    """
    out = []
    if glp1_ok:
        out.append(IQ_GLP1_NOTE)
    out.append(IQ_BI_NOTE)
    if irregular_meal_patterns_yes:
        out.append(
            IQ_IRREGULAR_MEALS_NOTE if glp1_ok else IQ_IRREGULAR_MEALS_NOTE_NO_GLP1
        )
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
    glp1_ok          = _iq_glp1_available(inputs)

    comments.extend(_iq_base_comments(irregular, glp1_ok))

    def result(therapy, why, next_steps):
        return {
            "therapy": therapy,
            "why": why,
            "next_steps": next_steps,
            "comments": comments,
        }

    # ── Step 3: BI(max)+GLP-1+Rapid still unmet ─────────────────────────────
    if on_bi_glp1_rapid and target_unmet:
        if irregular:
            why_irr = [
                "HbA1c target remains unmet on maximal basal insulin with "
                "prandial rapid-acting insulin.",
                "Further insulin intensification is warranted "
                "(Iraq algorithm step 3).",
                "Irregular meal patterns: premixed insulin is not recommended.",
            ]
            if glp1_ok:
                why_irr[0] = (
                    "HbA1c target remains unmet on BI (max dose) + GLP-1 RA "
                    "+ rapid-acting insulin."
                )
            return result(
                therapy="Intensify insulin: basal-bolus regimen",
                why=why_irr,
                next_steps=[
                    "Basal-bolus: optimise basal dose + add / titrate "
                    "rapid-acting insulin before each main meal.",
                    "Reassess HbA1c in 3 months after regimen change.",
                    "Ensure structured SMBG or CGM where available.",
                ],
            )
        why_bb = [
            "HbA1c target remains unmet on BI (max dose) + GLP-1 RA "
            "+ rapid-acting insulin.",
            "Further insulin intensification is warranted "
            "(Iraq algorithm step 3).",
        ]
        if not glp1_ok:
            why_bb = [
                "HbA1c target remains unmet on maximal basal insulin with "
                "prandial rapid-acting insulin.",
                "Further insulin intensification is warranted "
                "(Iraq algorithm step 3).",
            ]
        return result(
            therapy="Intensify insulin: basal-bolus OR premixed insulin",
            why=why_bb,
            next_steps=[
                "Option A – Basal-bolus: optimise basal dose + add / titrate "
                "rapid-acting insulin before each main meal.",
                "Option B – Premixed insulin: twice-daily premixed regimen as "
                "a simpler alternative when resources or patient complexity favour it.",
                "Reassess HbA1c in 3 months after regimen change.",
                "Ensure structured SMBG or CGM where available.",
            ],
        )

    # ── Step 2: BI+GLP-1 still unmet → add rapid ───────────────────────────
    if on_bi_glp1 and target_unmet:
        if not glp1_ok:
            return result(
                therapy="Basal (max dose) + Rapid-acting insulin",
                why=[
                    "HbA1c target remains unmet on intensified basal insulin "
                    "with prandial coverage.",
                    "Without GLP-1 RA access: maximise basal insulin and add or "
                    "titrate rapid-acting insulin (basal-bolus pattern).",
                ],
                next_steps=[
                    "Titrate basal insulin to its maximum tolerated / labelled dose.",
                    "Add rapid-acting insulin starting with the largest meal "
                    "(basal-plus approach).",
                    "Titrate prandial dose on postprandial glucose readings.",
                    "Add stepwise before remaining meals if further control needed.",
                    "Reassess HbA1c in 3 months.",
                ],
            )
        return result(
            therapy="BI (max dose) + GLP-1 RA + Rapid-acting insulin",
            why=[
                "HbA1c target remains unmet on BI + GLP-1 RA combination.",
                "Iraq algorithm: intensify by maximising basal insulin dose "
                "and adding rapid-acting insulin.",
            ],
            next_steps=[
                "Titrate basal insulin to its maximum tolerated / labelled dose.",
                "Add rapid-acting insulin starting with the largest meal "
                "(basal-plus approach).",
                "Titrate prandial dose on postprandial glucose readings.",
                "Add stepwise before remaining meals if further control needed.",
                "Reassess HbA1c in 3 months.",
            ],
        )

    # ── GLP-1 alone unmet → BI + GLP-1 RA first (then rapid on next step) ───
    if on_glp1_alone and target_unmet:
        if not glp1_ok:
            if irregular:
                return result(
                    therapy="Basal-bolus regimen (basal + prandial rapid-acting insulin)",
                    why=[
                        "HbA1c target remains unmet on current therapy.",
                        "GLP-1 RA not accessible locally: escalate using insulin-only "
                        "basal-bolus intensification.",
                        "Irregular meal patterns: premixed insulin is not recommended.",
                    ],
                    next_steps=[
                        "Initiate or intensify basal insulin; add prandial "
                        "rapid-acting insulin starting with the largest meal.",
                        "Titrate to glucose targets; reassess HbA1c in 3 months.",
                    ],
                )
            return result(
                therapy="Basal-bolus OR premixed insulin",
                why=[
                    "HbA1c target remains unmet on current therapy.",
                    "GLP-1 RA not accessible locally: escalate using insulin-only "
                    "options (basal-bolus or premix).",
                ],
                next_steps=[
                    "Option A – Basal-bolus: basal insulin + prandial rapid-acting "
                    "insulin titrated to meals.",
                    "Option B – Premixed insulin: twice-daily premixed regimen "
                    "when a simpler schedule fits.",
                    "Reassess HbA1c in 3 months.",
                ],
            )
        return result(
            therapy="BI + GLP-1 RA (FRC preferably, or separately)",
            why=[
                "HbA1c target remains unmet on GLP-1 RA alone.",
                "Iraq algorithm: escalate to BI + GLP-1 RA before adding "
                "prandial rapid-acting insulin.",
            ],
            next_steps=[
                "Preferred: switch to FRC for simplicity and better GI tolerability.",
                "Alternative: add GLP-1 RA as a separate injection alongside "
                "basal insulin.",
                "Titrate according to local label and glucose response.",
                "Reassess HbA1c in 3 months; if still above target, escalate to "
                "BI (max dose) + GLP-1 RA + rapid-acting insulin.",
            ],
        )

    # ── Step 1: basal-only still unmet → BI + GLP-1 RA ──────────────────────
    if on_basal_only and target_unmet:
        if not glp1_ok:
            if irregular:
                return result(
                    therapy="Basal-bolus (add prandial rapid-acting insulin)",
                    why=[
                        "HbA1c target remains unmet on basal insulin alone.",
                        "GLP-1 RA / FRC not accessible locally: intensify with "
                        "prandial rapid-acting insulin.",
                        "Irregular meal patterns: premixed insulin is not recommended.",
                    ],
                    next_steps=[
                        "Add rapid-acting insulin starting with the largest meal; "
                        "titrate basal to fasting target.",
                        "Reassess HbA1c in 3 months.",
                    ],
                )
            return result(
                therapy="Basal-bolus OR premixed insulin",
                why=[
                    "HbA1c target remains unmet on basal insulin alone.",
                    "GLP-1 RA / FRC not accessible locally: intensify with "
                    "basal-bolus or premixed insulin.",
                ],
                next_steps=[
                    "Basal-bolus: add prandial rapid-acting insulin titrated to meals.",
                    "Premix alternative: consider twice-daily premixed insulin "
                    "when a simpler multidose pattern fits.",
                    "Reassess HbA1c in 3 months.",
                ],
            )
        return result(
            therapy="BI + GLP-1 RA (FRC preferably, or separately)",
            why=[
                "HbA1c target remains unmet on basal insulin alone.",
                "Iraq algorithm: escalate to BI + GLP-1 RA combination.",
            ],
            next_steps=[
                "Preferred: switch to FRC for simplicity and better GI tolerability.",
                "Alternative: add GLP-1 RA as a separate injection alongside "
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
                    "Initiate 2nd-generation basal insulin "
                    "(e.g. degludec or glargine U-300).",
                    "Titrate to fasting glucose target.",
                ]
                if glp1_ok:
                    ns_basal.append(
                        "Reassess HbA1c in 3 months; if still above target, "
                        "escalate to BI + GLP-1 RA (FRC preferably or separately)."
                    )
                else:
                    ns_basal.append(
                        "Reassess HbA1c in 3 months; if still above target, "
                        "escalate to basal-bolus or premixed insulin as appropriate."
                    )
                return result(
                    therapy="Basal insulin & titration",
                    why=[
                        _above_target_str(diff) + ", which is less than 2% above target.",
                        "BMI \u2264 30 kg/m\u00b2: basal insulin is the recommended "
                        "first injectable (Iraq algorithm, step 0).",
                    ],
                    next_steps=ns_basal,
                )

            if bmi is not None and bmi > 30:
                if not glp1_ok:
                    return result(
                        therapy="Basal insulin & titration",
                        why=[
                            _above_target_str(diff) + ", which is less than 2% above target.",
                            "BMI > 30 kg/m\u00b2 but GLP-1 RA not accessible locally: "
                            "basal insulin is the recommended first injectable "
                            "(Iraq algorithm, step 0).",
                        ],
                        next_steps=[
                            "Initiate 2nd-generation basal insulin "
                            "(e.g. degludec or glargine U-300).",
                            "Titrate to fasting glucose target.",
                            "Reassess HbA1c in 3 months; if still above target, "
                            "escalate to basal-bolus or premixed insulin as appropriate.",
                        ],
                    )
                return result(
                    therapy="GLP-1 RA alone  OR  BI + GLP-1 RA (FRC or separately)",
                    why=[
                        _above_target_str(diff) + ", which is less than 2% above target.",
                        "BMI > 30 kg/m\u00b2: GLP-1 RA alone is preferred; "
                        "BI + GLP-1 RA (FRC or separately) is an alternative "
                        "(Iraq algorithm, step 0).",
                    ],
                    next_steps=[
                        "First choice: initiate GLP-1 RA alone; titrate per label.",
                        "If fasting glucose remains elevated, add basal insulin "
                        "or switch to FRC.",
                        "FRC: typically once daily from a single pen where available.",
                        "Reassess HbA1c in 3 months; if still above target, escalate "
                        "to BI (max) + GLP-1 RA + rapid-acting insulin.",
                    ],
                )

            # BMI unknown
            comments.append(
                "BMI not provided; conservative basal-insulin-first choice used."
                + (
                    " If BMI > 30, GLP-1 RA alone or BI + GLP-1 RA "
                    "(FRC or separately) may be preferred."
                    if glp1_ok
                    else " If BMI > 30 and GLP-1 RA becomes available, reassess."
                )
            )
            return result(
                therapy="Basal insulin & titration (BMI unknown)",
                why=[
                    _above_target_str(diff) + ", which is less than 2% above target.",
                    "BMI is unavailable; conservative basal-insulin-first approach used.",
                ],
                next_steps=[
                    "Confirm BMI to refine the choice.",
                    "Initiate 2nd-generation basal insulin and titrate to "
                    "fasting glucose target.",
                    "Reassess HbA1c in 3 months.",
                ],
            )

        # HbA1c 2% or more above target

        if bmi is not None and bmi <= 30:
            if not glp1_ok:
                if irregular:
                    return result(
                        therapy="Basal-bolus (basal + prandial rapid-acting insulin)",
                        why=[
                            _above_target_str(diff) + ", which is 2% or more above target.",
                            "GLP-1 RA not accessible locally: start with insulin-only "
                            "basal-bolus from initiation.",
                            "Irregular meal patterns: premix agents are not recommended.",
                        ],
                        next_steps=[
                            "Initiate basal insulin with prandial rapid-acting "
                            "insulin titrated to meals.",
                            "Reassess HbA1c in 3 months; intensify basal-bolus as needed.",
                        ],
                    )
                return result(
                    therapy="Premix agents\u266f  OR  basal-bolus insulin",
                    why=[
                        _above_target_str(diff) + ", which is 2% or more above target.",
                        "GLP-1 RA not accessible locally: premix or basal-bolus are "
                        "appropriate insulin-only options (Iraq algorithm, step 0).",
                    ],
                    next_steps=[
                        "Premix (\u266f): consider when a fixed mix suits the patient.",
                        "Basal-bolus: basal insulin + prandial rapid-acting insulin.",
                        "Reassess HbA1c in 3 months.",
                    ],
                )
            if irregular:
                return result(
                    therapy="BI + GLP-1 RA (FRC or separately)",
                    why=[
                        _above_target_str(diff) + ", which is 2% or more above target.",
                        "BMI \u2264 30 kg/m\u00b2: combination BI + GLP-1 RA is recommended "
                        "from initiation (Iraq algorithm, step 0).",
                        "Irregular meal patterns: premix agents are not recommended.",
                    ],
                    next_steps=[
                        "Preferred: FRC — typically once daily from a single pen.",
                        "Alternative: separate basal insulin + GLP-1 RA injections.",
                        "Reassess HbA1c in 3 months; if still above target, escalate "
                        "to BI (max) + GLP-1 RA + rapid-acting insulin.",
                    ],
                )
            return result(
                therapy="BI + GLP-1 RA (FRC or separately)  —  or Premix agents\u266f",
                why=[
                    _above_target_str(diff) + ", which is 2% or more above target.",
                    "BMI \u2264 30 kg/m\u00b2: combination BI + GLP-1 RA is recommended "
                    "from initiation; premix agents are an alternative if other options "
                    "are inaccessible locally (Iraq algorithm, step 0).",
                ],
                next_steps=[
                    "Preferred: FRC — typically once daily from a single pen.",
                    "Alternative: separate basal insulin + GLP-1 RA injections.",
                    "Premix alternative (\u266f): if FRC and GLP-1 RA are not "
                    "accessible locally.",
                    "Reassess HbA1c in 3 months; if still above target, escalate "
                    "to BI (max) + GLP-1 RA + rapid-acting insulin.",
                ],
            )

        if bmi is not None and bmi > 30:
            if not glp1_ok:
                if irregular:
                    return result(
                        therapy="Basal-bolus (basal + prandial rapid-acting insulin)",
                        why=[
                            _above_target_str(diff) + ", which is 2% or more above target.",
                            "GLP-1 RA not accessible locally: insulin-only basal-bolus "
                            "from initiation.",
                            "Irregular meal patterns: premix agents are not recommended.",
                        ],
                        next_steps=[
                            "Initiate basal insulin with mealtime rapid-acting insulin.",
                            "Reassess HbA1c in 3 months.",
                        ],
                    )
                return result(
                    therapy="Premix agents\u266f  OR  basal-bolus insulin",
                    why=[
                        _above_target_str(diff) + ", which is 2% or more above target.",
                        "GLP-1 RA not accessible locally: premix or basal-bolus from "
                        "initiation (Iraq algorithm, step 0).",
                    ],
                    next_steps=[
                        "Premix (\u266f) or basal-bolus per patient and access.",
                        "Reassess HbA1c in 3 months.",
                    ],
                )
            return result(
                therapy="BI + GLP-1 RA (FRC or separately)",
                why=[
                    _above_target_str(diff) + ", which is 2% or more above target.",
                    "BMI > 30 kg/m\u00b2: combination BI + GLP-1 RA is recommended "
                    "from initiation (Iraq algorithm, step 0).",
                ],
                next_steps=[
                    "Preferred: FRC — typically once daily from a single pen.",
                    "Alternative: separate basal insulin + GLP-1 RA injections.",
                    "Reassess HbA1c in 3 months; if still above target, escalate "
                    "to BI (max) + GLP-1 RA + rapid-acting insulin.",
                ],
            )

        # BMI unknown, 2% or more above target
        comments.append(
            (
                "BMI not provided; insulin-only intensification (premix or basal-bolus) "
                "recommended when HbA1c is 2% or more above target and GLP-1 RA is "
                "not accessible (Iraq algorithm)."
            )
            if not glp1_ok
            else (
                "BMI not provided; BI + GLP-1 RA combination recommended "
                "when HbA1c is 2% or more above target (Iraq algorithm)."
            )
        )
        if not glp1_ok:
            return result(
                therapy="Premix agents\u266f  OR  basal-bolus insulin",
                why=[
                    _above_target_str(diff) + ", which is 2% or more above target.",
                    "BMI unavailable; without GLP-1 RA access, use premix or basal-bolus.",
                ],
                next_steps=[
                    "Confirm BMI to refine the choice.",
                    "Initiate premix or basal-bolus per patient factors and access.",
                    "Reassess HbA1c in 3 months.",
                ],
            )
        return result(
            therapy="BI + GLP-1 RA (FRC or separately)",
            why=[
                _above_target_str(diff) + ", which is 2% or more above target.",
                "BMI unavailable; combination BI + GLP-1 RA recommended "
                "across all BMI categories at this level.",
            ],
            next_steps=[
                "Confirm BMI to refine the choice.",
                "Preferred: FRC.",
                "Alternative: separate basal insulin + GLP-1 RA.",
                "Reassess HbA1c in 3 months.",
            ],
        )

    # ── HbA1c missing — BMI fallback ─────────────────────────────────────────
    comments.append(
        "HbA1c not provided; routing based on BMI only."
    )

    if bmi is not None and bmi > 30:
        if not glp1_ok:
            return result(
                therapy="Basal insulin & titration",
                why=[
                    "Current HbA1c unavailable; routing based on BMI only.",
                    "BMI > 30 kg/m\u00b2 but GLP-1 RA not accessible locally: "
                    "start with basal insulin.",
                ],
                next_steps=[
                    "Obtain current HbA1c and individualised target to confirm routing.",
                    "Initiate 2nd-generation basal insulin and titrate to fasting "
                    "glucose target.",
                    "Reassess HbA1c in 3 months.",
                ],
            )
        return result(
            therapy="GLP-1 RA alone  OR  BI + GLP-1 RA (FRC or separately)",
            why=[
                "Current HbA1c unavailable; routing based on BMI only.",
                "BMI > 30 kg/m\u00b2: GLP-1 RA-containing strategy preferred.",
            ],
            next_steps=[
                "Obtain current HbA1c and individualised target to confirm routing.",
                "Initiate GLP-1 RA alone or BI + GLP-1 RA (FRC or separately).",
                "Reassess HbA1c in 3 months.",
            ],
        )

    return result(
        therapy="Basal insulin & titration",
        why=[
            "Current HbA1c unavailable; routing based on BMI only.",
            "BMI \u2264 30 kg/m\u00b2 or unknown: conservative basal-insulin-first approach.",
        ],
        next_steps=[
            "Obtain current HbA1c and individualised target to confirm routing.",
            "Initiate 2nd-generation basal insulin and titrate to fasting "
            "glucose target.",
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
                    "Optional non-reimbursed consideration: standalone GLP-1 RA "
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
            "Optional non-reimbursed consideration: standalone GLP-1 RA "
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
        # IQ without GLP-1 RA access
        {
            "label": "IQ | >=2% above, BMI<=30, no GLP-1 access -> premix or BB",
            "inputs": {"country": "IQ", "hba1c": 9.5,
                       "hba1c_target": 7.0, "bmi": 27,
                       "iq_glp1_ra_access": False},
        },
        {
            "label": "IQ | <2% above, BMI>30, no GLP-1 access -> basal",
            "inputs": {"country": "IQ", "hba1c": 8.5,
                       "hba1c_target": 7.0, "bmi": 34,
                       "iq_glp1_ra_access": False},
        },
        {
            "label": "IQ | on basal only unmet, no GLP-1 access -> BB or premix",
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
            "label": "IQ | on BI+GLP-1, unmet -> BI(max)+GLP-1+Rapid",
            "inputs": {"country": "IQ", "hba1c": 8.6,
                       "hba1c_target": 7.0, "bmi": 31,
                       "on_bi_glp1": True,
                       "iq_glp1_ra_access": True},
        },
        {
            "label": "IQ | on BI(max)+GLP-1+Rapid, unmet -> BB or Premix",
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
            "label": "IQ | omit iq_glp1_ra_access key -> no GLP-1 path (<2% BMI>30)",
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
