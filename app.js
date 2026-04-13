// ─────────────────────────────────────────────────────────────────────────────
//  app.js  –  T2D Injectable Therapy CDS  v3
//  Supports: Turkey (TR) · Iraq (IQ)
//
//  Visibility is controlled exclusively via style.display.
//  index.html sets the correct initial state via inline style="display:..."
//  so nothing is ever shown before this script runs.
// ─────────────────────────────────────────────────────────────────────────────

"use strict";

let pyodide = null;

// ── DOM refs ──────────────────────────────────────────────────────────────────
const statusEl  = document.getElementById("status");
const resultEl  = document.getElementById("result");
const countryEl = document.getElementById("country");

// ── Visibility helper — single source of truth ───────────────────────────────
function show(el) {
  if (!el) return;
  el.hidden = false;
  el.style.display = "";
}

function hide(el) {
  if (!el) return;
  el.hidden = true;
  el.style.display = "none";
}
function showById(id) { show(document.getElementById(id)); }
function hideById(id) { hide(document.getElementById(id)); }

// ══════════════════════════════════════════════════════════════════════════════
//  INPUT HELPERS
// ══════════════════════════════════════════════════════════════════════════════

function numOrNull(id) {
  const el = document.getElementById(id);
  if (!el) return null;
  const v = el.value;
  if (v === "" || v === null) return null;
  const n = Number(v);
  return Number.isFinite(n) ? n : null;
}

function boolVal(id) {
  const el = document.getElementById(id);
  return el ? el.checked : false;
}

function getCountry() {
  return countryEl ? countryEl.value : "TR";
}

function getRegimen() {
  const name = getCountry() === "IQ" ? "regimen_iq" : "regimen";
  const el   = document.querySelector(`input[name="${name}"]:checked`);
  return el ? el.value : "none";
}

function irregularMealPatternsYes() {
  const el = document.querySelector(
    'input[name="irregular_meal_patterns"]:checked'
  );
  return el ? el.value === "yes" : false;
}

function fpgUnit() {
  const sel = document.getElementById("fpg_unit");
  return sel ? sel.value : "mg_dl";
}

/** IQ only: true when standalone long-acting GLP-1 RA access select is explicitly Yes (maps to iq_glp1_ra_access). */
function iqLaGlp1RaAccessFromUI() {
  const sel = document.getElementById("iq_glp1_ra_access");
  if (!sel) return false;
  return sel.value === "yes";
}

function getInputs() {
  const country = getCountry();
  const regimen = getRegimen();

  const base = {
    country,
    hba1c:              numOrNull("hba1c"),
    hba1c_target:       numOrNull("hba1c_target"),
    bmi:                numOrNull("bmi"),
    fpg:                numOrNull("fpg"),
    fpg_unit:           fpgUnit(),
    symptoms_catabolic: boolVal("symptoms_catabolic"),
    irregular_meal_patterns: irregularMealPatternsYes(),
  };

  if (country === "IQ") {
    return {
      ...base,
      iq_glp1_ra_access:      iqLaGlp1RaAccessFromUI(),
      on_basal_only:          regimen === "basal_only",
      on_glp1_alone:          regimen === "glp1_alone",
      on_bi_glp1:             regimen === "bi_glp1",
      on_bi_glp1_rapid:       regimen === "bi_glp1_rapid",
      on_premix:              regimen === "premix",
      on_basal_bolus:         regimen === "bb",
      recurrent_hypoglycemia: boolVal("recurrent_hypoglycemia"),
    };
  }

  return {
    ...base,
    on_basal_insulin:       regimen === "basal",
    on_frc:                 regimen === "frc" || regimen === "frc_rapid",
    on_rapid_added:         regimen === "frc_rapid",
    on_premix:              regimen === "premix",
    on_basal_bolus:         regimen === "bb",
    recurrent_hypoglycemia: boolVal("recurrent_hypoglycemia"),
    ppg_uncontrolled:       boolVal("ppg_uncontrolled"),
  };
}

// ══════════════════════════════════════════════════════════════════════════════
//  UI RULES
// ══════════════════════════════════════════════════════════════════════════════

function applyCountryRegimenSets() {
  const country   = getCountry();
  const regimenTR = document.getElementById("regimen_tr");
  const regimenIQ = document.getElementById("regimen_iq");
  const iqGlp1Wrap = document.getElementById("iq_glp1_access_wrap");
  const iqGlp1Sel = document.getElementById("iq_glp1_ra_access");

  if (country === "IQ") {
    hide(regimenTR);
    show(regimenIQ);
    if (iqGlp1Wrap) show(iqGlp1Wrap);
    // Reset TR group so stale value never reaches getInputs()
    const noneTR = document.querySelector('input[name="regimen"][value="none"]');
    if (noneTR) noneTR.checked = true;
  } else {
    show(regimenTR);
    hide(regimenIQ);
    if (iqGlp1Wrap) hide(iqGlp1Wrap);
    if (iqGlp1Sel) iqGlp1Sel.value = "";
    // Reset IQ group
    const noneIQ = document.querySelector('input[name="regimen_iq"][value="none"]');
    if (noneIQ) noneIQ.checked = true;
  }
}

function applyHints() {
  const country     = getCountry();
  const countryHint = document.getElementById("country_hint");
  const regimenHint = document.getElementById("regimen_hint");

  if (countryHint) {
    countryHint.textContent = country === "TR"
      ? "Turkey: when FRC is recommended and BMI is below 35 kg/m², "
        + "reimbursement may be limited and treatment may be out-of-pocket."
      : "Iraq: routing is based on how far HbA1c is above the individualised "
        + "target and BMI. Select the current regimen to route intensification correctly.";
  }

  if (regimenHint) {
    regimenHint.textContent = country === "TR"
      ? "Turkey logic is FRC/reimbursement-oriented. "
        + "Standalone GLP-1 RA appears only as an optional note."
      : "Iraq algorithm: each regimen step maps to a specific intensification branch.";
  }
}

function applyRegimenUIRules() {
  const country = getCountry();
  const regimen = getRegimen();

  // Hide all contextual checkboxes first
  hideById("ppg_uncontrolled_wrap");
  hideById("recurrent_hypoglycemia_wrap");

  if (country === "IQ") {
    // Hypoglycaemia only relevant on premix / bb
    if (regimen === "premix" || regimen === "bb") {
      showById("recurrent_hypoglycemia_wrap");
    }
    // ppg_uncontrolled: not part of Iraq algorithm — stays hidden

  } else {
    // Turkey
    if (regimen === "basal") {
      showById("ppg_uncontrolled_wrap");
    }
    if (regimen === "premix" || regimen === "bb") {
      showById("recurrent_hypoglycemia_wrap");
    }
  }
}

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
    if (comments.length) {
      show(commentsBlock);
      fillList("comments", comments);
    } else {
      hide(commentsBlock);
    }
  }

  if (resultEl) show(resultEl);
}

// ══════════════════════════════════════════════════════════════════════════════
//  PYODIDE
// ══════════════════════════════════════════════════════════════════════════════

async function init() {
  try {
    statusEl.textContent = "Loading Pyodide…";
    pyodide = await loadPyodide({
      indexURL: "https://cdn.jsdelivr.net/pyodide/v0.25.1/full/",
    });
    statusEl.textContent = "Loading clinical engine…";
    const code = await (
      await fetch(`py/engine.py?v=${Date.now()}`)
    ).text();
    pyodide.runPython(code);
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
//  RUN
// ══════════════════════════════════════════════════════════════════════════════

document.getElementById("run").addEventListener("click", () => {
  if (!pyodide) {
    statusEl.textContent = "Pyodide is still loading — please wait…";
    return;
  }
  try {
    pyodide.globals.set("JS_INPUTS_JSON", JSON.stringify(getInputs()));
    const rec = JSON.parse(pyodide.runPython("recommend_json(JS_INPUTS_JSON)"));
    render(rec);
    statusEl.textContent = "Recommendation generated.";
  } catch (e) {
    console.error("[CDS run]", e);
    statusEl.textContent = "Run failed — open Console (F12) for details.";
  }
});

// ══════════════════════════════════════════════════════════════════════════════
//  EVENT WIRING
// ══════════════════════════════════════════════════════════════════════════════

countryEl.addEventListener("change", refreshUI);

document.querySelectorAll('input[name="regimen"]').forEach((el) =>
  el.addEventListener("change", applyRegimenUIRules)
);
document.querySelectorAll('input[name="regimen_iq"]').forEach((el) =>
  el.addEventListener("change", applyRegimenUIRules)
);

// ══════════════════════════════════════════════════════════════════════════════
//  BOOTSTRAP — refreshUI() runs synchronously before init() starts loading
// ══════════════════════════════════════════════════════════════════════════════

refreshUI();
init();
