import json
import sys

# ======================
# Country configuration
# ======================

COUNTRIES = {
    # tr_bmi_threshold: reimbursement / access commentary only (SGK-linked), not TEMD clinical thresholds.
    "TR": {"frc": True, "label": "Türkiye", "tr_bmi_threshold": 35},
    "IQ": {"frc": True, "label": "Iraq"},
}

# Feature flag: the Türkiye (TR) TEMD branch is currently disabled and kept as
# legacy. Set TR_ENABLED = True to restore TR routing (engine + UI markup).
TR_ENABLED = False

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


def _glucose_numeric_mg_dl(raw_val, unit_key, inputs):
    """Return glucose in mg/dL from optional raw value and unit selector key, or None."""
    raw = num(raw_val)
    if raw is None:
        return None
    unit = str(inputs.get(unit_key) or "mg_dl").strip().lower().replace(" ", "")
    if unit in ("mmol_l", "mmol/l", "mmol"):
        return raw * FPG_MMOL_TO_MG_DL
    return raw


def fpg_mg_dl_from_inputs(inputs):
    """Return fasting (FPG/APG) in mg/dL, or None if not provided."""
    return _glucose_numeric_mg_dl(inputs.get("fpg"), "fpg_unit", inputs)


def random_pg_mg_dl_from_inputs(inputs):
    """Optional random / non-fasting glucose (TEMD §9.2.3 random PG criterion), mg/dL or None."""
    return _glucose_numeric_mg_dl(inputs.get("random_pg"), "random_pg_unit", inputs)


def add_tr_frc_reimbursement_note(country, profile, bmi, comments):
    if country == "TR" and bmi is not None and bmi < profile.get("tr_bmi_threshold", 35):
        comments.append(
            "SGK/access (non-TEMD clinical rule): reimbursed FRC coverage may be limited when "
            "BMI < 35 kg/m²; treatment may be out-of-pocket depending on local conditions."
        )


# ── Türkiye (TR) — TEMD-aligned notes (injectable-scope) ─────────────────────

TR_BASAL_ANALOG_NOTE = (
    "Basal insulin: long-acting or newer-generation basal analogues (e.g. degludec, "
    "glargine U-300, icodec) are typically preferred where available for lower hypoglycaemia "
    "risk versus older basal insulins."
)


def _tr_severe_symptoms_any(inputs):
    """
    Severe-context symptoms per TEMD §9.2.3: hyperglycaemic symptoms (polyuria/polydipsia /
    nocturia), weight-loss / catabolic signs, or suspected metabolic catastrophe.
    Legacy `symptoms_catabolic` is accepted as a combined shortcut.
    """
    return (
        boolv(inputs.get("symptoms_catabolic"))
        or boolv(inputs.get("symptoms_hyperglycemic"))
        or boolv(inputs.get("symptoms_weight_loss"))
        or boolv(inputs.get("symptoms_metabolic_emergency"))
    )


def _tr_cardiometabolic_focus(inputs):
    """TEMD Şekil 9.4 / §9.2.4–style modifiers (injectable-layer proxy)."""
    return (
        boolv(inputs.get("tr_ascvd"))
        or boolv(inputs.get("tr_hf"))
        or boolv(inputs.get("tr_ckd"))
        or boolv(inputs.get("tr_masld"))
    )


def _append_tr_cardiorenal_hints(comments, inputs):
    if not _tr_cardiometabolic_focus(inputs):
        return
    lines = []
    if boolv(inputs.get("tr_ascvd")):
        lines.append(
            "TEMD 2024: established ASCVD — GLP-1 RA evidence class prioritised "
            "(FRC combines basal insulin + GLP-1 RA in this tool)."
        )
    if boolv(inputs.get("tr_hf")) or boolv(inputs.get("tr_ckd")):
        lines.append(
            "TEMD 2024: HF and/or CKD — where oral therapy fits, guideline-preferred agents "
            "often include GLP-1 RA and/or SGLT2-İ alongside metformin; individualise CV/renal indications."
        )
    if boolv(inputs.get("tr_masld")):
        lines.append(
            "TEMD 2024 / Şekil 9.4: MASLD/MASH setting — pioglitazone or GLP-1 RA are commonly "
            "highlighted orally; injectable pathway here favours GLP-1 RA-containing options when applicable."
        )
    comments.extend(lines)


def _append_tr_basal_quality_note(comments):
    comments.append(TR_BASAL_ANALOG_NOTE)


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


def _iq_key_considerations(irregular_meal_patterns_yes):
    """
    Standardised Iraq consensus 'Key Considerations' block, attached to every Iraq
    recommendation. Mirrors the fixed card in the Cases Consensus document.
    """
    kc = [
        "HbA1c target (~7%): individualised.",
        "2nd-generation basal insulin: lower hypoglycaemia risk, >24h stable profile.",
        "GLP-1 RA choice: guided by weight, CVD/CKD, and access/cost.",
        "FRC (BI + GLP-1 RA): simple, once daily, low hypo, weight neutral, improved "
        "adherence; consider when GLP-1 RA access or tolerability is limited.",
        "Basal-bolus: flexible but higher injection burden.",
        "Premix insulin: simple but requires fixed meals; alternative when preferred "
        "options are unavailable.",
    ]
    if irregular_meal_patterns_yes:
        kc.append("Irregular meals: avoid premix.")
    return kc


# ══════════════════════════════════════════════════════════════════════════════
#  IRAQ ALGORITHM
# ══════════════════════════════════════════════════════════════════════════════

def _above_target_str(diff):
    """
    Human-readable description of how far HbA1c is above target.
    Uses 'above target' language — no 'gap' terminology.
    """
    return f"HbA1c is {diff:.1f}% above target"


def _recommend_iq(inputs, diff, bmi, target_unmet, comments, band_mode=False):
    """
    Iraq-specific routing.
    `diff`         – float or None  (hba1c − effective_target)
    `bmi`          – float or None
    `target_unmet` – bool
    `comments`     – list (extended here with standing Iraq footnotes)
    `band_mode`    – bool: inputs came from binary band selectors, so phrase the
                     HbA1c-distance generically (no fabricated percentage).
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

    def lead(below2):
        """First sentence describing HbA1c distance above target."""
        if band_mode:
            return (
                "HbA1c is less than 2% above target."
                if below2
                else "HbA1c is 2% or more above target."
            )
        return _above_target_str(diff) + (
            ", which is less than 2% above target."
            if below2
            else ", which is 2% or more above target."
        )

    def result(therapy, why, next_steps):
        return {
            "therapy": therapy,
            "why": why,
            "next_steps": next_steps,
            "comments": comments,
            "key_considerations": _iq_key_considerations(irregular),
        }

    # ── Step 3: BI(max)+GLP-1+Rapid still unmet ─────────────────────────────
    if on_bi_glp1_rapid and target_unmet:
        why_core = [
            "HbA1c target remains unmet on BI (max dose) + GLP-1 RA "
            "+ rapid-acting insulin.",
            "Optimise the BI + GLP-1 RA component and ensure prandial insulin is "
            "titrated before moving to more complex regimens (Iraq algorithm step 3).",
            "Persistent hyperglycaemia with multiple daily excursions requires full "
            "insulin coverage; intensify to basal-bolus for full basal and prandial control.",
        ]
        ns_rapid = [
            "Optimise basal dose and stepwise rapid-acting insulin before each main "
            "meal as appropriate.",
            "Intensify to basal-bolus for full basal and prandial glucose control "
            "across the day.",
        ]
        if irregular:
            why_core.append(
                "Irregular meal patterns: premixed insulin is not recommended."
            )
        else:
            ns_rapid.append(
                "Alternative: premix insulin if needed or access is limited "
                "(simpler fixed-dose regimen when basal-bolus is not feasible)."
            )
        ns_rapid.append("Reassess HbA1c in 3 months after regimen optimisation.")
        ns_rapid.append(
            "Ensure structured SMBG or CGM where available; address adherence "
            "barriers before escalating complexity."
        )
        return result(
            therapy="Intensify to basal-bolus (optimise BI + GLP-1 RA + prandial first)",
            why=why_core,
            next_steps=ns_rapid,
        )

    # ── Step 2: BI+GLP-1 still unmet → optimise then add stepwise prandial ──
    if on_bi_glp1 and target_unmet:
        why_rapid = [
            "HbA1c target remains unmet on BI + GLP-1 RA combination.",
            "Iraq algorithm: optimise BI + GLP-1 RA, then add stepwise prandial insulin "
            "(start with the largest meal); maximise basal insulin dose as needed.",
        ]
        ns_rapid = [
            "Optimise BI + GLP-1 RA (FRC or separate basal + GLP-1 RA).",
            "Titrate basal insulin to its maximum tolerated / labelled dose.",
            "Add rapid-acting insulin starting with the largest meal "
            "(basal-plus approach); stepwise addition to further meals as needed; "
            "titrate prandial dose on postprandial glucose readings.",
        ]
        if irregular:
            why_rapid.append(
                "Irregular meal patterns: premixed insulin is not recommended."
            )
        if not la_ok:
            why_rapid.append(
                "Because monotherapy LA GLP-1 RA is not accessible, continue GLP-1 RA "
                "delivery via FRC and treat this step as stepwise prandial coverage."
            )
        ns_rapid.append(
            "If persistent hyperglycaemia despite optimised therapy, intensify to basal-bolus."
        )
        if not irregular:
            ns_rapid.append(
                "Alternative: premix insulin if needed or access is limited."
            )
        ns_rapid.append("Reassess HbA1c in 3 months.")
        return result(
            therapy="BI (max dose) + GLP-1 RA + Rapid-acting insulin",
            why=why_rapid,
            next_steps=ns_rapid,
        )

    # ── GLP-1 alone unmet → BI + GLP-1 RA (split <2% vs >=2% above target) ──
    if on_glp1_alone and target_unmet:
        below2 = diff is not None and diff < 2.0
        if not la_ok:
            why_g = ["HbA1c target remains unmet on GLP-1 RA monotherapy."]
            if below2:
                why_g.append(
                    "HbA1c <2% above target: optimise GLP-1 RA and add basal insulin; "
                    "GLP-1 RA alone does not adequately control fasting glucose."
                )
            else:
                why_g.append(
                    "HbA1c >=2% above target: start BI + GLP-1 RA combination targeting "
                    "both fasting and postprandial glucose."
                )
            why_g.append(
                "Monotherapy LA GLP-1 RA is not available for routing; escalate using "
                "fixed-ratio combination (FRC), assumed available."
            )
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
                    "Reassess HbA1c in 3 months; if still above target, add stepwise "
                    "prandial insulin (largest meal first), then escalate to "
                    "BI (max dose) + GLP-1 RA + rapid-acting insulin.",
                ],
            )
        why_g = ["HbA1c target remains unmet on GLP-1 RA monotherapy."]
        if below2:
            why_g.append(
                "HbA1c <2% above target: optimise GLP-1 RA and add basal insulin "
                "(FRC or separate injections); GLP-1 RA alone does not adequately "
                "control fasting glucose."
            )
        else:
            why_g.append(
                "HbA1c >=2% above target: start BI + GLP-1 RA combination "
                "(FRC or separate injections; no preference enforced), targeting "
                "both fasting and postprandial glucose."
            )
        return result(
            therapy="BI + GLP-1 RA (FRC or separately)",
            why=why_g,
            next_steps=[
                "Option A — Add basal insulin alongside continued separate GLP-1 RA injections.",
                "Option B — Switch to FRC (basal + GLP-1 fixed ratio) where suitable.",
                "Titrate according to local label and glucose response.",
                "Reassess HbA1c in 3 months; if still above target, add stepwise prandial "
                "insulin (largest meal first), then escalate to "
                "BI (max dose) + GLP-1 RA + rapid-acting insulin.",
            ],
        )

    # ── Step 1: basal-only still unmet → titrate + add GLP-1 RA / combination ─
    if on_basal_only and target_unmet:
        below2 = diff is not None and diff < 2.0

        if not la_ok:
            if below2:
                why_base = [
                    "HbA1c target remains unmet on basal insulin (<2% above target): "
                    "titrate basal to fasting target (up to ~0.5 U/kg/day) and add GLP-1 RA."
                ]
            else:
                why_base = [
                    "HbA1c target remains unmet on basal insulin (>=2% above target): "
                    "start BI + GLP-1 RA combination."
                ]
            why_base.append(
                "Monotherapy LA GLP-1 RA not used for access routing; "
                "escalate via FRC (assumed available)."
            )
            if irregular:
                why_base.append(
                    "Irregular meal patterns: premixed insulin is not recommended."
                )
            ns_ladd = [
                "Titrate basal insulin to fasting glucose target (up to ~0.5 U/kg/day).",
                "Switch to or initiate FRC (basal + GLP-1 fixed ratio).",
                IQ_MONOTHERAPY_LA_UNAVAILABLE,
            ]
            if not below2 and not irregular:
                ns_ladd.append(
                    "Alternative: premix insulin when FRC / free combination is unavailable."
                )
            ns_ladd.append("Titrate according to local label and glucose response.")
            ns_ladd.append(
                "Reassess HbA1c in 3 months; if still above target, add stepwise "
                "prandial insulin (largest meal first)."
            )
            return result(
                therapy="BI + GLP-1 RA (FRC)",
                why=why_base,
                next_steps=ns_ladd,
            )

        if below2:
            why_base = [
                "HbA1c target remains unmet on basal insulin (<2% above target): titrate "
                "basal to fasting target (up to ~0.5 U/kg/day) and add GLP-1 RA "
                "(FRC or separate injections)."
            ]
        else:
            why_base = [
                "HbA1c target remains unmet on basal insulin (>=2% above target): start "
                "BI + GLP-1 RA combination (FRC or separate injections; no preference enforced)."
            ]
        if bmi is not None and bmi > 30:
            why_base.append(
                "BMI and weight considerations favor GLP-1 RA–based combinations."
            )
        ns_base = [
            "Titrate basal insulin to fasting glucose target (up to ~0.5 U/kg/day).",
            "Option A — Switch to FRC (basal + GLP-1 fixed ratio) where suitable.",
            "Option B — Add GLP-1 RA as a separate injection alongside current basal insulin.",
        ]
        if not below2 and not irregular:
            ns_base.append(
                "Alternative: premix insulin when FRC / free combination is unavailable."
            )
        ns_base.append("Titrate according to local label and glucose response.")
        ns_base.append(
            "Reassess HbA1c in 3 months; if still above target, add stepwise "
            "prandial insulin (largest meal first)."
        )
        return result(
            therapy="BI + GLP-1 RA (FRC or separately)",
            why=why_base,
            next_steps=ns_base,
        )

    # ── On premixed insulin → simplify to FRC (or basal-bolus) ───────────────
    # Handled on the regimen flag alone so an established premix patient never
    # falls through to first-injectable routing.
    if on_premix:
        why_pre = [
            "On premixed insulin with inadequate control.",
            "Premix challenges: limited flexibility (requires regular meals), "
            "hypoglycaemia risk with irregular eating, and difficult titration.",
            "Iraq algorithm: prefer simplification to FRC (BI + GLP-1 RA) where accessible.",
        ]
        if boolv(inputs.get("recurrent_hypoglycemia")):
            why_pre.append(
                "Recurrent hypoglycaemia on premix further supports simplification."
            )
        return result(
            therapy="Transition to FRC (BI + GLP-1 RA) where accessible; otherwise basal-bolus",
            why=why_pre,
            next_steps=[
                "If HbA1c is above target, prefer transition to FRC (BI + GLP-1 RA) where "
                "accessible — simplifies the regimen, improves adherence, and targets both "
                "fasting and postprandial glucose.",
                "Alternative: intensify to basal-bolus for flexible full basal and prandial "
                "control across the day.",
                "Reassess HbA1c in 3 months.",
            ],
        )

    # ── On basal-bolus → simplify to FRC (premix alternative if regular meals) ─
    if on_bb:
        why_bb = [
            "On basal-bolus insulin with inadequate control.",
            "Basal-bolus challenges: high injection burden, low adherence, higher "
            "hypoglycaemia risk, and complexity.",
            "Iraq algorithm: prefer simplification to FRC (BI + GLP-1 RA) where accessible.",
        ]
        if boolv(inputs.get("recurrent_hypoglycemia")):
            why_bb.append(
                "Recurrent hypoglycaemia on basal-bolus further supports simplification."
            )
        ns_bb = [
            "If HbA1c is above target, prefer transition to FRC (BI + GLP-1 RA) where "
            "accessible — simplifies the regimen, improves adherence, and targets both "
            "fasting and postprandial glucose.",
        ]
        if irregular:
            why_bb.append(
                "Irregular meal patterns: premixed insulin is not recommended."
            )
        else:
            ns_bb.append(
                "Alternative: switch to premix insulin if needed or access is limited."
            )
        ns_bb.append("Reassess HbA1c in 3 months.")
        return result(
            therapy="Transition to FRC (BI + GLP-1 RA) where accessible (simplification)",
            why=why_bb,
            next_steps=ns_bb,
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
                        lead(True),
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
                            lead(True),
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
                    lead(True),
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
                    lead(True),
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
                            lead(False),
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
                        lead(False),
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
                        lead(False),
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
                    lead(False),
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
                            lead(False),
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
                        lead(False),
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
                    lead(False),
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
                    lead(False),
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
                lead(False),
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
    # Simplified deployment is Iraq-only; default a missing/empty country to IQ.
    if not country:
        country = "IQ"

    # Türkiye (TR) is currently disabled legacy — see TR_ENABLED.
    if country == "TR" and not TR_ENABLED:
        return {
            "therapy": "Türkiye (TR) is currently disabled (legacy)",
            "why": [
                "The Türkiye TEMD branch is turned off in this deployment.",
                "Re-enable it by setting TR_ENABLED = True in py/engine.py "
                "(and restoring the TR inputs in the UI).",
            ],
            "next_steps": ["Use the Iraq (IQ) pathway."],
            "comments": [],
        }

    if country not in COUNTRIES:
        return {
            "therapy": "Unsupported country",
            "why": ["This engine currently supports only Iraq (IQ). Türkiye (TR) is legacy/disabled."],
            "next_steps": ["Provide: IQ."],
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

    recurrent_hypoglycemia = boolv(inputs.get("recurrent_hypoglycemia"))
    ppg_uncontrolled       = boolv(inputs.get("ppg_uncontrolled"))
    irregular_meal_patterns = boolv(inputs.get("irregular_meal_patterns"))

    fpg_mg_dl = fpg_mg_dl_from_inputs(inputs)
    random_mg_dl = random_pg_mg_dl_from_inputs(inputs)

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

    # ── Türkiye: severe hyperglycaemia / insulin-start gate (TEMD 2024 §9.2.3, Bölüm 8) ──
    # Inequalities follow §9.2.3 wording: HbA1c ≥9%; APG (fasting) >250 mg/dL; random PG >300 mg/dL.
    # Iraq (IQ) uses regimen-first routing; this gate is TR-only.
    if country == "TR":
        severe_symptoms = _tr_severe_symptoms_any(inputs)
        severe_hba1c = hba1c is not None and hba1c >= 9.0
        severe_apg = fpg_mg_dl is not None and fpg_mg_dl > 250
        severe_random = random_mg_dl is not None and random_mg_dl > 300
        severe = severe_symptoms or severe_hba1c or severe_apg or severe_random
        if severe:
            why_severe = [
                "TEMD Diabetes Mellitus Guide 2024 (§9.2.3, Bölüm 8): metabolic decompensation "
                "or severe hyperglycaemia — insulin should be started or intensified urgently."
            ]
            detail = []
            if boolv(inputs.get("symptoms_hyperglycemic")):
                detail.append("hyperglycaemic symptoms (e.g. polyuria, polydipsia, nocturia)")
            if boolv(inputs.get("symptoms_weight_loss")):
                detail.append("weight loss / catabolic signs")
            if boolv(inputs.get("symptoms_metabolic_emergency")):
                detail.append("suspected metabolic emergency (e.g. DKA, HHS)")
            if boolv(inputs.get("symptoms_catabolic")) and not (
                boolv(inputs.get("symptoms_hyperglycemic"))
                or boolv(inputs.get("symptoms_weight_loss"))
                or boolv(inputs.get("symptoms_metabolic_emergency"))
            ):
                detail.append("severe hyperglycaemia symptoms (legacy combined flag)")
            if severe_hba1c:
                detail.append("HbA1c \u2265 9%")
            if severe_apg:
                detail.append(
                    "fasting / APG plasma glucose > 250 mg/dL "
                    "(FPG field after unit conversion)"
                )
            if severe_random:
                detail.append(
                    "random plasma glucose > 300 mg/dL "
                    "(optional random PG field after unit conversion)"
                )
            if detail:
                why_severe.append("Triggers: " + "; ".join(detail) + ".")
            if fpg_mg_dl is not None:
                comments.append(
                    f"FPG/APG entered: {fpg_mg_dl:.0f} mg/dL (equivalent after conversion)."
                )
            if random_mg_dl is not None:
                comments.append(
                    f"Random PG entered: {random_mg_dl:.0f} mg/dL "
                    "(equivalent after conversion)."
                )
            comments.append(
                "Evaluate for unrecognised type 1 diabetes or LADA where presentation suggests."
            )
            return {
                "therapy": "Start / intensify insulin (severe hyperglycaemia)",
                "why": why_severe,
                "next_steps": [
                    "TEMD §9.2.3: prefer basal–bolus insulin or premixed (biphasic) insulin; "
                    "continue metformin when not contraindicated.",
                    "Initiate SMBG or CGM; monitor ketones if indicated; ensure hypoglycaemia education.",
                    "Reassess once glucose toxicity improves; recheck HbA1c within ~3 months.",
                ],
                "comments": comments,
            }

    # ── Iraq branch ───────────────────────────────────────────────────────────
    if country == "IQ":
        # Simple binary band inputs replace numeric HbA1c/target/BMI for Iraq.
        band_mode = False
        hba1c_band = inputs.get("hba1c_band")
        bmi_band = inputs.get("bmi_band")
        if hba1c_band in ("lt2", "ge2"):
            band_mode = True
            below2 = hba1c_band == "lt2"
            diff = 1.0 if below2 else 2.5
            target_unmet = True
            if bmi_band == "le30":
                bmi = 28.0
            elif bmi_band == "gt30":
                bmi = 33.0
            else:
                bmi = None
        return _recommend_iq(inputs, diff, bmi, target_unmet, comments, band_mode)

    # ── Türkiye (TR) regimen and first injectable ───────────────────────────────

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
                if _tr_cardiometabolic_focus(inputs):
                    add_tr_frc_reimbursement_note(country, profile, bmi, comments)
                    _append_tr_cardiorenal_hints(comments, inputs)
                    comments.append(
                        "Optional non-reimbursed consideration: monotherapy GLP-1 RA "
                        "may be discussed if feasible out-of-pocket."
                    )
                    return {
                        "therapy": "Start FRC",
                        "why": [
                            "HbA1c is {:.1f}% above target, which is less than "
                            "2% above target.".format(diff),
                            "Despite BMI \u2264 30 kg/m\u00b2, TEMD 2024 (Şekil 9.4 / "
                            "individualised therapy) favours a GLP-1 RA–containing injectable "
                            "(FRC) given selected comorbidities over basal insulin alone "
                            "in this CDS layer.",
                        ],
                        "next_steps": [
                            "Initiate FRC and titrate according to local label.",
                            "Reassess HbA1c in 3 months.",
                        ],
                        "comments": comments,
                    }
                _append_tr_basal_quality_note(comments)
                return {
                    "therapy": "Start basal insulin",
                    "why": [
                        "HbA1c is {:.1f}% above target, which is less than "
                        "2% above target.".format(diff),
                        "BMI \u2264 30 kg/m\u00b2: basal insulin is the preferred "
                        "initial injectable choice when no cardiometabolic overrides apply.",
                    ],
                    "next_steps": [
                        "Initiate basal insulin and titrate to fasting glucose target.",
                        "Reassess HbA1c in 3 months.",
                    ],
                    "comments": comments,
                }
            if bmi is not None and bmi > 30:
                add_tr_frc_reimbursement_note(country, profile, bmi, comments)
                _append_tr_cardiorenal_hints(comments, inputs)
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
            if _tr_cardiometabolic_focus(inputs):
                add_tr_frc_reimbursement_note(country, profile, bmi, comments)
                _append_tr_cardiorenal_hints(comments, inputs)
                comments.append(
                    "Optional non-reimbursed consideration: monotherapy GLP-1 RA "
                    "may be discussed if feasible out-of-pocket."
                )
                return {
                    "therapy": "Start FRC",
                    "why": [
                        "HbA1c is {:.1f}% above target (less than 2% above target) but "
                        "BMI is unavailable.".format(diff),
                        "TEMD 2024 individualised therapy inputs suggest a GLP-1 RA–containing "
                        "injectable start (FRC) rather than basal insulin alone in this CDS layer.",
                    ],
                    "next_steps": [
                        "Initiate FRC and titrate according to local label.",
                        "Confirm BMI and reassess HbA1c in 3 months.",
                    ],
                    "comments": comments,
                }
            _append_tr_basal_quality_note(comments)
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
        _append_tr_cardiorenal_hints(comments, inputs)
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
        _append_tr_cardiorenal_hints(comments, inputs)
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
        if _tr_cardiometabolic_focus(inputs):
            add_tr_frc_reimbursement_note(country, profile, bmi, comments)
            _append_tr_cardiorenal_hints(comments, inputs)
            comments.append(
                "Optional non-reimbursed consideration: monotherapy GLP-1 RA "
                "may be discussed if feasible out-of-pocket."
            )
            return {
                "therapy": "Start FRC",
                "why": [
                    "Current HbA1c is not available; routing uses BMI with comorbidity context.",
                    "BMI \u2264 30 kg/m\u00b2 but TEMD 2024 individualised inputs favour a "
                    "GLP-1 RA–containing injectable (FRC).",
                ],
                "next_steps": [
                    "Initiate FRC and titrate according to local label.",
                    "Define individualised HbA1c target for follow-up.",
                ],
                "comments": comments,
            }
        _append_tr_basal_quality_note(comments)
        return {
            "therapy": "Start basal insulin",
            "why": [
                "Current HbA1c is not available; routing based on BMI only.",
                "BMI \u2264 30 kg/m\u00b2: basal insulin is the preferred "
                "conservative choice when no cardiometabolic overrides apply.",
            ],
            "next_steps": [
                "Initiate basal insulin and titrate to fasting glucose target.",
                "Define individualised HbA1c target for follow-up.",
            ],
            "comments": comments,
        }

    if _tr_cardiometabolic_focus(inputs):
        comments.append(
            "HbA1c and BMI insufficient; comorbidity-led start uses FRC "
            "(GLP-1 RA–containing injectable) per TEMD personalised layer."
        )
        _append_tr_cardiorenal_hints(comments, inputs)
        add_tr_frc_reimbursement_note(country, profile, bmi, comments)
        comments.append(
            "Optional non-reimbursed consideration: monotherapy GLP-1 RA "
            "may be discussed if feasible out-of-pocket."
        )
        return {
            "therapy": "Start FRC",
            "why": [
                "Current HbA1c and BMI are not sufficiently available; conservative default "
                "would be basal insulin, but comorbidity selections favour FRC in this tool.",
            ],
            "next_steps": [
                "Initiate FRC and titrate according to local label.",
                "Confirm BMI and current HbA1c urgently.",
            ],
            "comments": comments,
        }

    _append_tr_basal_quality_note(comments)
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
        # TR severe gate (not used for IQ — regimen-first)
        {
            "label": "TR | severe (HbA1c ≥9%)",
            "inputs": {"country": "TR", "hba1c": 9.0, "bmi": 33},
        },
        {
            "label": "IQ | BAND lt2 / le30 -> Basal (generic band phrasing)",
            "inputs": {"country": "IQ", "hba1c_band": "lt2", "bmi_band": "le30",
                       "iq_glp1_ra_access": True},
        },
        {
            "label": "IQ | BAND ge2 / gt30 -> BI + GLP-1 RA (generic band phrasing)",
            "inputs": {"country": "IQ", "hba1c_band": "ge2", "bmi_band": "gt30",
                       "iq_glp1_ra_access": True},
        },
        {
            "label": "IQ | regimen-first ignores catabolic + high FPG (no severe shortcut)",
            "inputs": {"country": "IQ", "hba1c": 8.0, "hba1c_target": 7.0, "bmi": 28,
                       "symptoms_catabolic": True,
                       "fpg": 16.7, "fpg_unit": "mmol_l",
                       "iq_glp1_ra_access": True},
        },
        {
            "label": "TR | severe (FPG/APG > 250 mg/dL)",
            "inputs": {"country": "TR", "hba1c": 8.0, "bmi": 28,
                       "fpg": 260, "fpg_unit": "mg_dl"},
        },
        {
            "label": "TR | severe (random PG > 300)",
            "inputs": {"country": "TR", "hba1c": 8.0, "bmi": 28,
                       "random_pg": 305, "random_pg_unit": "mg_dl"},
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
            "label": "IQ | on basal only <2% above -> titrate + add GLP-1 RA",
            "inputs": {"country": "IQ", "hba1c": 7.8,
                       "hba1c_target": 7.0, "bmi": 28,
                       "on_basal_only": True,
                       "iq_glp1_ra_access": True},
        },
        {
            "label": "IQ | on GLP-1 alone <2% above -> optimise GLP-1 + add basal",
            "inputs": {"country": "IQ", "hba1c": 7.7,
                       "hba1c_target": 7.0, "bmi": 26,
                       "on_glp1_alone": True,
                       "iq_glp1_ra_access": True},
        },
        {
            "label": "IQ | on premix, unmet -> transition to FRC / basal-bolus",
            "inputs": {"country": "IQ", "hba1c": 9.0,
                       "hba1c_target": 7.0, "bmi": 30,
                       "on_premix": True,
                       "iq_glp1_ra_access": True},
        },
        {
            "label": "IQ | on basal-bolus, unmet -> transition to FRC (premix alt)",
            "inputs": {"country": "IQ", "hba1c": 9.0,
                       "hba1c_target": 7.0, "bmi": 30,
                       "on_basal_bolus": True,
                       "iq_glp1_ra_access": True},
        },
        {
            "label": "IQ | on basal-bolus, irregular -> transition to FRC only (no premix)",
            "inputs": {"country": "IQ", "hba1c": 9.0,
                       "hba1c_target": 7.0, "bmi": 30,
                       "on_basal_bolus": True,
                       "irregular_meal_patterns": True,
                       "iq_glp1_ra_access": True},
        },
        {
            "label": "IQ | on premix, HbA1c missing -> still routes to simplify (no fall-through)",
            "inputs": {"country": "IQ", "bmi": 33,
                       "on_premix": True,
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
            "label": "IQ | on BI(max)+GLP-1+Rapid, unmet, regular -> basal-bolus + premix alt",
            "inputs": {"country": "IQ", "hba1c": 9.0,
                       "hba1c_target": 7.0, "bmi": 31,
                       "on_bi_glp1_rapid": True,
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
            "label": "TR | first <2%, BMI≤30 + ASCVD -> FRC override",
            "inputs": {"country": "TR", "hba1c": 8.6,
                       "hba1c_target": 7.0, "bmi": 28,
                       "tr_ascvd": True},
        },
        {
            "label": "TR | first, >=2% above target, HbA1c<9% -> FRC",
            "inputs": {"country": "TR", "hba1c": 8.8,
                       "hba1c_target": 6.5, "bmi": 27},
        },
    ]

    sep = "-" * 72
    for tc in TEST_CASES:
        if tc["inputs"].get("country") == "TR" and not TR_ENABLED:
            print(sep)
            print(f"TEST       : {tc['label']}")
            print("Result     : [skipped: TR legacy]")
            continue
        r = recommend(tc["inputs"])
        print(sep)
        print(f"TEST       : {tc['label']}")
        print(f"Therapy    : {r['therapy']}")
        print(f"Why        : {r['why']}")
        print(f"Next steps : {r['next_steps']}")
        if r.get("comments"):
            print(f"Comments   : {r['comments']}")
    print(sep)
