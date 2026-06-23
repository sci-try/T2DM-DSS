// ─────────────────────────────────────────────────────────────────────────────
//  app.js  –  T2D Injectable Therapy CDS  v3
//  Currently Iraq (IQ) only. Türkiye (TR) is disabled legacy — re-enable by
//  restoring the TR markup in index.html and setting TR_ENABLED = True in
//  py/engine.py (legacy code paths below are kept commented for that purpose).
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
// LEGACY (TR): country selector removed from the Iraq-only UI.
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

function selVal(id) {
  const el = document.getElementById(id);
  return el ? el.value : null;
}

// Returns the checked radio value for a group, or null.
function radioVal(name) {
  const el = document.querySelector(`input[name="${name}"]:checked`);
  return el ? el.value : null;
}

// Iraq-only deployment. (LEGACY: return countryEl ? countryEl.value : "IQ";)
function getCountry() {
  return "IQ";
}

function getRegimen() {
  return radioVal("regimen_iq") || "none";
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

/** IQ only: true when the monotherapy long-acting GLP-1 RA access radio is Yes (maps to iq_glp1_ra_access). */
function iqLaGlp1RaAccessFromUI() {
  return radioVal("iq_glp1_ra_access") === "yes";
}

function getInputs() {
  const regimen = getRegimen();

  // Iraq-only payload: simple binary bands + current-regimen flags.
  return {
    country:                "IQ",
    hba1c_band:             radioVal("hba1c_band"),
    bmi_band:               radioVal("bmi_band"),
    irregular_meal_patterns: irregularMealPatternsYes(),
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

// ══════════════════════════════════════════════════════════════════════════════
//  UI RULES
// ══════════════════════════════════════════════════════════════════════════════

// Iraq-only: ensure the IQ regimen set is visible. (LEGACY TR branch removed.)
function applyCountryRegimenSets() {
  show(document.getElementById("regimen_iq"));
}

// Input hints are switched off; kept as a no-op so refreshUI() stays intact.
function applyHints() {}

function applyRegimenUIRules() {
  const regimen = getRegimen();

  // Hide all contextual checkboxes first
  hideById("ppg_uncontrolled_wrap");
  hideById("recurrent_hypoglycemia_wrap");

  // Iraq: recurrent hypoglycaemia only relevant on premix / basal-bolus.
  if (regimen === "premix" || regimen === "bb") {
    showById("recurrent_hypoglycemia_wrap");
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

// Slide-aligned per-line icon for a Key Considerations item.
function kcIcon(text) {
  const t = text.toLowerCase();
  if (t.startsWith("hba1c target")) return "🧪";
  if (t.includes("basal insulin:") || t.includes("2nd-generation basal")) return "💉";
  if (t.startsWith("glp-1 ra choice")) return "⚖️";
  if (t.startsWith("frc")) return "🔗";
  if (t.startsWith("basal-bolus")) return "🔄";
  if (t.startsWith("premix")) return "⚖️";
  if (t.startsWith("irregular")) return "⚠️";
  return "🔹";
}

function fillKeyConsiderations(items) {
  const ul = document.getElementById("key_considerations");
  if (!ul) return;
  ul.innerHTML = "";
  (items || []).forEach((x) => {
    const text = String(x);
    const li = document.createElement("li");

    const icon = document.createElement("span");
    icon.className = "rec__kc-icon";
    icon.setAttribute("aria-hidden", "true");
    icon.textContent = kcIcon(text);
    li.appendChild(icon);

    const body = document.createElement("span");
    const idx = text.indexOf(":");
    if (idx > -1) {
      const lead = document.createElement("span");
      lead.className = "rec__kc-lead";
      lead.textContent = text.slice(0, idx + 1);
      body.appendChild(lead);
      body.appendChild(document.createTextNode(text.slice(idx + 1)));
    } else {
      body.textContent = text;
    }
    li.appendChild(body);
    ul.appendChild(li);
  });
}

function render(rec) {
  const therapyEl = document.getElementById("therapy");
  if (therapyEl) therapyEl.textContent = rec.therapy || "";

  fillList("why",  rec.why        || []);
  fillList("next", rec.next_steps || []);

  const kcBlock = document.getElementById("kc_block");
  const keyConsiderations = rec.key_considerations || [];
  if (kcBlock) {
    if (keyConsiderations.length) {
      show(kcBlock);
      fillKeyConsiderations(keyConsiderations);
    } else {
      hide(kcBlock);
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

// LEGACY (TR): country selector is absent in the Iraq-only UI; guard before use.
if (countryEl) countryEl.addEventListener("change", refreshUI);

document.querySelectorAll('input[name="regimen_iq"]').forEach((el) =>
  el.addEventListener("change", applyRegimenUIRules)
);

// ══════════════════════════════════════════════════════════════════════════════
//  BOOTSTRAP — refreshUI() runs synchronously before init() starts loading
// ══════════════════════════════════════════════════════════════════════════════

refreshUI();
init();
