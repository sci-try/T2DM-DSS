let pyodide = null;

const statusEl = document.getElementById("status");
const resultEl = document.getElementById("result");

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

function getRegimen() {
  const el = document.querySelector('input[name="regimen"]:checked');
  return el ? el.value : "none";
}

function getInputs() {
  const regimen = getRegimen();

  return {
    country: document.getElementById("country").value,
    hba1c: numOrNull("hba1c"),
    hba1c_target: numOrNull("hba1c_target"),
    bmi: numOrNull("bmi"),

    symptoms_catabolic: boolVal("symptoms_catabolic"),
    recurrent_hypoglycemia: boolVal("recurrent_hypoglycemia"),
    ppg_uncontrolled: boolVal("ppg_uncontrolled"),

    on_basal_insulin: regimen === "basal",
    on_frc: regimen === "frc",
    on_premix: regimen === "premix",
    on_basal_bolus: regimen === "bb",
    on_rapid_added: boolVal("on_rapid_added"),
  };
}

function fillList(ulId, items) {
  const ul = document.getElementById(ulId);
  ul.innerHTML = "";
  (items || []).forEach((x) => {
    const li = document.createElement("li");
    li.textContent = String(x);
    ul.appendChild(li);
  });
}

function render(rec) {
  document.getElementById("therapy").textContent = rec.therapy || "";

  fillList("why", rec.why || []);
  fillList("next", rec.next_steps || []);

  const commentsBlock = document.getElementById("comments_block");
  const comments = rec.comments || [];

  if (comments.length) {
    commentsBlock.hidden = false;
    fillList("comments", comments);
  } else {
    commentsBlock.hidden = true;
  }

  resultEl.hidden = false;
}

function applyCountryUIRules() {
  const country = document.getElementById("country").value;
  const hint = document.getElementById("country_hint");

  if (country === "TR") {
    hint.textContent =
      "Turkey: when FRC is recommended and BMI is below 35 kg/m², reimbursement may be limited and treatment may be out-of-pocket.";
  } else {
    hint.textContent = "";
  }
}

function applyRegimenUIRules() {
  const regimen = getRegimen();

  const onRapidWrap = document.getElementById("on_rapid_added_wrap");
  const ppgWrap = document.getElementById("ppg_uncontrolled_wrap");
  const hypoWrap = document.getElementById("recurrent_hypoglycemia_wrap");

  onRapidWrap.hidden = true;
  ppgWrap.hidden = true;
  hypoWrap.hidden = true;

  if (regimen === "none") {
    return;
  }

  if (regimen === "basal") {
    ppgWrap.hidden = false;
    return;
  }

  if (regimen === "frc") {
    onRapidWrap.hidden = false;
    return;
  }

  if (regimen === "premix" || regimen === "bb") {
    hypoWrap.hidden = false;
  }
}

async function init() {
  try {
    statusEl.textContent = "Loading Pyodide…";

    pyodide = await loadPyodide({
      indexURL: "https://cdn.jsdelivr.net/pyodide/v0.25.1/full/",
    });

    statusEl.textContent = "Loading clinical engine…";

    const engineUrl = `py/engine.py?v=${Date.now()}`;
    const engineCode = await (await fetch(engineUrl)).text();
    pyodide.runPython(engineCode);

    pyodide.runPython("assert 'recommend_json' in globals()");

    statusEl.textContent = "Ready.";
  } catch (e) {
    console.error(e);
    statusEl.textContent = "Init failed — open Console (F12) for details.";
  }
}

document.getElementById("country").addEventListener("change", applyCountryUIRules);

document.querySelectorAll('input[name="regimen"]').forEach((el) => {
  el.addEventListener("change", applyRegimenUIRules);
});

document.getElementById("run").addEventListener("click", () => {
  if (!pyodide) {
    statusEl.textContent = "Pyodide is still loading…";
    return;
  }

  try {
    const inputs = getInputs();
    const inputsJson = JSON.stringify(inputs);

    pyodide.globals.set("JS_INPUTS_JSON", inputsJson);
    const outJson = pyodide.runPython("recommend_json(JS_INPUTS_JSON)");

    const rec = JSON.parse(outJson);
    render(rec);
    statusEl.textContent = "Recommendation generated.";
  } catch (e) {
    console.error(e);
    statusEl.textContent = "Run failed — open Console (F12) for details.";
  }
});

applyCountryUIRules();
applyRegimenUIRules();
init();
