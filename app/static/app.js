const state = {
  dashboard: null,
  user: null,
  generation: 0,
  editingAccount: null,
  modelInitialized: false,
  expanded: new Set(),
  pollTimer: null,
};

const apiBase = document.querySelector('meta[name="mailaya-root"]')?.content || "";

const $ = (id) => document.getElementById(id);

function setDefaultDate() {
  const date = new Date();
  date.setDate(date.getDate() - 30);
  $("since-date").value = date.toISOString().slice(0, 10);
}

async function api(path, options = {}) {
  const response = await fetch(apiBase + path, {
    ...options,
    headers: { "Content-Type": "application/json", "X-Mailaya-Request": "1", ...(options.headers || {}) },
  });
  if (!response.ok) {
    let message = `Erreur ${response.status}`;
    try {
      const body = await response.json();
      message = body.detail || message;
    } catch (_) {
      // The HTTP status is sufficient when the body is not JSON.
    }
    const error = new Error(message);
    error.status = response.status;
    throw error;
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

function renderAccounts(accounts) {
  const selected = $("imap-account").value;
  $("imap-account").replaceChildren(new Option("Choisir un compte", ""));
  const container = $("imap-accounts");
  container.replaceChildren();
  for (const account of accounts) {
    $("imap-account").add(new Option(`${account.name} · ${account.username}`, String(account.id)));
    const item = text("div", "", "imap-item");
    item.append(text("strong", account.name), text("p", `${account.username} · ${account.host}:${account.port} · ${account.mailbox}`));
    const actions = text("div", "", "account-actions");
    for (const [label, action] of [["Tester", "test"], ["Modifier", "edit"], ["Supprimer", "delete"]]) {
      const button = text("button", label, "text-button");
      button.type = "button";
      button.addEventListener("click", () => accountAction(account, action, button));
      actions.append(button);
    }
    item.append(actions);
    container.append(item);
  }
  if (!accounts.length) container.append(text("p", "Ajoutez votre premier compte pour analyser vos messages IMAP."));
  $("imap-account").value = accounts.some(account => String(account.id) === selected) ? selected : accounts.length === 1 ? String(accounts[0].id) : "";
  $("imap-selector").hidden = !state.user || $("source").value !== "imap";
}

function renderSession(user) {
  state.user = user;
  $("user-copy").textContent = user ? `Connecté : ${user.username} · votre espace personnel.` : "Mode public · messages de démonstration uniquement.";
  $("logout").hidden = !user;
  $("login-panel").hidden = Boolean(user);
  $("password-panel").hidden = !user;
  $("imap-panel").hidden = !user;
  // Remove IMAP entirely from the public source selector.
  const source = $("source").value;
  $("source").replaceChildren(new Option("Démonstration", "demo"));
  if (user) $("source").add(new Option("IMAP", "imap"));
  $("source").value = user && source === "imap" ? "imap" : "demo";
  if (!user) $("imap-selector").hidden = true;
}

function resetDashboard() {
  state.generation += 1;
  state.dashboard = null;
  state.expanded.clear();
  state.modelInitialized = false;
  state.editingAccount = null;
  schedulePoll(false);
  $("imap-form").reset();
  $("imap-form").hidden = true;
  $("password-form").reset();
  $("imap-accounts").replaceChildren();
  $("imap-note").textContent = "";
  renderRows([]);
  renderCategoryFilter([]);
  renderCategorySummary({});
  $("system-note").textContent = "Chargement de votre espace…";
}

function renderDashboard(payload) {
  state.dashboard = payload;
  const run = payload.run;
  const emails = payload.emails || [];
  const metrics = payload.metrics || {};
  renderCategoryFilter(emails);
  renderRows(emails);
  renderCategorySummary(metrics.categories || {});
  renderAccounts(payload.imap_accounts || []);
  if (!state.modelInitialized) {
    $("model").value = payload.configuration.default_model;
    state.modelInitialized = true;
  }
  if (run && ["queued", "fetching", "running", "paused"].includes(run.status)) {
    $("model").value = run.model_backend === "laya-pytorch" ? "laya" : "julia";
    $("source").value = run.source;
    $("since-date").value = run.since_date;
    $("limit").value = String(run.requested_limit);
    if (run.imap_account_id) $("imap-account").value = String(run.imap_account_id);
    $("imap-selector").hidden = run.source !== "imap";
  }

  $("model-copy").textContent = payload.configuration.backend === "demonstration"
    ? "Moteur de démonstration, aucune donnée externe"
    : `${payload.configuration.model}, données traitées en local`;

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
  const sourceReady = selectedSource === "demo" || Boolean(state.user && $("imap-account").value);
  $("run-button-label").textContent = active ? "Mettre en pause" : paused ? "Reprendre l’analyse" : "Lancer l’analyse";
  $("run-button").dataset.action = active ? "pause" : paused ? "resume" : "start";
  $("run-button").disabled = !active && !paused && !sourceReady;
  $("source").disabled = active || paused;
  $("limit").disabled = active || paused;
  $("model").disabled = active || paused;
  $("imap-account").disabled = active || paused;
  $("since-date").disabled = active || paused;
  $("clear-results").disabled = active;
  $("results-summary").textContent = run
    ? `${total} message${total > 1 ? "s" : ""} depuis le ${new Date(`${run.since_date}T00:00:00`).toLocaleDateString("fr-FR")}`
    : "Lancez une démonstration pour découvrir le classement.";

  if (run?.error) $("system-note").textContent = run.error;
  else if (active) $("system-note").textContent = `${processed} traité${processed > 1 ? "s" : ""}, capacité locale active.`;
  else if (paused) $("system-note").textContent = "Exécution en pause. Les résultats déjà calculés sont conservés.";
  else if (status === "complete") $("system-note").textContent = `Terminé avec ${run.model || payload.configuration.backend}.`;
  else $("system-note").textContent = "Prêt pour une démonstration locale.";

  schedulePoll(active);
}

function schedulePoll(shouldPoll) {
  clearTimeout(state.pollTimer);
  if (shouldPoll) state.pollTimer = setTimeout(loadDashboard, 650);
}

async function loadDashboard() {
  const generation = state.generation;
  try {
    const payload = await api("/api/dashboard");
    if (generation === state.generation) renderDashboard(payload);
  } catch (error) {
    if (generation !== state.generation) return;
    if (error.status === 401) {
      resetDashboard();
      renderSession(null);
      await api("/api/logout", { method: "POST" });
      $("session-note").textContent = error.message;
      await loadDashboard();
      return;
    }
    $("system-note").textContent = error.message;
    schedulePoll(false);
  }
}

async function handleRun(event) {
  event.preventDefault();
  const action = $("run-button").dataset.action || "start";
  const run = state.dashboard?.run;
  let errorMessage = null;
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
          model: $("model").value,
          imap_account_id: $("source").value === "imap" ? Number($("imap-account").value) : null,
        }),
      });
    }
    await loadDashboard();
  } catch (error) {
    errorMessage = error.message;
  } finally {
    if (state.dashboard) renderDashboard(state.dashboard);
    if (errorMessage) $("system-note").textContent = errorMessage;
  }
}

async function authenticate(register = false) {
  if (!$("login-form").reportValidity()) return;
  const buttons = $("login-form").querySelectorAll("button");
  buttons.forEach(button => button.disabled = true);
  try {
    const payload = await api(register ? "/api/users" : "/api/login", {
      method: "POST", body: JSON.stringify({ username: $("login-username").value, password: $("login-password").value }),
    });
    resetDashboard();
    renderSession(payload.user);
    $("login-form").reset();
    $("session-note").textContent = register ? "Votre compte est créé. Vous pouvez ajouter vos boîtes IMAP." : "Connexion établie.";
    await loadDashboard();
  } catch (error) {
    $("session-note").textContent = error.message;
  } finally {
    buttons.forEach(button => button.disabled = false);
  }
}

function editAccount(account = null) {
  state.editingAccount = account?.id || null;
  $("imap-form").reset();
  for (const field of ["name", "host", "port", "security", "username", "mailbox"]) {
    if (account) $(`imap-${field}`).value = account[field];
  }
  $("imap-form-title").textContent = account ? "Modifier le compte" : "Ajouter un compte";
  $("imap-password-label").textContent = account ? "Mot de passe IMAP · laisser vide pour le conserver" : "Mot de passe IMAP";
  $("imap-password").required = !account;
  $("imap-form").hidden = false;
  $("imap-name").focus();
}

async function accountAction(account, action, button) {
  if (action === "edit") { editAccount(account); return; }
  button.disabled = true;
  try {
    await api(`/api/imap/accounts/${account.id}${action === "test" ? "/test" : ""}`, { method: action === "test" ? "POST" : "DELETE" });
    $("imap-note").textContent = action === "test" ? `Connexion à ${account.name} réussie. Le dossier est accessible en lecture seule.` : `Le compte ${account.name} a été supprimé de votre espace.`;
    await loadDashboard();
  } catch (error) {
    $("imap-note").textContent = error.message;
  } finally {
    button.disabled = false;
  }
}

async function saveAccount(event) {
  event.preventDefault();
  const button = $("imap-form").querySelector('button[type="submit"]');
  button.disabled = true;
  const body = {};
  for (const field of ["name", "host", "port", "security", "username", "mailbox"]) body[field] = $(`imap-${field}`).value;
  body.port = Number(body.port);
  body.password = $("imap-password").value || null;
  try {
    const id = state.editingAccount;
    const payload = await api(`/api/imap/accounts${id ? `/${id}` : ""}`, { method: id ? "PUT" : "POST", body: JSON.stringify(body) });
    $("imap-form").reset();
    $("imap-form").hidden = true;
    state.editingAccount = null;
    $("source").value = "imap";
    await loadDashboard();
    $("imap-account").value = String(payload.account.id);
    if (state.dashboard) renderDashboard(state.dashboard);
    $("imap-note").textContent = "Compte enregistré. Utilisez Tester pour vérifier la connexion au serveur.";
  } catch (error) {
    $("imap-note").textContent = error.message;
  } finally {
    button.disabled = false;
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
$("imap-account").addEventListener("change", () => { if (state.dashboard) renderDashboard(state.dashboard); });
$("clear-results").addEventListener("click", clearResults);
$("new-run").addEventListener("click", () => {
  if (!state.dashboard || ["queued", "fetching", "running"].includes(state.dashboard.run?.status)) return;
  state.generation += 1;
  renderDashboard({ ...state.dashboard, run: null, emails: [], metrics: {} });
  $("since-date").focus();
  $("system-note").textContent = "Réglez la source, la date et le volume, puis relancez l’analyse.";
});
$("login-form").addEventListener("submit", event => { event.preventDefault(); authenticate(); });
$("register").addEventListener("click", () => authenticate(true));
$("logout").addEventListener("click", async () => {
  try {
    await api("/api/logout", { method: "POST" });
    resetDashboard();
    renderSession(null);
    $("session-note").textContent = "Vous êtes déconnecté. Le mode public propose uniquement la démonstration.";
    await loadDashboard();
  } catch (error) { $("session-note").textContent = error.message; }
});
$("password-form").addEventListener("submit", async event => {
  event.preventDefault();
  try {
    await api("/api/password", { method: "PUT", body: JSON.stringify({ current_password: $("current-password").value, new_password: $("new-password").value }) });
    $("password-form").reset();
    $("password-panel").open = false;
    $("session-note").textContent = "Mot de passe enregistré. Vos autres sessions ont été fermées.";
  } catch (error) { $("session-note").textContent = error.message; }
});
$("add-account").addEventListener("click", () => editAccount());
$("cancel-account").addEventListener("click", () => { $("imap-form").reset(); $("imap-form").hidden = true; state.editingAccount = null; });
$("imap-form").addEventListener("submit", saveAccount);
$("imap-security").addEventListener("change", () => { $("imap-port").value = $("imap-security").value === "ssl" ? "993" : "143"; });
async function initialize() {
  try {
    const payload = await api("/api/session");
    if (!payload.user) await api("/api/logout", { method: "POST" });
    renderSession(payload.user);
    await loadDashboard();
  } catch (error) { $("session-note").textContent = error.message; }
}
initialize();
