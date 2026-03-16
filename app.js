// ─────────────────────────────────────────────────────────────────────────────
//  app.js  –  T2D Injectable Therapy CDS
//  Supports: Turkey (TR) · Iraq (IQ)
//  Matches:  index.html v3  ·  py/engine.py v3
//
//  This file is the SOLE owner of all UI-show/hide logic for index.html.
//  index.html contains NO inline <script> UI code.
// ─────────────────────────────────────────────────────────────────────────────

"use strict";

// ── Module-level state ────────────────────────────────────────────────────────
let pyodide = null;

// ── DOM refs ──────────────────────────────────────────────────────────────────
const statusEl  = document.getElementById("status");
const resultEl  = document.getElementById("result");
const countryEl = document.getElementById("country");

// ══════════════════════════════════════════════════════════════════════════════
//  INPUT HELPERS
// ══════════════════════════════════════════════════════════════════════════════

/** Return a finite number or null from a numeric input field. */
function numOrNull(id) {
  const el = document.getElementById(id);
  if (!el) return null;
  const v = el.value;
  if (v === "" || v === null) return null;
  const n = Number(v);
  return Number.isFinite(n) ? n : null;
}

/** Return the checked state of a checkbox, safely. */
function boolVal(id) {
  const el = document.getElementById(id);
  return el ? el.checked : false;
}

/** Active country code. */
function getCountry() {
  return countryEl ? countryEl.value : "TR";
}

/**
 * Selected regimen value for the active country.
 *   Turkey → radio group  name="regimen"
 *   Iraq   → radio group  name="regimen_iq"
 */
function getRegimen() {
  const name = getCountry() === "IQ" ? "regimen_iq" : "regimen";
  const el   = document.querySelector(`input[name="${name}"]:checked`);
  return el ? el.value : "none";
}

/**
 * Build the inputs object for the Python engine.
 * Iraq and Turkey use different regimen flag sets.
 */
function getInputs() {
  const country = getCountry();
  const regimen = getRegimen();

  // Shared fields
  const base = {
    country,
    hba1c:              numOrNull("hba1c"),
    hba1c_target:       numOrNull("hba1c_target"),
    bmi:                numOrNull("bmi"),
    symptoms_catabolic: boolVal("symptoms_catabolic"),
  };

  // ── Iraq ──────────────────────────────────────────────────────────────────
  if (country === "IQ") {
    return {
      ...base,
      on_basal_only:    regimen === "basal_only",
      on_glp1_alone:    regimen === "glp1_alone",
      on_bi_glp1:       regimen === "bi_glp1",
      on_bi_glp1_rapid: regimen === "bi_glp1_rapid",
      on_premix:        regimen === "premix",
      on_basal_bolus:   regimen === "bb",
      recurrent_hypoglycemia: boolVal("recurrent_hypoglycemia"),
    };
  }

  // ── Turkey (legacy flag set, unchanged) ───────────────────────────────────
  return {
    ...base,
    on_basal_insulin: regimen === "basal",
    on_frc:           regimen === "frc",
    on_premix:        regimen === "premix",
    on_basal_bolus:   regimen === "bb",
    recurrent_hypoglycemia: boolVal("recurrent_hypoglycemia"),
    ppg_uncontrolled:       boolVal("ppg_uncontrolled"),
  };
}

// ══════════════════════════════════════════════════════════════════════════════
//  UI RULES  –  show / hide contextual fields
// ══════════════════════════════════════════════════════════════════════════════

/**
 * Show the correct regimen radio group; hide and reset the other.
 * Resetting prevents stale checked values bleeding into getInputs().
 */
function applyCountryRegimenSets() {
  const country   = getCountry();
  const regimenTR = document.getElementById("regimen_tr");
  const regimenIQ = document.getElementById("regimen_iq");

  if (regimenTR) regimenTR.hidden = (country === "IQ");
  if (regimenIQ) regimenIQ.hidden = (country !== "IQ");

  // Reset the hidden group to "none"
  if (country === "IQ") {
    const el = document.querySelector('input[name="regimen"][value="none"]');
    if (el) el.checked = true;
  } else {
    const el = document.querySelector('input[name="regimen_iq"][value="none"]');
    if (el) el.checked = true;
  }
}

/**
 * Country hint and regimen hint text.
 */
function applyHints() {
  const country     = getCountry();
  const countryHint = document.getElementById("country_hint");
  const regimenHint = document.getElementById("regimen_hint");

  if (countryHint) {
    countryHint.textContent = country === "TR"
      ? "Turkey: when FRC is recommended and BMI is below 35 kg/m², "
        + "reimbursement may be limited and treatment may be out-of-pocket."
      : "Iraq: gap- and BMI-based algorithm. "
        + "Select the patient's current regimen to route intensification correctly.";
  }

  if (regimenHint) {
    regimenHint.textContent = country === "TR"
      ? "Turkey logic is FRC/reimbursement-oriented. "
        + "Standalone GLP-1 RA appears only as an optional note."
      : "Iraq algorithm: each regimen step maps to a specific intensification branch.";
  }
}

/**
 * Show / hide contextual checkboxes.
 *
 * Iraq:
 *   recurrent_hypoglycemia → premix or bb only
 *   ppg_uncontrolled       → never (not part of IQ algorithm)
 *
 * Turkey:
 *   ppg_uncontrolled       → basal only
 *   recurrent_hypoglycemia → premix or bb only
 */
function applyRegimenUIRules() {
  const country  = getCountry();
  const regimen  = getRegimen();
  const ppgWrap  = document.getElementById("ppg_uncontrolled_wrap");
  const hypoWrap = document.getElementById("recurrent_hypoglycemia_wrap");

  // Default: hide both
  if (ppgWrap)  ppgWrap.hidden  = true;
  if (hypoWrap) hypoWrap.hidden = true;

  if (country === "IQ") {
    if (hypoWrap)
      hypoWrap.hidden = !(regimen === "premix" || regimen === "bb");
    // ppg_uncontrolled stays hidden for IQ
  } else {
    // Turkey
    if (ppgWrap)
      ppgWrap.hidden  = (regimen !== "basal");
    if (hypoWrap)
      hypoWrap.hidden = !(regimen === "premix" || regimen === "bb");
  }
}

/** Master UI refresh — single call covers all three concerns. */
function refreshUI() {
  applyCountryRegimenSets();
  applyHints();
  applyRegimenUIRules();
}

// ══════════════════════════════════════════════════════════════════════════════
//  RENDER RESULT
// ══════════════════════════════════════════════════════════════════════════════

function fillList(ulId, items) {
  const ul = document.getElementById(ulId);
  if (!ul) return;
  ul.innerHTML = "";
  (items || []).forEach((x) => {
    const li = document.createElement("li");
    li.textContent = String(x);
    ul.appendChild(li);
  });
}

function render(rec) {
  const therapyEl = document.getElementById("therapy");
  if (therapyEl) therapyEl.textContent = rec.therapy || "";

  fillList("why",  rec.why        || []);
  fillList("next", rec.next_steps || []);

  const commentsBlock = document.getElementById("comments_block");
  const comments      = rec.comments || [];
  if (commentsBlock) {
    commentsBlock.hidden = comments.length === 0;
    fillList("comments", comments);
  }

  if (resultEl) resultEl.hidden = false;
}

// ══════════════════════════════════════════════════════════════════════════════
//  PYODIDE INIT
// ══════════════════════════════════════════════════════════════════════════════

async function init() {
  try {
    statusEl.textContent = "Loading Pyodide…";
    pyodide = await loadPyodide({
      indexURL: "https://cdn.jsdelivr.net/pyodide/v0.25.1/full/",
    });

    statusEl.textContent = "Loading clinical engine…";
    const engineCode = await (
      await fetch(`py/engine.py?v=${Date.now()}`)
    ).text();
    pyodide.runPython(engineCode);
    pyodide.runPython(
      "assert 'recommend_json' in globals(), 'recommend_json missing'"
    );

    statusEl.textContent = "Ready.";
  } catch (e) {
    console.error("[CDS init]", e);
    statusEl.textContent = "Init failed — open Console (F12) for details.";
  }
}

// ══════════════════════════════════════════════════════════════════════════════
//  RUN BUTTON
// ══════════════════════════════════════════════════════════════════════════════

document.getElementById("run").addEventListener("click", () => {
  if (!pyodide) {
    statusEl.textContent = "Pyodide is still loading — please wait…";
    return;
  }
  try {
    const inputs  = getInputs();
    pyodide.globals.set("JS_INPUTS_JSON", JSON.stringify(inputs));
    const outJson = pyodide.runPython("recommend_json(JS_INPUTS_JSON)");
    render(JSON.parse(outJson));
    statusEl.textContent = "Recommendation generated.";
  } catch (e) {
    console.error("[CDS run]", e);
    statusEl.textContent = "Run failed — open Console (F12) for details.";
  }
});

// ══════════════════════════════════════════════════════════════════════════════
//  EVENT WIRING
// ══════════════════════════════════════════════════════════════════════════════

// Country change
countryEl.addEventListener("change", refreshUI);

// Turkey regimen radios
document.querySelectorAll('input[name="regimen"]').forEach((el) =>
  el.addEventListener("change", applyRegimenUIRules)
);

// Iraq regimen radios
document.querySelectorAll('input[name="regimen_iq"]').forEach((el) =>
  el.addEventListener("change", applyRegimenUIRules)
);

// ══════════════════════════════════════════════════════════════════════════════
//  BOOTSTRAP
// ══════════════════════════════════════════════════════════════════════════════

refreshUI();   // set correct initial state before Pyodide loads
init();
