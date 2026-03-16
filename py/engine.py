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

def _iq_base_comments():
    return [IQ_GLP1_NOTE, IQ_BI_NOTE, IQ_PREMIX_NOTE]


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

    comments.extend(_iq_base_comments())

    def result(therapy, why, next_steps):
        return {
            "therapy": therapy,
            "why": why,
            "next_steps": next_steps,
            "comments": comments,
        }

    # ── Step 3: BI(max)+GLP-1+Rapid still unmet ─────────────────────────────
    if on_bi_glp1_rapid and target_unmet:
        return result(
            therapy="Intensify insulin: basal-bolus OR premixed insulin",
            why=[
                "HbA1c target remains unmet on BI (max dose) + GLP-1 RA "
                "+ rapid-acting insulin.",
                "Further insulin intensification is warranted "
                "(Iraq algorithm step 3).",
            ],
            next_steps=[
                "Option A – Basal-bolus: optimise basal dose + add / titrate "
                "rapid-acting insulin before each main meal.",
                "Option B – Premixed insulin: twice-daily premixed regimen as "
                "a simpler alternative when resources or patient complexity favour it.",
                "Reassess HbA1c in 3 months after regimen change.",
                "Ensure structured SMBG or CGM where available.",
            ],
        )

    # ── Step 2: BI+GLP-1 or GLP-1 alone still unmet → add rapid ─────────────
    if on_bi_glp1 and target_unmet:
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

    if on_glp1_alone and target_unmet:
        return result(
            therapy="BI (max dose) + GLP-1 RA + Rapid-acting insulin",
            why=[
                "HbA1c target remains unmet on GLP-1 RA alone.",
                "Iraq algorithm: add basal insulin (titrate to max) "
                "and rapid-acting insulin.",
            ],
            next_steps=[
                "Add basal insulin (2nd-generation preferred) and titrate "
                "to fasting glucose target.",
                "Add rapid-acting insulin at the largest meal; titrate on "
                "postprandial glucose.",
                "Reassess HbA1c in 3 months.",
            ],
        )

    # ── Step 1: basal-only still unmet → BI + GLP-1 RA ──────────────────────
    if on_basal_only and target_unmet:
        return result(
            therapy="BI + GLP-1 RA (FRC preferably, or separately)",
            why=[
                "HbA1c target remains unmet on basal insulin alone.",
                "Iraq algorithm: escalate to BI + GLP-1 RA combination.",
            ],
            next_steps=[
                "Preferred: switch to FRC (iDegLira or iGlarLixi) for "
                "simplicity and better GI tolerability.",
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
                return result(
                    therapy="Basal insulin & titration",
                    why=[
                        _above_target_str(diff) + ", which is less than 2% above target.",
                        "BMI \u2264 30 kg/m\u00b2: basal insulin is the recommended "
                        "first injectable (Iraq algorithm, step 0).",
                    ],
                    next_steps=[
                        "Initiate 2nd-generation basal insulin "
                        "(e.g. degludec or glargine U-300).",
                        "Titrate to fasting glucose target.",
                        "Reassess HbA1c in 3 months; if still above target, "
                        "escalate to BI + GLP-1 RA (FRC preferably or separately).",
                    ],
                )

            if bmi is not None and bmi > 30:
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
                        "FRC option: iDegLira or iGlarLixi (single pen, once daily).",
                        "Reassess HbA1c in 3 months; if still above target, escalate "
                        "to BI (max) + GLP-1 RA + rapid-acting insulin.",
                    ],
                )

            # BMI unknown
            comments.append(
                "BMI not provided; conservative basal-insulin-first choice used. "
                "If BMI > 30, GLP-1 RA alone or BI + GLP-1 RA "
                "(FRC or separately) may be preferred."
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
            return result(
                therapy="BI + GLP-1 RA (FRC or separately)  —  or Premix agents\u266f",
                why=[
                    _above_target_str(diff) + ", which is 2% or more above target.",
                    "BMI \u2264 30 kg/m\u00b2: combination BI + GLP-1 RA is recommended "
                    "from initiation; premix agents are an alternative if other options "
                    "are inaccessible locally (Iraq algorithm, step 0).",
                ],
                next_steps=[
                    "Preferred: FRC (iDegLira or iGlarLixi) — single pen, once daily.",
                    "Alternative: separate basal insulin + GLP-1 RA injections.",
                    "Premix alternative (\u266f): if FRC and GLP-1 RA are not "
                    "accessible locally.",
                    "Reassess HbA1c in 3 months; if still above target, escalate "
                    "to BI (max) + GLP-1 RA + rapid-acting insulin.",
                ],
            )

        if bmi is not None and bmi > 30:
            return result(
                therapy="BI + GLP-1 RA (FRC or separately)",
                why=[
                    _above_target_str(diff) + ", which is 2% or more above target.",
                    "BMI > 30 kg/m\u00b2: combination BI + GLP-1 RA is recommended "
                    "from initiation (Iraq algorithm, step 0).",
                ],
                next_steps=[
                    "Preferred: FRC (iDegLira or iGlarLixi) — single pen, once daily.",
                    "Alternative: separate basal insulin + GLP-1 RA injections.",
                    "Reassess HbA1c in 3 months; if still above target, escalate "
                    "to BI (max) + GLP-1 RA + rapid-acting insulin.",
                ],
            )

        # BMI unknown, 2% or more above target
        comments.append(
            "BMI not provided; BI + GLP-1 RA combination recommended "
            "when HbA1c is 2% or more above target (Iraq algorithm)."
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
                "Preferred: FRC (iDegLira or iGlarLixi).",
                "Alternative: separate basal insulin + GLP-1 RA.",
                "Reassess HbA1c in 3 months.",
            ],
        )

    # ── HbA1c missing — BMI fallback ─────────────────────────────────────────
    comments.append(
        "HbA1c not provided; routing based on BMI only."
    )

    if bmi is not None and bmi > 30:
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
    severe = symptoms_catabolic or (hba1c is not None and hba1c >= 10)
    if severe:
        return {
            "therapy": "Start / intensify insulin (severe hyperglycaemia)",
            "why": [
                "Catabolic symptoms or HbA1c \u2265 10% require rapid "
                "insulin-based control."
            ],
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
    TEST_CASES = [
        # Shared gate
        {
            "label": "TR | severe (HbA1c 10.5)",
            "inputs": {"country": "TR", "hba1c": 10.5, "bmi": 33},
        },
        {
            "label": "IQ | severe (catabolic)",
            "inputs": {"country": "IQ", "hba1c": 9.8, "bmi": 29,
                       "symptoms_catabolic": True},
        },
        # IQ first injectable
        {
            "label": "IQ | <2% above target, BMI<=30 -> Basal",
            "inputs": {"country": "IQ", "hba1c": 7.8,
                       "hba1c_target": 7.0, "bmi": 28},
        },
        {
            "label": "IQ | <2% above target, BMI>30 -> GLP-1 RA or BI+GLP-1",
            "inputs": {"country": "IQ", "hba1c": 8.5,
                       "hba1c_target": 7.0, "bmi": 34},
        },
        {
            "label": "IQ | >=2% above target, BMI<=30 -> BI+GLP-1 or Premix",
            "inputs": {"country": "IQ", "hba1c": 9.5,
                       "hba1c_target": 7.0, "bmi": 27},
        },
        {
            "label": "IQ | >=2% above target, BMI>30 -> BI+GLP-1",
            "inputs": {"country": "IQ", "hba1c": 9.5,
                       "hba1c_target": 7.0, "bmi": 33},
        },
        # IQ intensification ladder
        {
            "label": "IQ | on basal only, unmet -> BI+GLP-1",
            "inputs": {"country": "IQ", "hba1c": 8.2,
                       "hba1c_target": 7.0, "bmi": 28,
                       "on_basal_only": True},
        },
        {
            "label": "IQ | on GLP-1 alone, unmet -> BI(max)+GLP-1+Rapid",
            "inputs": {"country": "IQ", "hba1c": 8.4,
                       "hba1c_target": 7.0, "bmi": 35,
                       "on_glp1_alone": True},
        },
        {
            "label": "IQ | on BI+GLP-1, unmet -> BI(max)+GLP-1+Rapid",
            "inputs": {"country": "IQ", "hba1c": 8.6,
                       "hba1c_target": 7.0, "bmi": 31,
                       "on_bi_glp1": True},
        },
        {
            "label": "IQ | on BI(max)+GLP-1+Rapid, unmet -> BB or Premix",
            "inputs": {"country": "IQ", "hba1c": 9.0,
                       "hba1c_target": 7.0, "bmi": 31,
                       "on_bi_glp1_rapid": True},
        },
        # IQ no target provided
        {
            "label": "IQ | no target, default 7.0, >=2% above, BMI>30",
            "inputs": {"country": "IQ", "hba1c": 9.1, "bmi": 33},
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
