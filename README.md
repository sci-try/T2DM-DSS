# T2D Injectable Therapy CDS (Pyodide / GitHub Pages)

Country-adaptive clinical decision support (prototype) for adults with **type 2 diabetes** focusing on:
- **First injectable choice**
- **Intensification**
- **Simplification / de-escalation** (e.g., basal-bolus or premix → FRC)

Runs fully **client-side** in the browser (Pyodide). No backend, no patient data storage.

## Disclaimer
This tool is a **prototype** for decision-support logic transparency and internal evaluation. It does **not** replace clinical judgement, local policies, or product labels.

---

## Country-first priority
**Country is the first decision node** and controls:
- Local priority (when 2023–2026 guidance exists)
- Availability constraints (Jordan: FRC not available)
- Notes (Turkey reimbursement note for FRC at BMI < 35 — comment only)

Supported: RU, TR, LB, JO, IQ, EU, US, OTHER.

---

## Inputs (MVP)
- Country
- HbA1c, BMI, (optional eGFR)
- **FPG** (optional): value + unit (mg/dL or mmol/L); mmol/L × **18.018** → mg/dL for logic
- **Iraq only — Access to GLP-1 RA** (select): **Yes** enables GLP-1 RA and FRC branches; **No** or **not specified** (empty) → insulin-only recommendations (no GLP-1 / no FRC in output)
- Catabolic symptoms
- **Irregular meal patterns** (Yes/No; default No) — when Yes, premix is not offered where the algorithm would otherwise list it; FRC or basal-bolus preferred
- ASCVD / HF / CKD flags
- Availability: long-acting GLP-1 RA, **FRC** (fixed-ratio combination)
- Current regimen: none / basal / GLP-1 / FRC / premix / basal-bolus
- Simplification triggers: recurrent hypoglycaemia, regimen complexity

---

## Decision logic (with short rationale)

### Node 1 — Severe hyperglycaemia
**If** catabolic symptoms OR HbA1c ≥ 10% OR **FPG > 300 mg/dL** (after conversion) → **insulin start / urgent insulin intensification**  
**Rationale:** rapid control is prioritized in severe dysglycaemia / catabolic context.

### Node 2 — Simplification (BB or premix)
**If** basal-bolus OR premix AND (hypoglycaemia OR complexity):
- If FRC available (and not Jordan) → **switch to FRC**
- Else → **simplify within insulin options**
**Rationale:** de-intensification / simplification may be appropriate when hypoglycaemia risk or burden is high.

### Node 3 — Intensification on basal insulin
**If** on basal insulin and above target:
1) If GLP-1 available → **add GLP-1 RA**
2) Else if FRC available (and not Jordan) → **switch basal → FRC**
3) Else → **add prandial insulin** (basal-plus → escalate)
**Rationale:** GLP-1 is preferred before prandial insulin when feasible; FRC provides basal+postprandial coverage with one injection.

### Node 4 — First injectable selection
A) Cardiorenal risk (ASCVD/HF/CKD):
- GLP-1 available → **GLP-1 RA**
- Else → **basal insulin**
**Rationale:** prioritize agents with established cardiometabolic benefit when feasible.

B) BMI ≥ 30:
- GLP-1 available → **GLP-1 RA**
**Rationale:** weight benefit + low hypoglycaemia risk.

C) HbA1c > 9 (no catabolism) and FRC available (not Jordan):
- **start FRC**
**Rationale:** early basal+postprandial strategy may reduce need for multi-injection intensification.

D) Default:
- GLP-1 available → GLP-1 RA
- Else → basal insulin

---

## Decision tree (Mermaid)

```mermaid
flowchart TD
  A[Start: Select country] --> B{Severe hyperglycaemia?\n(catabolic OR HbA1c ≥10 OR FPG > 300 mg/dL)}
  B -- Yes --> I0[Insulin start / urgent insulin intensification]

  B -- No --> S{On premix or basal-bolus\nAND hypoglycaemia/complexity?}
  S -- Yes --> S1{FRC available?\n(and not Jordan)}
  S1 -- Yes --> SFRC[Simplify: switch to FRC]
  S1 -- No --> SINS[Simplify within insulin options]

  S -- No --> D{On basal insulin?}
  D -- Yes --> D2{GLP-1 available?}
  D2 -- Yes --> DBG[Add GLP-1 RA to basal]
  D2 -- No --> D3{FRC available?\n(and not Jordan)}
  D3 -- Yes --> DBF[Switch basal -> FRC]
  D3 -- No --> DBP[Add prandial insulin\n(basal-plus -> escalate)]

  D -- No --> E{Cardiorenal risk?\nASCVD/HF/CKD}
  E -- Yes --> E1{GLP-1 available?}
  E1 -- Yes --> F1[First injectable: GLP-1 RA]
  E1 -- No --> F2[First injectable: basal insulin]

  E -- No --> W{BMI ≥ 30?}
  W -- Yes --> W1{GLP-1 available?}
  W1 -- Yes --> F1
  W1 -- No --> H{HbA1c > 9\nand FRC available?\n(and not Jordan)}
  W -- No --> H

  H -- Yes --> F3[First injectable: FRC]
  H -- No --> Z{GLP-1 available?}
  Z -- Yes --> F1
  Z -- No --> F2
```
