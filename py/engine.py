import json

# ======================
# Country configuration
# ======================

COUNTRIES = {
    "TR": {"frc": True, "label": "Turkey", "tr_bmi_threshold": 35},
    "IQ": {"frc": True, "label": "Iraq"},
}


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


def add_tr_frc_reimbursement_note(country, profile, bmi, comments):
    if country == "TR" and bmi is not None and bmi < profile.get("tr_bmi_threshold", 35):
        comments.append(
            "Turkey: reimbursement for FRC may be limited when BMI < 35; "
            "treatment may be out-of-pocket depending on local access conditions."
        )


# ══════════════════════════════════════════════════════════════════════════════
#  IRAQ-SPECIFIC NOTES  (appended to comments, never change therapy decision)
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


def _iq_base_comments():
    """Return the three standing Iraq footnotes."""
    return [IQ_GLP1_NOTE, IQ_BI_NOTE, IQ_PREMIX_NOTE]


# ══════════════════════════════════════════════════════════════════════════════
#  IRAQ ALGORITHM
#
#  Regimen states (mutually exclusive radio in the UI, mapped to booleans here):
#    on_basal_only   – basal insulin alone, no GLP-1 RA yet
#    on_glp1_alone   – GLP-1 RA alone (gap<2 / BMI>30 first step)
#    on_bi_glp1      – BI + GLP-1 RA (FRC or separately), BI not yet at max
#    on_bi_glp1_rapid– BI (max dose) + GLP-1 RA + rapid-acting insulin
#    on_bb           – basal-bolus
#    on_premix       – premixed insulin
#
#  Intensification ladder (mirrors the image top-to-bottom):
#
#  GAP < 2%, BMI ≤ 30
#    Step 0 → Basal insulin & titration
#    Step 1 → BI + GLP-1 RA (FRC preferably or separately)
#    Step 2 → BI (max) + GLP-1 RA + Rapid
#    Step 3 → BB or Premix
#
#  GAP < 2%, BMI > 30
#    Step 0 → GLP-1 RA alone  OR  BI + GLP-1 RA (FRC or separately)
#    Step 1 → BI (max) + GLP-1 RA + Rapid          [same as step 2 above]
#    Step 2 → BB or Premix
#
#  GAP ≥ 2%, BMI ≤ 30
#    Step 0 → BI + GLP-1 RA (FRC or separately)  OR  Premix agents
#    Step 1 → BI (max) + GLP-1 RA + Rapid
#    Step 2 → BB or Premix
#
#  GAP ≥ 2%, BMI > 30
#    Step 0 → BI + GLP-1 RA (FRC or separately)
#    Step 1 → BI (max) + GLP-1 RA + Rapid
#    Step 2 → BB or Premix
# ══════════════════════════════════════════════════════════════════════════════

def _recommend_iq(inputs, gap, bmi, target_unmet, comments):
    """
    Iraq-specific routing.
    `gap`          – float or None  (hba1c − effective_target)
    `bmi`          – float or None
    `target_unmet` – bool
    `comments`     – list, already seeded with default-target note if applicable;
                     Iraq standing footnotes are appended here.
    Returns a standard result dict.
    """

    # ── Regimen flags ────────────────────────────────────────────────────────
    on_basal_only    = boolv(inputs.get("on_basal_only"))
    on_glp1_alone    = boolv(inputs.get("on_glp1_alone"))
    on_bi_glp1       = boolv(inputs.get("on_bi_glp1"))
    on_bi_glp1_rapid = boolv(inputs.get("on_bi_glp1_rapid"))
    on_bb            = boolv(inputs.get("on_basal_bolus"))
    on_premix        = boolv(inputs.get("on_premix"))

    # Append standing Iraq footnotes once
    comments.extend(_iq_base_comments())

    # ── Helpers ──────────────────────────────────────────────────────────────
    def result(therapy, why, next_steps):
        return {
            "therapy": therapy,
            "why": why,
            "next_steps": next_steps,
            "comments": comments,
        }

    # ════════════════════════════════════════════════════════════════════════
    # STEP 3 / FINAL INTENSIFICATION
    # Already on BI (max) + GLP-1 RA + Rapid and still above target
    # ════════════════════════════════════════════════════════════════════════
    if on_bi_glp1_rapid and target_unmet:
        return result(
            therapy="Intensify insulin: basal-bolus OR premixed insulin",
            why=[
                "HbA1c target remains unmet on BI (max dose) + GLP-1 RA + rapid-acting insulin.",
                "Further insulin intensification / optimisation is warranted (Iraq algorithm step 3).",
            ],
            next_steps=[
                "Option A – Basal-bolus: optimise basal dose + add / titrate rapid-acting insulin "
                "before each main meal.",
                "Option B – Premixed insulin: twice-daily premixed regimen as a simpler alternative "
                "when resources or patient complexity favour it.",
                "Reassess HbA1c in 3 months after regimen change.",
                "Ensure structured SMBG or CGM where available.",
            ],
        )

    # ════════════════════════════════════════════════════════════════════════
    # STEP 2  –  Add rapid-acting insulin
    # Triggered when:
    #   • on_basal_only AND target unmet  (gap<2 / BMI≤30 ladder, step 1→2)
    #     BUT only after BI+GLP-1 has already been tried — represented by
    #     on_bi_glp1 flag.
    #   • on_glp1_alone AND target unmet  (gap<2 / BMI>30 ladder)
    #   • on_bi_glp1    AND target unmet  (all gap≥2 ladders, and gap<2/BMI>30)
    # ════════════════════════════════════════════════════════════════════════
    if on_bi_glp1 and target_unmet:
        return result(
            therapy="BI (max dose) + GLP-1 RA + Rapid-acting insulin",
            why=[
                "HbA1c target remains unmet on BI + GLP-1 RA combination.",
                "Iraq algorithm: intensify by maximising basal insulin dose and adding "
                "rapid-acting insulin.",
            ],
            next_steps=[
                "Titrate basal insulin to its maximum tolerated / labelled dose.",
                "Add rapid-acting insulin starting with the largest meal (basal-plus approach).",
                "Titrate prandial dose on postprandial glucose readings.",
                "If further injections needed, add stepwise before remaining meals.",
                "Reassess HbA1c in 3 months.",
            ],
        )

    if on_glp1_alone and target_unmet:
        return result(
            therapy="BI (max dose) + GLP-1 RA + Rapid-acting insulin",
            why=[
                "HbA1c target remains unmet on GLP-1 RA alone.",
                "Iraq algorithm: add basal insulin (titrate to max) and rapid-acting insulin.",
            ],
            next_steps=[
                "Add basal insulin (2nd-generation preferred) and titrate to fasting glucose target.",
                "Add rapid-acting insulin at the largest meal; titrate on postprandial glucose.",
                "Reassess HbA1c in 3 months.",
            ],
        )

    # ════════════════════════════════════════════════════════════════════════
    # STEP 1  –  Escalate basal-only to BI + GLP-1 RA
    # (gap < 2%, BMI ≤ 30 ladder only — patient started on basal insulin alone)
    # ════════════════════════════════════════════════════════════════════════
    if on_basal_only and target_unmet:
        return result(
            therapy="BI + GLP-1 RA (FRC preferably, or separately)",
            why=[
                "HbA1c target remains unmet on basal insulin alone.",
                "Iraq algorithm (gap < 2%, BMI ≤ 30): escalate to BI + GLP-1 RA combination.",
            ],
            next_steps=[
                "Preferred: switch to FRC (iDegLira or iGlarLixi) for simplicity and "
                "better GI tolerability.",
                "Alternative: add GLP-1 RA as a separate injection alongside current basal insulin.",
                "Titrate according to local label and glucose response.",
                "Reassess HbA1c in 3 months.",
            ],
        )

    # ════════════════════════════════════════════════════════════════════════
    # FIRST INJECTABLE SELECTION
    # Requires gap to be calculable; if not, fall through to BMI fallback.
    # ════════════════════════════════════════════════════════════════════════
    if gap is not None:

        # ── GAP < 2% ────────────────────────────────────────────────────────
        if gap < 2.0:

            # BMI ≤ 30  →  Basal insulin & titration
            if bmi is not None and bmi <= 30:
                return result(
                    therapy="Basal insulin & titration",
                    why=[
                        f"HbA1c gap {gap:.1f}% is < 2% above target.",
                        "BMI ≤ 30 kg/m²: basal insulin is the recommended first injectable "
                        "(Iraq algorithm, step 0).",
                    ],
                    next_steps=[
                        "Initiate 2nd-generation basal insulin (e.g. degludec or glargine U-300).",
                        "Titrate to fasting glucose target.",
                        "Reassess HbA1c in 3 months; if still above target, escalate to "
                        "BI + GLP-1 RA (FRC preferably or separately).",
                    ],
                )

            # BMI > 30  →  GLP-1 RA alone  OR  BI + GLP-1 RA (FRC or separately)
            if bmi is not None and bmi > 30:
                return result(
                    therapy="GLP-1 RA alone  OR  BI + GLP-1 RA (FRC or separately)",
                    why=[
                        f"HbA1c gap {gap:.1f}% is < 2% above target.",
                        "BMI > 30 kg/m²: GLP-1 RA alone is preferred; "
                        "BI + GLP-1 RA (FRC or separately) is an alternative "
                        "(Iraq algorithm, step 0).",
                    ],
                    next_steps=[
                        "First choice: initiate GLP-1 RA alone; titrate per label.",
                        "If fasting glucose remains elevated, add basal insulin or switch to FRC.",
                        "FRC option: iDegLira or iGlarLixi (single pen, once daily).",
                        "Reassess HbA1c in 3 months; if still above target, escalate to "
                        "BI (max) + GLP-1 RA + rapid-acting insulin.",
                    ],
                )

            # BMI unknown
            comments.append(
                "BMI not provided; conservative basal-insulin-first choice used. "
                "If BMI > 30, GLP-1 RA alone or BI + GLP-1 RA (FRC or separately) may be preferred."
            )
            return result(
                therapy="Basal insulin & titration (BMI unknown)",
                why=[
                    f"HbA1c gap {gap:.1f}% is < 2% above target.",
                    "BMI is unavailable; conservative basal-insulin-first approach used.",
                ],
                next_steps=[
                    "Confirm BMI to refine the choice.",
                    "Initiate 2nd-generation basal insulin and titrate to fasting glucose target.",
                    "Reassess HbA1c in 3 months.",
                ],
            )

        # ── GAP ≥ 2% ────────────────────────────────────────────────────────

        # BMI ≤ 30  →  BI + GLP-1 RA (FRC or separately)  OR  Premix agents
        if bmi is not None and bmi <= 30:
            return result(
                therapy="BI + GLP-1 RA (FRC or separately)  —  or Premix agents\u266f",
                why=[
                    f"HbA1c gap {gap:.1f}% is ≥ 2% above target.",
                    "BMI ≤ 30 kg/m²: combination BI + GLP-1 RA is recommended from initiation; "
                    "premix agents are an alternative if other options are inaccessible locally "
                    "(Iraq algorithm, step 0).",
                ],
                next_steps=[
                    "Preferred: FRC (iDegLira or iGlarLixi) — single pen, once daily.",
                    "Alternative: separate basal insulin + GLP-1 RA injections.",
                    "Premix alternative (\u266f): if FRC and GLP-1 RA are not accessible locally.",
                    "Reassess HbA1c in 3 months; if still above target, escalate to "
                    "BI (max) + GLP-1 RA + rapid-acting insulin.",
                ],
            )

        # BMI > 30  →  BI + GLP-1 RA (FRC or separately)
        if bmi is not None and bmi > 30:
            return result(
                therapy="BI + GLP-1 RA (FRC or separately)",
                why=[
                    f"HbA1c gap {gap:.1f}% is ≥ 2% above target.",
                    "BMI > 30 kg/m²: combination BI + GLP-1 RA is recommended from initiation "
                    "(Iraq algorithm, step 0).",
                ],
                next_steps=[
                    "Preferred: FRC (iDegLira or iGlarLixi) — single pen, once daily.",
                    "Alternative: separate basal insulin + GLP-1 RA injections.",
                    "Reassess HbA1c in 3 months; if still above target, escalate to "
                    "BI (max) + GLP-1 RA + rapid-acting insulin.",
                ],
            )

        # BMI unknown, gap ≥ 2%
        comments.append(
            "BMI not provided; BI + GLP-1 RA combination recommended regardless of BMI "
            "when gap ≥ 2% (Iraq algorithm)."
        )
        return result(
            therapy="BI + GLP-1 RA (FRC or separately)",
            why=[
                f"HbA1c gap {gap:.1f}% is ≥ 2% above target.",
                "BMI unavailable; combination BI + GLP-1 RA recommended across all BMI "
                "categories at this gap level.",
            ],
            next_steps=[
                "Confirm BMI to refine the choice.",
                "Preferred: FRC (iDegLira or iGlarLixi).",
                "Alternative: separate basal insulin + GLP-1 RA.",
                "Reassess HbA1c in 3 months.",
            ],
        )

    # ════════════════════════════════════════════════════════════════════════
    # GAP CANNOT BE CALCULATED  (HbA1c missing)
    # ════════════════════════════════════════════════════════════════════════
    comments.append(
        "HbA1c not provided; gap-based routing unavailable. "
        "Recommendation based on BMI only."
    )

    if bmi is not None and bmi > 30:
        return result(
            therapy="GLP-1 RA alone  OR  BI + GLP-1 RA (FRC or separately)",
            why=[
                "Current HbA1c unavailable; gap cannot be calculated.",
                "BMI > 30 kg/m²: GLP-1 RA-containing strategy preferred.",
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
            "Current HbA1c unavailable; gap cannot be calculated.",
            "BMI ≤ 30 kg/m² or unknown: conservative basal-insulin-first approach.",
        ],
        next_steps=[
            "Obtain current HbA1c and individualised target to confirm routing.",
            "Initiate 2nd-generation basal insulin and titrate to fasting glucose target.",
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

    # ── Numeric inputs ───────────────────────────────────────────────────────
    hba1c        = num(inputs.get("hba1c"))
    hba1c_target = num(inputs.get("hba1c_target"))
    bmi          = num(inputs.get("bmi"))

    # ── Regimen flags (shared) ───────────────────────────────────────────────
    # Turkey uses the legacy radio set; Iraq uses its own extended set.
    # Legacy flags kept for Turkey compatibility:
    on_basal   = boolv(inputs.get("on_basal_insulin"))
    on_bb      = boolv(inputs.get("on_basal_bolus"))
    on_premix  = boolv(inputs.get("on_premix"))
    on_frc     = boolv(inputs.get("on_frc"))
    on_rapid   = boolv(inputs.get("on_rapid_added"))

    # ── Clinical flags ───────────────────────────────────────────────────────
    symptoms_catabolic     = boolv(inputs.get("symptoms_catabolic"))
    recurrent_hypoglycemia = boolv(inputs.get("recurrent_hypoglycemia"))
    ppg_uncontrolled       = boolv(inputs.get("ppg_uncontrolled"))

    # ── Effective HbA1c target ───────────────────────────────────────────────
    effective_target = hba1c_target
    if effective_target is None and hba1c is not None:
        effective_target = 7.0

    # ── Gap & target_unmet ───────────────────────────────────────────────────
    if hba1c is not None and effective_target is not None:
        target_unmet = hba1c > effective_target
        gap = hba1c - effective_target
    else:
        target_unmet = False
        gap = None

    frc = profile["frc"]

    comments = []
    if hba1c is not None and hba1c_target is None:
        comments.append(
            "HbA1c target was not provided; default target of 7.0% was used."
        )

    # ════════════════════════════════════════════════════════════════════════
    # SHARED GATE — Severe hyperglycaemia (all countries)
    # ════════════════════════════════════════════════════════════════════════
    severe = symptoms_catabolic or (hba1c is not None and hba1c >= 10)
    if severe:
        return {
            "therapy": "Start / intensify insulin (severe hyperglycaemia)",
            "why": [
                "Catabolic symptoms or HbA1c ≥ 10% require rapid insulin-based control."
            ],
            "next_steps": [
                "Initiate or intensify insulin with close monitoring.",
                "Reassess regimen after initial stabilisation.",
            ],
            "comments": comments,
        }

    # ════════════════════════════════════════════════════════════════════════
    # IRAQ  —  fully self-contained branch
    # ════════════════════════════════════════════════════════════════════════
    if country == "IQ":
        return _recommend_iq(inputs, gap, bmi, target_unmet, comments)

    # ════════════════════════════════════════════════════════════════════════
    # TURKEY  —  original logic, unchanged
    # ════════════════════════════════════════════════════════════════════════

    # 2. On FRC + rapid insulin + target still unmet
    if on_frc and on_rapid and target_unmet:
        return {
            "therapy": "Intensify to basal-bolus regimen OR premixed insulin",
            "why": [
                "Glycaemic target remains unmet despite FRC plus rapid-acting insulin.",
                "Further intensification is warranted.",
            ],
            "next_steps": [
                "Basal-bolus: continue basal insulin + add rapid-acting insulin before additional meals.",
                "Premixed insulin: consider when a simpler multidose insulin regimen is preferable.",
                "Reassess HbA1c in 3 months.",
                "Ensure SMBG or CGM where available.",
            ],
            "comments": comments,
        }

    # 3. On FRC + target still unmet
    if on_frc and target_unmet:
        comments.append(
            "Adding rapid-acting insulin to FRC may be off-label depending on local label and market."
        )
        return {
            "therapy": "Add rapid-acting insulin to FRC",
            "why": [
                "Glycaemic target remains unmet on FRC.",
                "Prandial coverage may be needed as the next intensification step.",
            ],
            "next_steps": [
                "Start with 1 prandial injection at the largest meal.",
                "If needed, intensify stepwise to additional meals.",
                "Reassess HbA1c in 3 months.",
                "Review local label / internal policy because this approach may be off-label.",
            ],
            "comments": comments,
        }

    # 4. On basal-bolus or premix + recurrent hypoglycaemia
    if (on_bb or on_premix) and recurrent_hypoglycemia:
        if frc:
            add_tr_frc_reimbursement_note(country, profile, bmi, comments)
            return {
                "therapy": "Consider switch to FRC for simplification",
                "why": [
                    "Recurrent hypoglycaemia on basal-bolus or premixed insulin supports simplification."
                ],
                "next_steps": [
                    "Review current insulin doses and switching approach.",
                    "Initiate FRC and titrate according to local label.",
                    "Reassess glucose patterns after switch.",
                ],
                "comments": comments,
            }

    # 5. On basal insulin + target unmet or PPG uncontrolled
    if on_basal and (target_unmet or ppg_uncontrolled):
        if frc:
            add_tr_frc_reimbursement_note(country, profile, bmi, comments)
            why = []
            if target_unmet:
                why.append("HbA1c remains above target on basal insulin.")
            if ppg_uncontrolled:
                why.append("Postprandial glucose remains uncontrolled on basal insulin.")
            why.append(
                "FRC can address both fasting and postprandial glucose in one injectable strategy."
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

    # 6. First injectable — gap-based
    if gap is not None:
        if gap < 2.0:
            if bmi is not None and bmi <= 30:
                return {
                    "therapy": "Start basal insulin",
                    "why": [
                        f"HbA1c gap {gap:.1f}% is < 2% above target.",
                        "BMI ≤ 30 kg/m²: basal insulin is the preferred initial injectable choice.",
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
                    "Optional non-reimbursed consideration: standalone GLP-1 RA may be "
                    "discussed if feasible out-of-pocket."
                )
                return {
                    "therapy": "Start FRC",
                    "why": [
                        f"HbA1c gap {gap:.1f}% is < 2% above target.",
                        "BMI > 30 kg/m²: FRC is preferred as the reimbursed incretin-containing path.",
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
                    f"HbA1c gap {gap:.1f}% is < 2% above target.",
                    "BMI is unavailable, so a conservative basal-insulin-first choice is used.",
                ],
                "next_steps": [
                    "Confirm BMI if possible.",
                    "Initiate basal insulin and titrate to fasting glucose target.",
                    "Reassess HbA1c in 3 months.",
                ],
                "comments": comments,
            }

        # gap >= 2%
        add_tr_frc_reimbursement_note(country, profile, bmi, comments)
        comments.append(
            "Optional non-reimbursed consideration: GLP-1 RA-based strategy may be "
            "discussed if feasible out-of-pocket."
        )
        return {
            "therapy": "Start FRC",
            "why": [
                f"HbA1c gap {gap:.1f}% is ≥ 2% above target.",
                "FRC is preferred as the reimbursed combination path from initiation.",
            ],
            "next_steps": [
                "Initiate FRC and titrate according to local label.",
                "Reassess HbA1c in 3 months.",
            ],
            "comments": comments,
        }

    # 6B. Fallback — HbA1c missing
    if bmi is not None and bmi > 30:
        add_tr_frc_reimbursement_note(country, profile, bmi, comments)
        comments.append(
            "Optional non-reimbursed consideration: standalone GLP-1 RA may be "
            "discussed if feasible out-of-pocket."
        )
        return {
            "therapy": "Start FRC",
            "why": [
                "HbA1c gap cannot be calculated because current HbA1c is not available.",
                "BMI > 30 kg/m²: FRC is preferred.",
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
                "HbA1c gap cannot be calculated because current HbA1c is not available.",
                "BMI ≤ 30 kg/m²: basal insulin is the preferred conservative choice.",
            ],
            "next_steps": [
                "Initiate basal insulin and titrate to fasting glucose target.",
                "Define individualised HbA1c target for follow-up.",
            ],
            "comments": comments,
        }

    comments.append(
        "Recommendation made conservatively because current HbA1c and BMI were not fully available. "
        "If BMI > 30, FRC may be preferred."
    )
    return {
        "therapy": "Start basal insulin",
        "why": [
            "Current HbA1c and BMI are not sufficiently available for more specific routing; "
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
    TEST_CASES = [
        # ── Shared gate ──────────────────────────────────────────────────────
        {
            "label": "TR | severe hyperglycaemia (HbA1c ≥10)",
            "inputs": {"country": "TR", "hba1c": 10.5, "bmi": 33},
        },
        {
            "label": "IQ | severe hyperglycaemia (catabolic)",
            "inputs": {"country": "IQ", "hba1c": 9.8, "bmi": 29,
                       "symptoms_catabolic": True},
        },
        # ── IQ first injectable ──────────────────────────────────────────────
        {
            "label": "IQ | gap<2, BMI≤30 → Basal insulin & titration",
            "inputs": {"country": "IQ", "hba1c": 7.8, "hba1c_target": 7.0, "bmi": 28},
        },
        {
            "label": "IQ | gap<2, BMI>30 → GLP-1 RA alone or BI+GLP-1 RA",
            "inputs": {"country": "IQ", "hba1c": 8.5, "hba1c_target": 7.0, "bmi": 34},
        },
        {
            "label": "IQ | gap≥2, BMI≤30 → BI+GLP-1 RA or Premix",
            "inputs": {"country": "IQ", "hba1c": 9.5, "hba1c_target": 7.0, "bmi": 27},
        },
        {
            "label": "IQ | gap≥2, BMI>30 → BI+GLP-1 RA (FRC or separately)",
            "inputs": {"country": "IQ", "hba1c": 9.5, "hba1c_target": 7.0, "bmi": 33},
        },
        # ── IQ intensification ladder ────────────────────────────────────────
        {
            "label": "IQ | on basal only, target unmet → BI+GLP-1 RA",
            "inputs": {"country": "IQ", "hba1c": 8.2, "hba1c_target": 7.0,
                       "bmi": 28, "on_basal_only": True},
        },
        {
            "label": "IQ | on GLP-1 alone, target unmet → BI(max)+GLP-1+Rapid",
            "inputs": {"country": "IQ", "hba1c": 8.4, "hba1c_target": 7.0,
                       "bmi": 35, "on_glp1_alone": True},
        },
        {
            "label": "IQ | on BI+GLP-1, target unmet → BI(max)+GLP-1+Rapid",
            "inputs": {"country": "IQ", "hba1c": 8.6, "hba1c_target": 7.0,
                       "bmi": 31, "on_bi_glp1": True},
        },
        {
            "label": "IQ | on BI(max)+GLP-1+Rapid, target unmet → BB or Premix",
            "inputs": {"country": "IQ", "hba1c": 9.0, "hba1c_target": 7.0,
                       "bmi": 31, "on_bi_glp1_rapid": True},
        },
        # ── IQ no target provided ────────────────────────────────────────────
        {
            "label": "IQ | no target, gap≥2 (default 7.0), BMI>30 → BI+GLP-1 RA",
            "inputs": {"country": "IQ", "hba1c": 9.1, "bmi": 33},
        },
        # ── Turkey (unchanged) ───────────────────────────────────────────────
        {
            "label": "TR | BB + recurrent hypo → switch to FRC",
            "inputs": {"country": "TR", "hba1c": 7.8, "bmi": 32,
                       "on_basal_bolus": True, "recurrent_hypoglycemia": True},
        },
        {
            "label": "TR | basal + PPG uncontrolled → FRC",
            "inputs": {"country": "TR", "hba1c": 7.1, "hba1c_target": 7.0,
                       "bmi": 29, "on_basal_insulin": True, "ppg_uncontrolled": True},
        },
        {
            "label": "TR | first injectable, gap<2, BMI>30 → FRC + reimbursement note",
            "inputs": {"country": "TR", "hba1c": 8.2, "hba1c_target": 7.0, "bmi": 32},
        },
        {
            "label": "TR | first injectable, gap≥2 → FRC",
            "inputs": {"country": "TR", "hba1c": 9.4, "hba1c_target": 7.0, "bmi": 27},
        },
    ]

    sep = "─" * 72
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
