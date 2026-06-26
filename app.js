const STORAGE_KEY = "bitacora.mobile.v1";

const state = loadState();
let deferredInstallPrompt = null;

const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];

function todayISO() {
  return new Date().toISOString().slice(0, 10);
}

function uid() {
  return crypto.randomUUID ? crypto.randomUUID() : `${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function money(value) {
  return Number(value || 0).toLocaleString("es-MX", {
    style: "currency",
    currency: "MXN",
    maximumFractionDigits: 2,
  });
}

function number(value) {
  return Number(value || 0);
}

function loadState() {
  const fallback = { entries: [], debts: [], payments: [], debtMonths: [], exercisePlans: [] };
  try {
    const loaded = { ...fallback, ...JSON.parse(localStorage.getItem(STORAGE_KEY) || "{}") };
    loaded.debtMonths = loaded.debtMonths || [];
    loaded.exercisePlans = loaded.exercisePlans || [];
    return loaded;
  } catch {
    return fallback;
  }
}

function saveState() {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
}

function compliance(entry) {
  const checks = [
    entry.exercise === "si",
    number(entry.englishMinutes) > 0,
    entry.nofap === "cumplido",
    number(entry.sleepHours) >= 7,
    number(entry.ciscoModules) + number(entry.uvegProgress) + number(entry.tuchProgress) +
      number(entry.argosMinutes) + number(entry.centinelaMinutes) > 0,
  ];
  return Math.round((checks.filter(Boolean).length / checks.length) * 100);
}

function byDateDesc(a, b) {
  return b.date.localeCompare(a.date);
}

function monthOf(value) {
  return value.slice(0, 7);
}

function currentMonth() {
  return monthOf(todayISO());
}

function todayTime() {
  return new Date(`${todayISO()}T00:00:00`).getTime();
}

function debtPaidTotal(debtId) {
  return state.payments
    .filter((payment) => payment.debtId === debtId)
    .reduce((sum, payment) => sum + number(payment.amount), 0);
}

function debtPaidMonth(debtId, month = currentMonth()) {
  return state.payments
    .filter((payment) => payment.debtId === debtId && monthOf(payment.date) === month)
    .reduce((sum, payment) => sum + number(payment.amount), 0);
}

function debtPending(debt) {
  return Math.max(0, number(debt.initialBalance) - debtPaidTotal(debt.id));
}

function debtMonthConfig(debt, month = currentMonth()) {
  const config = state.debtMonths.find((item) => item.debtId === debt.id && item.month === month);
  return {
    minimumPayment: config ? number(config.minimumPayment) : number(debt.minimumPayment),
    noInterestPayment: config ? number(config.noInterestPayment) : number(debt.noInterestPayment),
    monthlyGoal: config ? number(config.monthlyGoal) : number(debt.monthlyGoal),
    dueDate: config ? config.dueDate || "" : "",
  };
}

function debtMonthStatus(debt, paidMonth, config) {
  if (debtPending(debt) <= 0) return "Liquidada";
  if (config.noInterestPayment && paidMonth >= config.noInterestPayment) return "Sin intereses cubierto";
  if (config.dueDate && new Date(`${config.dueDate}T00:00:00`).getTime() < todayTime()) {
    if (config.noInterestPayment) return `Intereses: faltan ${money(config.noInterestPayment - paidMonth)}`;
    const missing = config.minimumPayment ? Math.max(0, config.minimumPayment - paidMonth) : 0;
    return missing ? `Vencida: faltan ${money(missing)}` : "Fecha vencida";
  }
  if (config.minimumPayment && paidMonth >= config.minimumPayment) return "Minimo cubierto";
  if (config.minimumPayment) return `Faltan ${money(config.minimumPayment - paidMonth)}`;
  return "Sin meta";
}

function renderAll() {
  renderDebtOptions();
  renderPanel();
  renderDebts();
  renderExercise();
  renderChart();
}

function renderPanel() {
  const end = new Date(todayISO());
  const start = new Date(end);
  start.setDate(end.getDate() - 6);
  const startISO = start.toISOString().slice(0, 10);
  const recent = state.entries.filter((entry) => entry.date >= startISO && entry.date <= todayISO()).sort((a, b) => a.date.localeCompare(b.date));
  const complianceAverage = recent.length
    ? Math.round(recent.reduce((sum, entry) => sum + compliance(entry), 0) / recent.length)
    : 0;
  const energyAverage = recent.length
    ? recent.reduce((sum, entry) => sum + number(entry.energy), 0) / recent.length
    : 0;
  const debtTotal = state.debts.reduce((sum, debt) => sum + debtPending(debt), 0);

  $("#kpiDays").textContent = recent.length;
  $("#kpiCompliance").textContent = `${complianceAverage}%`;
  $("#kpiEnergy").textContent = `${energyAverage.toFixed(1)}/10`;
  $("#kpiDebt").textContent = money(debtTotal);

  const summary = [
    ["Cisco: submodulos", recent.reduce((sum, entry) => sum + number(entry.ciscoModules), 0)],
    ["Ejercicio: dias", recent.filter((entry) => entry.exercise === "si").length],
    ["Ingles: minutos", recent.reduce((sum, entry) => sum + number(entry.englishMinutes), 0)],
    ["Sueno promedio", `${average(recent.map((entry) => number(entry.sleepHours))).toFixed(1)} h`],
    ["Pagos de deuda", money(state.payments.filter((payment) => payment.date >= startISO).reduce((sum, payment) => sum + number(payment.amount), 0))],
    ["Gastos evitados", money(recent.reduce((sum, entry) => sum + number(entry.avoidedSpending), 0))],
  ];
  $("#weekSummary").innerHTML = summary.map(([label, value]) => `
    <div class="row"><div class="row-header"><span>${label}</span><strong>${value}</strong></div></div>
  `).join("");

  const latest = [...state.entries].sort(byDateDesc).slice(0, 8);
  $("#recentEntries").innerHTML = latest.length ? latest.map((entry) => `
    <article class="row">
      <div class="row-header">
        <span>${entry.date}</span>
        <span class="pill">${compliance(entry)}%</span>
      </div>
      <small>Energia ${number(entry.energy) || "-"} | Sueno ${number(entry.sleepHours) || "-"} h</small>
      ${entry.note ? `<small>${escapeHTML(entry.note)}</small>` : ""}
    </article>
  `).join("") : emptyHTML();

  const todayPlan = state.exercisePlans.find((plan) => plan.date === todayISO());
  $("#todayExercise").innerHTML = todayPlan ? exerciseCardHTML(todayPlan, false) : `
    <article class="row">
      <div class="row-header">
        <span>Sin rutina para hoy</span>
        <span class="pill">Pendiente</span>
      </div>
      <small>Ve a la pestaña Ejercicio para anotar qué toca y cuánto tiempo.</small>
    </article>
  `;
}

function renderExercise() {
  const today = todayISO();
  if ($('input[name="date"]', $("#exerciseForm"))) {
    const dateField = $('input[name="date"]', $("#exerciseForm"));
    if (!dateField.value) dateField.value = today;
  }
  const start = new Date(today);
  start.setDate(start.getDate() - 3);
  const end = new Date(today);
  end.setDate(end.getDate() + 3);
  const startISO = start.toISOString().slice(0, 10);
  const endISO = end.toISOString().slice(0, 10);
  const plans = state.exercisePlans
    .filter((plan) => plan.date >= startISO && plan.date <= endISO)
    .sort((a, b) => a.date.localeCompare(b.date));
  $("#exerciseWeek").innerHTML = plans.length ? plans.map((plan) => exerciseCardHTML(plan, true)).join("") : emptyHTML();

  $$("[data-load-exercise]").forEach((button) => {
    button.addEventListener("click", () => loadExerciseIntoForm(button.dataset.loadExercise));
  });
  $$("[data-delete-exercise]").forEach((button) => {
    button.addEventListener("click", () => {
      if (!confirm("¿Eliminar este plan de ejercicio?")) return;
      state.exercisePlans = state.exercisePlans.filter((plan) => plan.date !== button.dataset.deleteExercise);
      saveState();
      renderAll();
    });
  });
}

function exerciseCardHTML(plan, withActions) {
  const statusLabels = {
    pendiente: "Pendiente",
    hecho: "Hecho",
    parcial: "Parcial",
    descanso: "Descanso",
  };
  return `
    <article class="row">
      <div class="row-header">
        <span>${plan.date} · ${escapeHTML(plan.workout || "Sin nombre")}</span>
        <span class="pill">${statusLabels[plan.status] || plan.status || "Pendiente"}</span>
      </div>
      ${plan.routine ? `<small>${escapeHTML(plan.routine).replace(/\n/g, "<br>")}</small>` : ""}
      <small>Estimado: ${number(plan.plannedMinutes) || 0} min | Real: ${number(plan.actualMinutes) || 0} min</small>
      ${plan.note ? `<small>${escapeHTML(plan.note)}</small>` : ""}
      ${withActions ? `
        <div class="inline-actions">
          <button class="ghost-dark" type="button" data-load-exercise="${plan.date}">Editar</button>
          <button class="danger" type="button" data-delete-exercise="${plan.date}">Eliminar</button>
        </div>
      ` : ""}
    </article>
  `;
}

function renderDebtOptions() {
  const options = ['<option value="">Selecciona deuda</option>']
    .concat(state.debts.map((debt) => `<option value="${debt.id}">${escapeHTML(debt.name)}</option>`));
  $$('select[name="debtId"], select[name="debtMonthId"]').forEach((select) => {
    const selected = select.value;
    select.innerHTML = options.join("");
    select.value = selected;
  });
}

function renderDebts() {
  const debtRows = state.debts.map((debt) => {
    const paidMonth = debtPaidMonth(debt.id);
    const config = debtMonthConfig(debt);
    const minimum = config.minimumPayment;
    const noInterest = config.noInterestPayment;
    const status = debtMonthStatus(debt, paidMonth, config);

    return { debt, paidMonth, minimum, noInterest, dueDate: config.dueDate, monthlyGoal: config.monthlyGoal, status };
  });

  $("#debtTableBody").innerHTML = debtRows.length ? debtRows.map(({ debt, paidMonth, minimum, noInterest, dueDate, monthlyGoal, status }) => `
    <tr>
      <td>${escapeHTML(debt.name)}</td>
      <td>${money(debtPending(debt))}</td>
      <td>${money(paidMonth)}</td>
      <td>${money(minimum)}</td>
      <td>${money(noInterest)}</td>
      <td>${dueDate || "-"}</td>
      <td>${money(monthlyGoal)}</td>
      <td><span class="pill">${status}</span></td>
    </tr>
  `).join("") : `<tr><td colspan="8" class="empty-cell">Todavia no hay deudas.</td></tr>`;

  $("#debtList").innerHTML = debtRows.length ? debtRows.map(({ debt, paidMonth, minimum, noInterest, dueDate, status }) => `
      <article class="row">
        <div class="row-header">
          <span>${escapeHTML(debt.name)}</span>
          <span class="pill">${status}</span>
        </div>
        <small>Pendiente: ${money(debtPending(debt))}</small>
        <small>Pagado este mes: ${money(paidMonth)} | Minimo: ${money(minimum)} | Sin intereses: ${money(noInterest)} | Limite: ${dueDate || "-"}</small>
        <button class="danger" type="button" data-delete-debt="${debt.id}">Eliminar deuda</button>
      </article>
    `).join("") : emptyHTML();

  $$("[data-delete-debt]").forEach((button) => {
    button.addEventListener("click", () => {
      const debtId = button.dataset.deleteDebt;
      if (!confirm("Eliminar esta deuda tambien eliminara sus pagos. ¿Continuar?")) return;
      state.debts = state.debts.filter((debt) => debt.id !== debtId);
      state.payments = state.payments.filter((payment) => payment.debtId !== debtId);
      state.debtMonths = state.debtMonths.filter((item) => item.debtId !== debtId);
      saveState();
      renderAll();
    });
  });
}

function renderChart() {
  const canvas = $("#chartCanvas");
  if (!canvas) return;
  const ctx = canvas.getContext("2d");
  const type = $("#chartType").value;
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  ctx.fillStyle = "#ffffff";
  ctx.fillRect(0, 0, canvas.width, canvas.height);

  if (type === "debt") {
    drawBars(ctx, state.debts.map((debt) => [debt.name, debtPending(debt)]), "Saldos pendientes", true);
  } else if (type === "payments") {
    drawGroupedDebtBars(ctx);
  } else {
    const entries = [...state.entries].sort((a, b) => a.date.localeCompare(b.date)).slice(-30);
    if (type === "study") {
      drawLines(ctx, entries, [
        ["Cisco", (entry) => number(entry.ciscoModules), "#2855a6"],
        ["Ingles", (entry) => number(entry.englishMinutes), "#2e7d5b"],
        ["Argos", (entry) => number(entry.argosMinutes), "#c78318"],
        ["Centinela", (entry) => number(entry.centinelaMinutes), "#b64949"],
      ], "Avance academico");
    } else {
      drawLines(ctx, entries, [
        ["Energia", (entry) => number(entry.energy), "#2855a6", 10],
        ["Sueno", (entry) => number(entry.sleepHours), "#2e7d5b", 10],
        ["Cumplimiento", (entry) => compliance(entry) / 10, "#c78318", 10],
      ], "Habitos y bienestar");
    }
  }
}

function drawBars(ctx, items, title, currency = false) {
  titleCanvas(ctx, title);
  const filtered = items.filter(([, value]) => number(value) > 0);
  if (!filtered.length) return emptyCanvas(ctx);
  const max = Math.max(...filtered.map(([, value]) => number(value)), 1);
  const left = 190;
  const top = 80;
  const width = 650;
  const rowHeight = Math.min(55, 360 / filtered.length);
  filtered.forEach(([label, value], index) => {
    const y = top + index * rowHeight;
    const barWidth = (number(value) / max) * width;
    ctx.fillStyle = "#243247";
    ctx.textAlign = "right";
    ctx.fillText(String(label).slice(0, 22), left - 12, y + 22);
    ctx.fillStyle = "#2855a6";
    roundRect(ctx, left, y, barWidth, 26, 9);
    ctx.fill();
    ctx.textAlign = "left";
    ctx.fillStyle = "#243247";
    ctx.fillText(currency ? money(value) : value, left + barWidth + 10, y + 20);
  });
}

function drawGroupedDebtBars(ctx) {
  titleCanvas(ctx, "Pagos del mes frente a metas");
  if (!state.debts.length) return emptyCanvas(ctx);
  const rows = state.debts.map((debt) => ({
    label: debt.name,
    paid: debtPaidMonth(debt.id),
    minimum: debtMonthConfig(debt).minimumPayment,
    noInterest: debtMonthConfig(debt).noInterestPayment,
    goal: debtMonthConfig(debt).monthlyGoal,
  }));
  const max = Math.max(...rows.flatMap((row) => [row.paid, row.minimum, row.noInterest, row.goal]), 1);
  const left = 185;
  const top = 80;
  const width = 650;
  const rowHeight = Math.min(70, 380 / rows.length);
  const series = [
    ["paid", "#2855a6", "Pagado"],
    ["minimum", "#c78318", "Minimo"],
    ["noInterest", "#2e7d5b", "Sin intereses"],
    ["goal", "#65758b", "Meta"],
  ];
  rows.forEach((row, index) => {
    const y = top + index * rowHeight;
    ctx.textAlign = "right";
    ctx.fillStyle = "#243247";
    ctx.fillText(row.label.slice(0, 20), left - 10, y + 28);
    series.forEach(([key, color], offset) => {
      ctx.fillStyle = color;
      roundRect(ctx, left, y + offset * 11, (row[key] / max) * width, 8, 4);
      ctx.fill();
    });
  });
  drawLegend(ctx, series.map(([, color, label]) => [label, color]));
}

function drawLines(ctx, entries, series, title) {
  titleCanvas(ctx, title);
  if (!entries.length) return emptyCanvas(ctx);
  const left = 55;
  const top = 80;
  const right = 860;
  const bottom = 440;
  ctx.strokeStyle = "#d6dfea";
  ctx.beginPath();
  ctx.moveTo(left, top);
  ctx.lineTo(left, bottom);
  ctx.lineTo(right, bottom);
  ctx.stroke();

  const max = Math.max(...series.flatMap(([, getter, , fixed]) => entries.map((entry) => fixed || getter(entry))), 1);
  const step = (right - left) / Math.max(entries.length - 1, 1);
  series.forEach(([label, getter, color, fixed]) => {
    const scale = fixed || max;
    ctx.strokeStyle = color;
    ctx.lineWidth = 3;
    ctx.beginPath();
    entries.forEach((entry, index) => {
      const x = left + index * step;
      const y = bottom - (Math.min(getter(entry), scale) / scale) * (bottom - top);
      if (index === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    });
    ctx.stroke();
  });
  entries.forEach((entry, index) => {
    if (index % Math.max(1, Math.ceil(entries.length / 8)) === 0) {
      ctx.fillStyle = "#65758b";
      ctx.textAlign = "center";
      ctx.fillText(entry.date.slice(5), left + index * step, bottom + 22);
    }
  });
  drawLegend(ctx, series.map(([label, , color]) => [label, color]));
}

function titleCanvas(ctx, title) {
  ctx.fillStyle = "#152238";
  ctx.font = "700 28px Segoe UI, sans-serif";
  ctx.textAlign = "left";
  ctx.fillText(title, 32, 42);
  ctx.font = "15px Segoe UI, sans-serif";
}

function emptyCanvas(ctx) {
  ctx.fillStyle = "#65758b";
  ctx.textAlign = "center";
  ctx.font = "18px Segoe UI, sans-serif";
  ctx.fillText("Todavia no hay datos para graficar.", 450, 260);
}

function drawLegend(ctx, items) {
  ctx.font = "15px Segoe UI, sans-serif";
  items.forEach(([label, color], index) => {
    const x = 55 + index * 160;
    ctx.fillStyle = color;
    ctx.fillRect(x, 480, 18, 12);
    ctx.fillStyle = "#243247";
    ctx.textAlign = "left";
    ctx.fillText(label, x + 26, 491);
  });
}

function roundRect(ctx, x, y, width, height, radius) {
  const r = Math.min(radius, height / 2, Math.abs(width) / 2);
  ctx.beginPath();
  ctx.moveTo(x + r, y);
  ctx.arcTo(x + width, y, x + width, y + height, r);
  ctx.arcTo(x + width, y + height, x, y + height, r);
  ctx.arcTo(x, y + height, x, y, r);
  ctx.arcTo(x, y, x + width, y, r);
  ctx.closePath();
}

function average(values) {
  const filtered = values.filter((value) => value > 0);
  return filtered.length ? filtered.reduce((sum, value) => sum + value, 0) / filtered.length : 0;
}

function escapeHTML(value) {
  return String(value || "").replace(/[&<>"']/g, (char) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#039;",
  }[char]));
}

function emptyHTML() {
  return $("#emptyTemplate").innerHTML;
}

function setupTabs() {
  $$(".tab").forEach((button) => {
    button.addEventListener("click", () => {
      $$(".tab").forEach((tab) => tab.classList.remove("active"));
      $$(".view").forEach((view) => view.classList.remove("active"));
      button.classList.add("active");
      $(`#${button.dataset.tab}`).classList.add("active");
      if (button.dataset.tab === "registro") {
        loadEntryIntoForm($("#entryDate").value || todayISO());
      }
      if (button.dataset.tab === "ejercicio") {
        loadExerciseIntoForm($('input[name="date"]', $("#exerciseForm")).value || todayISO());
      }
      renderChart();
    });
  });
}

function setupForms() {
  $("#entryDate").value = todayISO();
  $('input[name="paymentDate"]').value = todayISO();
  $('input[name="month"]').value = currentMonth();
  loadEntryIntoForm(todayISO());

  $("#entryForm").addEventListener("submit", (event) => {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const entry = Object.fromEntries(form.entries());
    entry.date = entry.entryDate;
    delete entry.entryDate;
    const existingIndex = state.entries.findIndex((item) => item.date === entry.date);
    if (existingIndex >= 0) state.entries[existingIndex] = entry;
    else state.entries.push(entry);
    saveState();
    renderAll();
    loadEntryIntoForm(entry.date);
    alert("Registro guardado.");
  });

  $("#entryDate").addEventListener("change", (event) => {
    loadEntryIntoForm(event.target.value);
  });

  $("#debtForm").addEventListener("submit", (event) => {
    event.preventDefault();
    const data = Object.fromEntries(new FormData(event.currentTarget).entries());
    state.debts.push({ id: uid(), ...data });
    event.currentTarget.reset();
    saveState();
    renderAll();
  });

  $("#exerciseForm").addEventListener("submit", (event) => {
    event.preventDefault();
    const data = Object.fromEntries(new FormData(event.currentTarget).entries());
    const existingIndex = state.exercisePlans.findIndex((plan) => plan.date === data.date);
    if (existingIndex >= 0) state.exercisePlans[existingIndex] = data;
    else state.exercisePlans.push(data);

    const entry = state.entries.find((item) => item.date === data.date);
    if (entry) {
      entry.exercise = data.status === "hecho" || data.status === "parcial" ? "si" : entry.exercise;
    } else if (data.status === "hecho" || data.status === "parcial") {
      state.entries.push({ date: data.date, exercise: "si" });
    }

    saveState();
    renderAll();
    loadExerciseIntoForm(data.date);
    alert("Ejercicio guardado.");
  });

  $('input[name="date"]', $("#exerciseForm")).addEventListener("change", (event) => {
    loadExerciseIntoForm(event.target.value);
  });

  $("#debtMonthForm").addEventListener("submit", (event) => {
    event.preventDefault();
    const data = Object.fromEntries(new FormData(event.currentTarget).entries());
    const existingIndex = state.debtMonths.findIndex((item) => item.debtId === data.debtMonthId && item.month === data.month);
    const config = {
      debtId: data.debtMonthId,
      month: data.month,
      minimumPayment: data.minimumPayment,
      noInterestPayment: data.noInterestPayment,
      dueDate: data.dueDate,
      monthlyGoal: data.monthlyGoal,
    };
    if (existingIndex >= 0) state.debtMonths[existingIndex] = config;
    else state.debtMonths.push(config);
    saveState();
    renderAll();
    event.currentTarget.reset();
    $('input[name="month"]').value = currentMonth();
    alert("Configuracion mensual guardada.");
  });

  $("#paymentForm").addEventListener("submit", (event) => {
    event.preventDefault();
    const data = Object.fromEntries(new FormData(event.currentTarget).entries());
    state.payments.push({
      id: uid(),
      debtId: data.debtId,
      date: data.paymentDate,
      amount: data.amount,
      note: data.note,
    });
    event.currentTarget.reset();
    $('input[name="paymentDate"]').value = todayISO();
    saveState();
    renderAll();
  });

  $("#chartType").addEventListener("change", renderChart);
}

function loadEntryIntoForm(entryDate) {
  const form = $("#entryForm");
  const entry = state.entries.find((item) => item.date === entryDate);
  form.reset();
  $("#entryDate").value = entryDate;
  if (!entry) {
    form.elements.exercise.value = "no";
    form.elements.nofap.value = "";
    return;
  }
  Object.entries(entry).forEach(([key, value]) => {
    if (key === "date") return;
    const field = form.elements[key];
    if (field) field.value = value;
  });
}

function setupBackup() {
  $("#exportButton").addEventListener("click", () => {
    const blob = new Blob([JSON.stringify(state, null, 2)], { type: "application/json" });
    const link = document.createElement("a");
    link.href = URL.createObjectURL(blob);
    link.download = `bitacora-respaldo-${todayISO()}.json`;
    link.click();
    URL.revokeObjectURL(link.href);
  });

  $("#importFile").addEventListener("change", async (event) => {
    const file = event.target.files[0];
    if (!file) return;
    const imported = JSON.parse(await file.text());
    if (!confirm("Esto reemplazara los datos de este dispositivo. ¿Continuar?")) return;
    state.entries = imported.entries || [];
    state.debts = imported.debts || [];
    state.payments = imported.payments || [];
    state.debtMonths = imported.debtMonths || [];
    state.exercisePlans = imported.exercisePlans || [];
    saveState();
    renderAll();
  });

  $("#clearButton").addEventListener("click", () => {
    if (!confirm("¿Borrar todos los datos guardados en este dispositivo?")) return;
    state.entries = [];
    state.debts = [];
    state.payments = [];
    state.debtMonths = [];
    state.exercisePlans = [];
    saveState();
    renderAll();
  });
}

function loadExerciseIntoForm(dateValue) {
  const form = $("#exerciseForm");
  const plan = state.exercisePlans.find((item) => item.date === dateValue);
  form.reset();
  form.elements.date.value = dateValue;
  form.elements.status.value = "pendiente";
  if (!plan) return;
  Object.entries(plan).forEach(([key, value]) => {
    const field = form.elements[key];
    if (field) field.value = value;
  });
}

function setupPWA() {
  if ("serviceWorker" in navigator && ["http:", "https:"].includes(location.protocol)) {
    navigator.serviceWorker.register("service-worker.js");
  }
  window.addEventListener("beforeinstallprompt", (event) => {
    event.preventDefault();
    deferredInstallPrompt = event;
    $("#installButton").classList.remove("hidden");
  });
  $("#installButton").addEventListener("click", async () => {
    if (!deferredInstallPrompt) return;
    deferredInstallPrompt.prompt();
    await deferredInstallPrompt.userChoice;
    deferredInstallPrompt = null;
    $("#installButton").classList.add("hidden");
  });
}

setupTabs();
setupForms();
setupBackup();
setupPWA();
renderAll();
