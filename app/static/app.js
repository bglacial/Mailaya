const state = {
  dashboard: null,
  expanded: new Set(),
  pollTimer: null,
};

const $ = (id) => document.getElementById(id);

function setDefaultDate() {
  const date = new Date();
  date.setDate(date.getDate() - 30);
  $("since-date").value = date.toISOString().slice(0, 10);
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });
  if (!response.ok) {
    let message = `Erreur ${response.status}`;
    try {
      const body = await response.json();
      message = body.detail || message;
    } catch (_) {
      // The HTTP status is sufficient when the body is not JSON.
    }
    throw new Error(message);
  }
  return response.status === 204 ? null : response.json();
}

function text(tag, value, className) {
  const node = document.createElement(tag);
  node.textContent = value;
  if (className) node.className = className;
  return node;
}

function formatNumber(value, decimals = 0) {
  return new Intl.NumberFormat("fr-FR", { maximumFractionDigits: decimals }).format(value || 0);
}

function priorityLabel(score) {
  if (score >= 82) return { label: "Critique", level: "critical" };
  if (score >= 58) return { label: "Haute", level: "high" };
  if (score >= 28) return { label: "Normale", level: "normal" };
  return { label: "Basse", level: "low" };
}

function scoreNode(value) {
  const node = text("span", `${formatNumber(value, 1)} %`, "score");
  node.style.setProperty("--score", `${Math.max(0, Math.min(100, value || 0))}%`);
  return node;
}

function makeCell(content, className = "") {
  const cell = document.createElement("td");
  cell.className = className;
  if (content instanceof Node) cell.append(content);
  else cell.textContent = content;
  return cell;
}

function renderMatrix(email) {
  const row = document.createElement("tr");
  row.className = "matrix-row";
  row.dataset.open = state.expanded.has(email.id) ? "true" : "false";
  const cell = document.createElement("td");
  cell.colSpan = 7;
  const panel = document.createElement("div");
  panel.className = "matrix-panel";
  panel.id = `matrix-${email.id}`;

  const scores = Object.entries(email.category_scores || {}).sort((a, b) => b[1] - a[1]);
  for (const [category, score] of scores) {
    const item = document.createElement("div");
    item.className = "matrix-item";
    item.append(text("span", category), text("strong", `${formatNumber(score * 100, 1)} %`));
    const line = document.createElement("span");
    line.className = "matrix-line";
    const fill = document.createElement("span");
    fill.style.width = `${Math.max(1, score * 100)}%`;
    line.append(fill);
    item.append(line);
    panel.append(item);
  }
  cell.append(panel);
  row.append(cell);
  return row;
}

function renderRows(emails) {
  const tbody = $("mail-rows");
  tbody.replaceChildren();
  const filter = $("category-filter").value;
  const filtered = emails.filter((email) => filter === "all" || email.category === filter);
  $("empty-state").hidden = emails.length > 0;

  for (const email of filtered) {
    const row = document.createElement("tr");
    row.dataset.status = email.status;

    const sender = document.createElement("div");
    sender.append(text("div", email.sender_name, "sender-name"), text("div", email.sender_address, "sender-address"));
    row.append(makeCell(sender, "sender-cell"));

    const subject = document.createElement("div");
    subject.append(text("div", email.subject, "subject"), text("div", email.body_preview, "preview"));
    row.append(makeCell(subject, "subject-cell"));

    if (email.status === "complete") {
      const categoryButton = text("button", email.category, "category-button");
      categoryButton.type = "button";
      categoryButton.setAttribute("aria-expanded", state.expanded.has(email.id) ? "true" : "false");
      categoryButton.setAttribute("aria-controls", `matrix-${email.id}`);
      categoryButton.title = "Afficher la matrice de probabilités";
      categoryButton.addEventListener("click", () => {
        state.expanded.has(email.id) ? state.expanded.delete(email.id) : state.expanded.add(email.id);
        renderRows(state.dashboard.emails);
      });
      row.append(makeCell(categoryButton));
      const priority = priorityLabel(email.priority_score);
      const priorityNode = text("span", priority.label, "priority-label");
      priorityNode.dataset.level = priority.level;
      priorityNode.title = `${formatNumber(email.priority_score, 1)} sur 100`;
      row.append(makeCell(priorityNode));
      row.append(makeCell(scoreNode(email.spam_score)));
      row.append(makeCell(scoreNode(email.action_score)));
      row.append(makeCell(`${formatNumber(email.duration_ms, 1)} ms`, "numeric"));
    } else if (email.status === "failed") {
      row.append(makeCell("Échec", "pending-copy"));
      const error = text("span", "Voir le journal", "pending-copy");
      error.title = email.error || "Erreur inconnue";
      row.append(makeCell(error));
      row.append(makeCell("–"), makeCell("–"), makeCell("–"));
    } else {
      row.append(makeCell("En attente", "pending-copy"));
      row.append(makeCell("–"), makeCell("–"), makeCell("–"), makeCell("–"));
    }
    tbody.append(row);
    if (email.status === "complete") tbody.append(renderMatrix(email));
  }
}

function renderCategoryFilter(emails) {
  const select = $("category-filter");
  const current = select.value;
  const categories = [...new Set(emails.map((email) => email.category).filter(Boolean))].sort();
  select.replaceChildren(new Option("Toutes les catégories", "all"));
  categories.forEach((category) => select.add(new Option(category, category)));
  select.value = categories.includes(current) ? current : "all";
}

function renderCategorySummary(categories) {
  const container = $("category-bars");
  container.replaceChildren();
  const entries = Object.entries(categories || {}).sort((a, b) => b[1] - a[1]);
  const total = entries.reduce((sum, [, count]) => sum + count, 0);
  $("category-total").textContent = `${total} classé${total > 1 ? "s" : ""}`;
  if (!entries.length) {
    container.append(text("p", "Les catégories apparaîtront ici.", "category-empty"));
    return;
  }
  const max = Math.max(...entries.map(([, count]) => count));
  for (const [category, count] of entries) {
    const row = document.createElement("div");
    row.className = "category-summary-row";
    const track = document.createElement("span");
    track.className = "category-track";
    const fill = document.createElement("span");
    fill.style.width = `${count / max * 100}%`;
    track.append(fill);
    row.append(text("span", category), track, text("span", count));
    container.append(row);
  }
}

function renderAuth(authByProvider, gmailRedirectUri) {
  const panel = $("auth-panel");
  const copy = $("auth-copy");
  const button = $("connect-button");
  const source = $("source").value;
  const auth = authByProvider?.gmail || { state: "unconfigured" };
  panel.hidden = source === "demo";
  copy.replaceChildren();
  button.hidden = false;
  if (source === "demo") return;
  if (auth.state === "unconfigured") {
    copy.append(text("p", "Ajoutez GOOGLE_CLIENT_ID et GOOGLE_CLIENT_SECRET dans le fichier .env pour activer Gmail."));
    button.hidden = true;
  } else if (auth.state === "connected") {
    copy.append(text("p", `Connecté : ${auth.account || "compte Gmail"}`));
    button.textContent = "Reconnecter Gmail";
  } else {
    copy.append(text("p", auth.error || "Gmail n’est pas encore connecté."));
    button.textContent = "Connecter Gmail";
  }

  if (auth.state !== "connected" && gmailRedirectUri) {
    copy.append(text("p", "URI à autoriser dans Google Cloud :", "auth-redirect-label"));
    copy.append(text("code", gmailRedirectUri, "auth-redirect"));
  }
}

function renderDashboard(payload) {
  state.dashboard = payload;
  const run = payload.run;
  const emails = payload.emails || [];
  const metrics = payload.metrics || {};
  renderCategoryFilter(emails);
  renderRows(emails);
  renderCategorySummary(metrics.categories || {});
  renderAuth(payload.auth || {}, payload.configuration.gmail_redirect_uri);

  $("model-copy").textContent = payload.configuration.backend === "laya-mlx"
    ? "LAYA MLX, données traitées en local"
    : "Moteur de démonstration, aucune donnée externe";

  const statusMap = {
    queued: "En file",
    fetching: "Récupération",
    running: "En cours",
    paused: "En pause",
    complete: "Terminé",
    empty: "Aucun message",
    failed: "Échec",
  };
  const status = run?.status || "idle";
  $("run-status").textContent = statusMap[status] || "Au repos";
  $("run-status").dataset.state = status;

  const processed = run?.processed || 0;
  const failed = run?.failed || 0;
  const total = run?.total || 0;
  const finished = processed + failed;
  const percent = total ? Math.min(100, finished / total * 100) : 0;
  $("processed-count").textContent = processed;
  $("total-count").textContent = ` sur ${total}`;
  $("progress-percent").textContent = `${formatNumber(percent, 1)} %`;
  $("progress-bar").style.width = `${percent}%`;
  document.querySelector(".progress-track").setAttribute("aria-valuenow", String(Math.round(percent)));
  $("remaining-count").textContent = `${Math.max(0, total - finished)} restant${total - finished > 1 ? "s" : ""}`;
  $("failed-count").textContent = `${failed} échec${failed > 1 ? "s" : ""}`;

  $("duration-metric").textContent = `${formatNumber(metrics.elapsed_seconds, 1)} s`;
  $("average-metric").textContent = `${formatNumber(metrics.average_ms, 1)} ms`;
  $("rate-metric").textContent = formatNumber(metrics.per_second, 1);
  $("p95-metric").textContent = `${formatNumber(metrics.p95_ms, 1)} ms`;

  const active = ["queued", "fetching", "running"].includes(status);
  const paused = status === "paused";
  const selectedSource = $("source").value;
  const sourceReady = selectedSource === "demo" || payload.auth?.[selectedSource]?.state === "connected";
  $("run-button-label").textContent = active ? "Mettre en pause" : paused ? "Reprendre l’analyse" : "Lancer l’analyse";
  $("run-button").dataset.action = active ? "pause" : paused ? "resume" : "start";
  $("run-button").disabled = !active && !paused && !sourceReady;
  $("source").disabled = active || paused;
  $("limit").disabled = active || paused;
  $("since-date").disabled = active || paused;
  $("clear-results").disabled = active;
  $("results-summary").textContent = run
    ? `${total} message${total > 1 ? "s" : ""} depuis le ${new Date(`${run.since_date}T00:00:00`).toLocaleDateString("fr-FR")}`
    : "Lancez une démonstration pour découvrir le classement.";

  if (run?.error) $("system-note").textContent = run.error;
  else if (active) $("system-note").textContent = `${processed} traité${processed > 1 ? "s" : ""}, capacité locale active.`;
  else if (paused) $("system-note").textContent = "Exécution en pause. Les résultats déjà calculés sont conservés.";
  else if (status === "complete") $("system-note").textContent = `Terminé avec ${payload.configuration.backend}.`;
  else $("system-note").textContent = "Prêt pour une démonstration locale.";

  schedulePoll(active);
}

function schedulePoll(shouldPoll) {
  clearTimeout(state.pollTimer);
  if (shouldPoll) state.pollTimer = setTimeout(loadDashboard, 650);
}

async function loadDashboard() {
  try {
    renderDashboard(await api("/api/dashboard"));
  } catch (error) {
    $("system-note").textContent = error.message;
    schedulePoll(false);
  }
}

async function handleRun(event) {
  event.preventDefault();
  const action = $("run-button").dataset.action || "start";
  const run = state.dashboard?.run;
  try {
    $("run-button").disabled = true;
    if (action === "pause") await api(`/api/runs/${run.id}/pause`, { method: "POST" });
    else if (action === "resume") await api(`/api/runs/${run.id}/resume`, { method: "POST" });
    else {
      await api("/api/runs", {
        method: "POST",
        body: JSON.stringify({
          source: $("source").value,
          since_date: $("since-date").value,
          limit: Number($("limit").value),
        }),
      });
    }
    await loadDashboard();
  } catch (error) {
    $("system-note").textContent = error.message;
  } finally {
    if (state.dashboard) renderDashboard(state.dashboard);
  }
}

async function connectAccount() {
  try {
    $("connect-button").disabled = true;
    const response = await api("/api/auth/google/start", { method: "POST" });
    window.location.assign(response.authorization_url);
  } catch (error) {
    $("system-note").textContent = error.message;
  } finally {
    $("connect-button").disabled = false;
  }
}

async function clearResults() {
  if (!state.dashboard?.run) return;
  try {
    await api("/api/results", { method: "DELETE" });
    state.expanded.clear();
    await loadDashboard();
  } catch (error) {
    $("system-note").textContent = error.message;
  }
}

setDefaultDate();
$("run-form").addEventListener("submit", handleRun);
$("source").addEventListener("change", () => {
  if (state.dashboard) renderDashboard(state.dashboard);
});
$("category-filter").addEventListener("change", () => renderRows(state.dashboard?.emails || []));
$("connect-button").addEventListener("click", connectAccount);
$("clear-results").addEventListener("click", clearResults);
$("new-run").addEventListener("click", () => {
  if (["queued", "fetching", "running"].includes(state.dashboard?.run?.status)) return;
  $("since-date").focus();
  $("system-note").textContent = "Réglez la source, la date et le volume, puis relancez l’analyse.";
});
loadDashboard();
