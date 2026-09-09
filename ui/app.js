const fmt = new Intl.NumberFormat("es-GT");
const PAGE_SIZE = 50;

const els = {
  health: document.getElementById("health-pill"),
  summary: document.getElementById("summary"),
  fuentes: document.getElementById("fuentes"),
  tablas: document.getElementById("tablas"),
  cargas: document.getElementById("cargas"),
  error: document.getElementById("error"),
  notice: document.getElementById("notice"),
  refresh: document.getElementById("btn-refresh"),
  loadHistorico: document.getElementById("btn-load-historico"),
  loadPadron: document.getElementById("btn-load-padron"),
  periodo: document.getElementById("periodo"),
  watermark: document.getElementById("watermark"),
  periodoWarning: document.getElementById("periodo-warning"),
  tabs: document.getElementById("explorer-tabs"),
  explorer: document.getElementById("explorer"),
  explorerMeta: document.getElementById("explorer-meta"),
  explorerQ: document.getElementById("explorer-q"),
  explorerSearch: document.getElementById("explorer-search"),
  explorerPeriodo: document.getElementById("explorer-periodo"),
  explorerPeriodoWrap: document.getElementById("explorer-periodo-wrap"),
  prev: document.getElementById("explorer-prev"),
  next: document.getElementById("explorer-next"),
};

const LABELS = {
  centros_votacion: "Centros de votación",
  resultados_historicos: "Resultados históricos",
  mesas_votacion: "Mesas de votación",
  empadronados: "Padrón (empadronados)",
};

const explorer = {
  tabla: "centros_votacion",
  offset: 0,
  total: 0,
  q: "",
  periodo: "",
};

function showError(msg) {
  els.error.hidden = !msg;
  els.error.textContent = msg || "";
}

function showNotice(msg) {
  els.notice.hidden = !msg;
  els.notice.textContent = msg || "";
}

async function getJson(url, options) {
  const res = await fetch(url, options);
  const body = await res.json().catch(() => ({}));
  if (!res.ok) {
    const detail = body.detail;
    const message =
      typeof detail === "string"
        ? detail
        : detail?.mensaje || `Error ${res.status} en ${url}`;
    const err = new Error(message);
    err.status = res.status;
    err.detail = detail;
    throw err;
  }
  return body;
}

function badge(cargada) {
  return cargada
    ? '<span class="badge badge-ok">Cargada</span>'
    : '<span class="badge badge-pending">Falta</span>';
}

function renderFuente(fuente) {
  const title = LABELS[fuente.id] || fuente.id;
  if (fuente.id === "empadronados") {
    const fechas = (fuente.fechas || [])
      .map(
        (item) => `
        <div class="date-row">
          <span>${item.fecha}</span>
          <span>${fmt.format(item.filas_csv)} filas · ${item.cargada ? "en DB" : "pendiente"}</span>
        </div>`
      )
      .join("");
    return `
      <article class="card">
        ${badge(!(fuente.pendientes || []).length && fuente.snapshot_en_db)}
        <h3>${title}</h3>
        <p class="meta">${fuente.archivo}</p>
        <p class="stat">Snapshot en DB: ${fmt.format(fuente.filas_db)}${
          fuente.watermark ? ` · watermark ${fuente.watermark}` : ""
        }</p>
        <div class="dates">${fechas}</div>
      </article>`;
  }

  const csv =
    fuente.filas_csv == null ? "sin CSV" : `${fmt.format(fuente.filas_csv)} en CSV`;
  return `
    <article class="card">
      ${badge(fuente.cargada)}
      <h3>${title}</h3>
      <p class="meta">${fuente.archivo || fuente.nota || ""}</p>
      <p class="stat">${csv} · ${fmt.format(fuente.filas_db)} en DB</p>
    </article>`;
}

function renderSummary(cobertura, health) {
  const n = (cobertura.pendientes || []).length;
  const pendientes = (cobertura.pendientes || [])
    .map((item) => `<li>${item}</li>`)
    .join("");
  els.summary.innerHTML = `
    <div>
      <span class="n">${n}</span>
      <span class="label">fuentes o fechas pendientes</span>
    </div>
    <div>
      <span class="n">${health.postgres ? "OK" : "DOWN"}</span>
      <span class="label">${health.database}@${health.host}:${health.port}</span>
    </div>
    ${
      n
        ? `<ul class="pendientes">${pendientes}</ul>`
        : `<p class="pendientes">No falta data por cargar.</p>`
    }
  `;
}

function tableIdFromNombre(nombre) {
  return (nombre || "").split(".").pop();
}

function renderTablas(payload) {
  const rows = (payload.tablas || [])
    .map((t) => {
      const id = tableIdFromNombre(t.nombre);
      return `
      <tr>
        <td><button class="linkish" data-open-table="${id}" type="button">${t.nombre}</button></td>
        <td class="num">${fmt.format(t.filas)}</td>
        <td>${t.filas > 0 ? "con data" : "vacía"}</td>
      </tr>`;
    })
    .join("");
  els.tablas.innerHTML = `
    <table>
      <thead><tr><th>Tabla</th><th>Filas</th><th>Estado</th></tr></thead>
      <tbody>${rows}</tbody>
    </table>`;
  els.tablas.querySelectorAll("[data-open-table]").forEach((btn) => {
    btn.addEventListener("click", () => openTable(btn.dataset.openTable));
  });
}

function renderCargas(payload) {
  if (!payload.total) {
    els.cargas.innerHTML = '<p class="empty">Sin registros en electoral.carga_log.</p>';
    return;
  }
  const rows = payload.cargas
    .map(
      (c) => `
      <tr>
        <td class="num">${c.id_log}</td>
        <td>${c.proceso || ""}</td>
        <td>${c.observacion || ""}</td>
        <td>${c.fecha || ""}</td>
      </tr>`
    )
    .join("");
  els.cargas.innerHTML = `
    <table>
      <thead><tr><th>ID</th><th>Proceso</th><th>Observación</th><th>Fecha</th></tr></thead>
      <tbody>${rows}</tbody>
    </table>`;
}

function renderTabs(catalogo) {
  els.tabs.innerHTML = (catalogo || [])
    .map(
      (item) => `
      <button class="tab ${item.id === explorer.tabla ? "active" : ""}" data-table="${item.id}" type="button">
        ${item.label}
      </button>`
    )
    .join("");
  els.tabs.querySelectorAll("[data-table]").forEach((btn) => {
    btn.addEventListener("click", () => openTable(btn.dataset.table));
  });
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;");
}

function syncPeriodoFilter(data) {
  const isEmp = explorer.tabla === "empadronados";
  els.explorerPeriodoWrap.hidden = !isEmp;
  if (!isEmp) {
    explorer.periodo = "";
    return;
  }
  const periodos = data.periodos || [];
  const current = explorer.periodo;
  els.explorerPeriodo.innerHTML =
    `<option value="">Todos</option>` +
    periodos
      .map((fecha) => `<option value="${escapeHtml(fecha)}">${escapeHtml(fecha)}</option>`)
      .join("");
  if (current && periodos.includes(current)) {
    els.explorerPeriodo.value = current;
    explorer.periodo = current;
  } else {
    els.explorerPeriodo.value = "";
    explorer.periodo = "";
  }
}

async function loadExplorer() {
  const params = new URLSearchParams({
    limit: String(PAGE_SIZE),
    offset: String(explorer.offset),
  });
  if (explorer.q) params.set("q", explorer.q);
  if (explorer.tabla === "empadronados" && explorer.periodo) {
    params.set("periodo", explorer.periodo);
  }
  const data = await getJson(`/api/tablas/${explorer.tabla}?${params}`);
  explorer.total = data.total;
  syncPeriodoFilter(data);
  const start = data.total === 0 ? 0 : data.offset + 1;
  const end = Math.min(data.offset + data.filas.length, data.total);
  const filtro = data.periodo ? ` · periodo ${data.periodo}` : "";
  els.explorerMeta.textContent = `${data.label}: ${fmt.format(start)}–${fmt.format(end)} de ${fmt.format(data.total)}${filtro}`;
  if (!data.filas.length) {
    els.explorer.innerHTML = '<p class="empty">Esta tabla no tiene filas para mostrar.</p>';
  } else {
    const head = data.columnas.map((col) => `<th>${escapeHtml(col)}</th>`).join("");
    const body = data.filas
      .map((row) => {
        const cells = data.columnas
          .map((col) => `<td>${escapeHtml(row[col])}</td>`)
          .join("");
        return `<tr>${cells}</tr>`;
      })
      .join("");
    els.explorer.innerHTML = `<table><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table>`;
  }
  els.prev.disabled = explorer.offset <= 0;
  els.next.disabled = explorer.offset + PAGE_SIZE >= explorer.total;
  els.tabs.querySelectorAll(".tab").forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.table === explorer.tabla);
  });
}

async function openTable(tabla) {
  explorer.tabla = tabla;
  explorer.offset = 0;
  explorer.q = "";
  explorer.periodo = "";
  els.explorerQ.value = "";
  if (els.explorerPeriodo) els.explorerPeriodo.value = "";
  await loadExplorer();
  els.explorer.scrollIntoView({ behavior: "smooth", block: "start" });
}

async function load() {
  showError("");
  try {
    const [health, cobertura, tablas, cargas] = await Promise.all([
      getJson("/health"),
      getJson("/api/cobertura"),
      getJson("/api/tablas"),
      getJson("/api/cargas"),
    ]);

    els.health.textContent = health.postgres ? "Postgres listo" : "Postgres caído";
    els.health.className = `pill ${health.postgres ? "pill-ok" : "pill-bad"}`;
    renderSummary(cobertura, health);
    els.fuentes.innerHTML = (cobertura.fuentes || []).map(renderFuente).join("");
    renderTablas(tablas);
    renderTabs(tablas.catalogo);
    renderCargas(cargas);
    renderPeriodos(cobertura);
    await loadExplorer();
  } catch (err) {
    els.health.textContent = "Sin conexión";
    els.health.className = "pill pill-bad";
    showError(err.message);
  }
}

els.refresh.addEventListener("click", () => {
  showNotice("");
  load();
});
els.explorerSearch.addEventListener("click", () => {
  explorer.q = els.explorerQ.value.trim();
  explorer.offset = 0;
  loadExplorer().catch((err) => showError(err.message));
});
els.explorerQ.addEventListener("keydown", (event) => {
  if (event.key === "Enter") {
    explorer.q = els.explorerQ.value.trim();
    explorer.offset = 0;
    loadExplorer().catch((err) => showError(err.message));
  }
});
els.explorerPeriodo.addEventListener("change", () => {
  explorer.periodo = els.explorerPeriodo.value;
  explorer.offset = 0;
  loadExplorer().catch((err) => showError(err.message));
});
els.prev.addEventListener("click", () => {
  explorer.offset = Math.max(0, explorer.offset - PAGE_SIZE);
  loadExplorer().catch((err) => showError(err.message));
});
els.next.addEventListener("click", () => {
  explorer.offset += PAGE_SIZE;
  loadExplorer().catch((err) => showError(err.message));
});

function selectedPeriodo() {
  const emp = (window.__coberturaFuentes || []).find((f) => f.id === "empadronados");
  const fecha = els.periodo.value;
  return (emp?.fechas || []).find((item) => item.fecha === fecha);
}

function renderPeriodos(cobertura) {
  window.__coberturaFuentes = cobertura.fuentes || [];
  const emp = (cobertura.fuentes || []).find((f) => f.id === "empadronados");
  const fechas = emp?.fechas || [];
  const current = els.periodo.value;
  els.periodo.innerHTML = fechas
    .map((item) => {
      const mark = item.cargada ? " (ya cargado)" : "";
      return `<option value="${item.fecha}">${item.fecha} · ${fmt.format(item.filas_csv)} filas${mark}</option>`;
    })
    .join("");
  if (current && [...els.periodo.options].some((opt) => opt.value === current)) {
    els.periodo.value = current;
  } else {
    const pendiente = fechas.find((item) => !item.cargada);
    els.periodo.value = pendiente?.fecha || fechas[0]?.fecha || "";
  }
  els.watermark.textContent = emp?.watermark
    ? `Watermark: ${emp.watermark}`
    : "Watermark: sin padrón cargado";
  updatePeriodoWarning();
}

function updatePeriodoWarning() {
  const item = selectedPeriodo();
  const emp = (window.__coberturaFuentes || []).find((f) => f.id === "empadronados");
  if (!item) {
    els.periodoWarning.hidden = true;
    return;
  }
  if (item.cargada) {
    els.periodoWarning.hidden = false;
    els.periodoWarning.textContent = `El periodo ${item.fecha} ya está cargado. Si lo vuelves a cargar se sobreescribirá el padrón vigente, sin duplicar ids.`;
    return;
  }
  if (emp?.watermark && item.fecha < emp.watermark) {
    els.periodoWarning.hidden = false;
    els.periodoWarning.textContent = `El watermark es ${emp.watermark}. Cargar ${item.fecha} sobreescribirá el padrón con una foto anterior.`;
    return;
  }
  els.periodoWarning.hidden = true;
}

async function postLoad(url, payload, pendingMsg, openTabla) {
  showError("");
  showNotice(pendingMsg);
  const headers = { "Content-Type": "application/json" };
  const send = (body) =>
    getJson(url, { method: "POST", headers, body: JSON.stringify(body) });
  try {
    let result;
    try {
      result = await send({ ...payload, overwrite: false });
    } catch (err) {
      if (err.status === 409 && err.detail?.requiere_overwrite) {
        const ok = window.confirm(`${err.detail.mensaje}\n\n¿Sobreescribir?`);
        if (!ok) {
          showNotice("Carga cancelada: no sobreescribí nada.");
          return;
        }
        result = await send({ ...payload, overwrite: true });
      } else {
        throw err;
      }
    }
    const metricas = result.metricas;
    const resumen = Array.isArray(metricas)
      ? metricas.map((m) => `${m.pipeline}: ${m.cargados} cargados / ${m.rechazados} rechazados`).join(" · ")
      : `${metricas.pipeline || "padrón"}: ${fmt.format(metricas.cargados || 0)} cargados · altas ${metricas.altas ?? "—"} · cambios ${metricas.cambios ?? "—"} · bajas ${metricas.bajas ?? "—"}`;
    showNotice(resumen);
    await load();
    if (openTabla) await openTable(openTabla);
  } catch (err) {
    showNotice("");
    showError(err.message);
  }
}

els.periodo.addEventListener("change", updatePeriodoWarning);
els.loadHistorico.addEventListener("click", async () => {
  els.loadHistorico.disabled = true;
  try {
    await postLoad("/api/cargas/historico", {}, "Cargando histórico…", "centros_votacion");
  } finally {
    els.loadHistorico.disabled = false;
  }
});
els.loadPadron.addEventListener("click", async () => {
  const fecha = els.periodo.value;
  if (!fecha) {
    showError("Elige un periodo.");
    return;
  }
  els.loadPadron.disabled = true;
  try {
    await postLoad(
      "/api/cargas/empadronados",
      { fecha },
      `Cargando padrón ${fecha}…`,
      "empadronados"
    );
  } finally {
    els.loadPadron.disabled = false;
  }
});

load();
