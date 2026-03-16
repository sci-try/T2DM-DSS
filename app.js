// ─────────────────────────────────────────────────────────────────────────────
//  app.js  –  T2D Injectable Therapy CDS
//  Supports: Turkey (TR) and Iraq (IQ)
//  Matches: index.html v3 + py/engine.py v3
// ─────────────────────────────────────────────────────────────────────────────

"use strict";

// ── Module-level state ────────────────────────────────────────────────────────
let pyodide = null;

// ── DOM refs (always present) ─────────────────────────────────────────────────
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

/** Return the value of the currently-active country. */
function getCountry() {
  return countryEl ? countryEl.value : "TR";
}

/**
 * Return the selected regimen value for the active country.
 * Turkey  → reads radio group  name="regimen"
 * Iraq    → reads radio group  name="regimen_iq"
 */
function getRegimen() {
  const country = getCountry();
  const name    = country === "IQ" ? "regimen_iq" : "regimen";
  const el      = document.querySelector(`input[name="${name}"]:checked`);
  return el ? el.value : "none";
}

/**
 * Build the inputs object sent to the Python engine.
 * Iraq and Turkey map their regimen radio values to different boolean flags.
 */
function getInputs() {
  const country = getCountry();
  const regimen = getRegimen();

  // ── Shared numeric / clinical inputs ────────────────────────────────────
  const base = {
    country,
    hba1c:        numOrNull("hba1c"),
    hba1c_target: numOrNull("hba1c_target"),
    bmi:          numOrNull("bmi"),
    symptoms_catabolic: boolVal("symptoms_catabolic"),
  };

  // ── Iraq-specific regimen flags ──────────────────────────────────────────
  if (country === "IQ") {
    return {
      ...base,
      // Intensification-ladder regimen flags (mutually exclusive)
      on_basal_only:    regimen === "basal_only",
      on_glp1_alone:    regimen === "glp1_alone",
      on_bi_glp1:       regimen === "bi_glp1",
      on_bi_glp1_rapid: regimen === "bi_glp1_rapid",
      on_premix:        regimen === "premix",
      on_basal_bolus:   regimen === "bb",
      // Contextual clinical flags visible for IQ
      recurrent_hypoglycemia: boolVal("recurrent_hypoglycemia"),
    };
  }

  // ── Turkey regimen flags (legacy set, unchanged) ─────────────────────────
  return {
    ...base,
    on_basal_insulin: regimen === "basal",
    on_frc:           regimen === "frc",
    on_premix:        regimen === "premix",
    on_basal_bolus:   regimen === "bb",
    // Turkey contextual flags
    recurrent_hypoglycemia: boolVal("recurrent_hypoglycemia"),
    ppg_uncontrolled:       boolVal("ppg_uncontrolled"),
  };
}

// ══════════════════════════════════════════════════════════════════════════════
//  UI RULES  –  show / hide contextual fields
// ══════════════════════════════════════════════════════════════════════════════

/**
 * Regimen sets: show the correct radio group for the selected country,
 * hide the other, and reset the hidden group to "none" to avoid stale values.
 */
function applyCountryRegimenSets() {
  const country   = getCountry();
  const regimenTR = document.getElementById("regimen_tr");
  const regimenIQ = document.getElementById("regimen_iq");

  if (regimenTR) regimenTR.hidden = (country === "IQ");
  if (regimenIQ) regimenIQ.hidden = (country !== "IQ");

  // Reset the now-hidden group so it doesn't bleed stale state into getInputs()
  if (country === "IQ") {
    const noneTR = document.querySelector('input[name="regimen"][value="none"]');
    if (noneTR) noneTR.checked = true;
  } else {
    const noneIQ = document.querySelector('input[name="regimen_iq"][value="none"]');
    if (noneIQ) noneIQ.checked = true;
  }
}

/**
 * Country hint text below the country selector.
 */
function applyCountryHint() {
  const country = getCountry();
  const hint    = document.getElementById("country_hint");
  if (!hint) return;

  if (country === "TR") {
    hint.textContent =
      "Turkey: when FRC is recommended and BMI is below 35 kg/m², "
      + "reimbursement may be limited and treatment may be out-of-pocket.";
  } else if (country === "IQ") {
    hint.textContent =
      "Iraq: gap- and BMI-based algorithm with GLP-1 RA as a primary option. "
      + "Select the patient's current injectable regimen to route intensification correctly.";
  } else {
    hint.textContent = "";
  }
}

/**
 * Show / hide contextual checkboxes based on country + current regimen.
 *
 * Iraq:
 *   recurrent_hypoglycemia  → visible only when regimen is premix or bb
 *   ppg_uncontrolled        → never shown (not part of IQ algorithm)
 *
 * Turkey:
 *   ppg_uncontrolled        → visible only when regimen is basal
 *   recurrent_hypoglycemia  → visible only when regimen is premix or bb
 */
function applyRegimenUIRules() {
  const country = getCountry();
  const regimen = getRegimen();

  const ppgWrap  = document.getElementById("ppg_uncontrolled_wrap");
  const hypoWrap = document.getElementById("recurrent_hypoglycemia_wrap");

  // Default: hide everything, then selectively show
  if (ppgWrap)  ppgWrap.hidden  = true;
  if (hypoWrap) hypoWrap.hidden = true;

  if (country === "IQ") {
    // Iraq: hypoglycaemia checkbox only relevant on premix / bb
    if (hypoWrap) hypoWrap.hidden = !(regimen === "premix" || regimen === "bb");
    // ppg_uncontrolled is not part of the Iraq algorithm — stays hidden

  } else {
    // Turkey
    if (ppgWrap)  ppgWrap.hidden  = (regimen !== "basal");
    if (hypoWrap) hypoWrap.hidden = !(regimen === "premix" || regimen === "bb");
  }
}

/**
 * Master UI refresh — call whenever country or regimen changes.
 */
function refreshUI() {
  applyCountryRegimenSets();
  applyCountryHint();
  applyRegimenUIRules();
}

// ══════════════════════════════════════════════════════════════════════════════
//  RENDER RESULT
// ══════════════════════════════════════════════════════════════════════════════

/** Populate a <ul> with text items. */
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

/** Render the recommendation object into the result card. */
function render(rec) {
  // Therapy headline
  const therapyEl = document.getElementById("therapy");
  if (therapyEl) therapyEl.textContent = rec.therapy || "";

  // Rationale + next steps
  fillList("why",  rec.why        || []);
  fillList("next", rec.next_steps || []);

  // Notes / comments block
  const commentsBlock = document.getElementById("comments_block");
  const comments      = rec.comments || [];
  if (commentsBlock) {
    commentsBlock.hidden = comments.length === 0;
    fillList("comments", comments);
  }

  // Show result card
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

    // Cache-bust so stale engine.py is never served during development
    const engineUrl  = `py/engine.py?v=${Date.now()}`;
    const engineCode = await (await fetch(engineUrl)).text();
    pyodide.runPython(engineCode);

    // Sanity-check: ensure the entry-point function is present
    pyodide.runPython("assert 'recommend_json' in globals(), 'recommend_json missing'");

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
    const inputs     = getInputs();
    const inputsJson = JSON.stringify(inputs);

    // Pass JSON string into Python namespace and call the engine
    pyodide.globals.set("JS_INPUTS_JSON", inputsJson);
    const outJson = pyodide.runPython("recommend_json(JS_INPUTS_JSON)");

    const rec = JSON.parse(outJson);
    render(rec);
    statusEl.textContent = "Recommendation generated.";
  } catch (e) {
    console.error("[CDS run]", e);
    statusEl.textContent = "Run failed — open Console (F12) for details.";
  }
});

// ══════════════════════════════════════════════════════════════════════════════
//  EVENT WIRING
// ���═════════════════════════════════════════════════════════════════════════════

// Country change → full UI refresh
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

// Apply UI rules immediately on page load, then start Pyodide
refreshUI();
init();
