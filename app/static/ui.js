/* Navigation and progressive disclosure. Panels retain drafts when hidden. */
(() => {
  let data = null;
  let page = "messages", settings = "mailboxes";
  let sessionReady = false;
  const names = { messages: "Messages", brief: "Brief quotidien", analyses: "Analyses", settings: "Paramètres" };
  $("brief-slot").append($("brief-panel"));
  $("history-slot").append($("history-panel"));
  $("comparison-slot").append($("comparison-panel"));
  $("settings-connections").append($("connection-note"));

  function show(next, section = settings, focus = true) {
    page = Object.hasOwn(names, next) ? next : "messages";
    settings = ["mailboxes", "features", "connections", "rules", "account"].includes(section) ? section : "mailboxes";
    if (page === "settings" && sessionReady && !state.user) settings = "account";
    for (const panel of document.querySelectorAll("[data-page-panel]")) panel.hidden = panel.dataset.pagePanel !== page;
    for (const button of document.querySelectorAll("[data-page]")) {
      if (button.dataset.page === page) button.setAttribute("aria-current", "page");
      else button.removeAttribute("aria-current");
    }
    for (const panel of document.querySelectorAll("[data-settings-panel]")) panel.hidden = panel.dataset.settingsPanel !== settings;
    for (const button of document.querySelectorAll("[data-settings]")) {
      if (button.dataset.settings === settings) button.setAttribute("aria-current", "page");
      else button.removeAttribute("aria-current");
      button.disabled = !state.user && button.dataset.settings !== "account";
    }
    $("page-context").textContent = names[page];
    const hash = "#" + page + (page === "settings" ? "/" + settings : "");
    if (location.hash !== hash) history.replaceState(null, "", hash);
    document.querySelector(".profile-menu").open = false;
    if (focus) {
      const heading = $("page-" + page).querySelector("h1");
      heading.tabIndex = -1; heading.focus({ preventScroll: true });
      window.scrollTo({ top: 0, behavior: "instant" });
    }
  }
  function openSettings(section, account) {
    show("settings", section);
    if (account !== undefined && state.user) {
      const id = section === "rules" ? "rule-account" : "feature-account";
      $(id).value = String(account);
      $(id).dispatchEvent(new Event("change", { bubbles: true }));
    }
  }
  function dependencies() {
    $("sync-options").hidden = !$("feature-sync_enabled").checked;
    $("brief-options").hidden = !$("feature-brief_enabled").checked;
    $("brief-schedule").hidden = !$("feature-brief_auto").checked;
    $("llm-account-options").hidden = !($("feature-brief_enabled").checked && $("feature-llm_enabled").checked || $("feature-natural_search_enabled").checked);
    $("notification-options").hidden = !$("feature-notifications_enabled").checked;
  }
  function availability() {
    const brief = data?.profiles[String($("brief-account").value || 0)]?.options;
    const natural = data?.profiles[String($("natural-account").value || 0)]?.options;
    $("brief-setup").hidden = Boolean(state.user && brief?.brief_enabled);
    $("brief-panel").hidden = !state.user || !brief?.brief_enabled;
    $("configure-brief").textContent = state.user ? "Configurer ce brief" : "Se connecter pour commencer";
    $("natural-submit").disabled = !natural?.natural_search_enabled || !natural.connection_id || $("natural-submit").dataset.busy === "true";
    $("configure-natural").hidden = Boolean(natural?.natural_search_enabled && natural.connection_id);
    $("natural-availability").textContent = natural?.natural_search_enabled && natural.connection_id
      ? "Votre demande sera traduite en filtres visibles. Aucun aperçu de mail n’est envoyé pour cette recherche."
      : "Activez la recherche naturelle et associez une connexion IA pour cette boîte.";
    $("generate-brief").disabled = !brief?.brief_enabled || $("generate-brief").dataset.busy === "true";
    dependencies();
  }
  function session(user) {
    sessionReady = true;
    $("session-badge").textContent = user ? user.username : "Se connecter";
    $("settings-login-hint").hidden = Boolean(user);
    if (!user && page === "settings") show("settings", "account", false);
    else show(page, settings, false);
    availability();
  }
  function update(next) { data = next; availability(); }
  function filterSummary(filters, total) {
    const labels = [];
    if (filters.q) labels.push(`« ${filters.q} »`);
    if (filters.sender) labels.push("Expéditeur");
    if (filters.category) labels.push(filters.category);
    if (filters.since || filters.until) labels.push("Période");
    if (filters.priority_min || filters.action_min || filters.spam_max < 100) labels.push("Scores");
    if (filters.task !== "all") labels.push(({todo:"À faire",done:"Traité",snoozed:"Reporté"})[filters.task]);
    if (filters.conversations || filters.conversation) labels.push("Conversation");
    if (filters.run_id) labels.push(`Analyse #${filters.run_id}`);
    if (filters.demo_only) labels.push("Démonstration");
    $("active-filter-copy").textContent = labels.join(" · ");
    $("filter-count").textContent = labels.length;
    $("filter-count").hidden = !labels.length;
    $("clear-filters").hidden = !labels.length && !filters.account_id;
    const hasMessages = data?.history.some(run => run.total > 0);
    $("empty-heading").textContent = total ? "Vos messages commencent ici" : hasMessages ? "Aucun message dans cette vue" : "Vos messages commencent ici";
    $("empty-copy").textContent = hasMessages ? "Modifiez vos filtres ou réinitialisez la recherche pour retrouver vos messages." : "Importez un premier lot depuis Analyses, ou essayez la démonstration.";
    $("empty-state").querySelector("button").hidden = Boolean(hasMessages);
  }
  function editConnection() { show("settings", "connections"); $("connection-form").hidden = false; $("cancel-connection").hidden = false; $("connection-form-title").textContent = "Modifier la connexion"; $("llm-name").focus(); }
  function reset() {
    data = null;
    $("connection-form").hidden = true; $("rule-form").hidden = true;
    $("message-reader").hidden = true; $("mail-workspace").classList.remove("reader-open");
    $("reader-content").replaceChildren();
    $("natural-panel").hidden = true; $("natural-toggle").setAttribute("aria-expanded", "false");
    $("clear-confirm").hidden = true;
    availability();
  }
  window.MailayaUI = { show, openSettings, update, session, filterSummary, dependencies, editConnection, reset };
  for (const button of document.querySelectorAll("[data-page]")) button.addEventListener("click", () => show(button.dataset.page));
  for (const button of document.querySelectorAll("[data-go]")) button.addEventListener("click", () => show(button.dataset.go));
  for (const button of document.querySelectorAll("[data-settings]")) button.addEventListener("click", () => show("settings", button.dataset.settings));
  for (const button of document.querySelectorAll("[data-open-settings]")) button.addEventListener("click", () => openSettings(button.dataset.openSettings));
  $("configure-brief").addEventListener("click", () => openSettings("features", Number($("brief-account").value)));
  $("configure-natural").addEventListener("click", () => openSettings("features", Number($("natural-account").value)));
  $("history-open").addEventListener("click", () => show("messages"));
  function naturalPanel(open) { $("natural-panel").hidden = !open; $("natural-toggle").setAttribute("aria-expanded", String(open)); if (open) $("natural-query").focus(); }
  $("natural-toggle").addEventListener("click", () => naturalPanel($("natural-panel").hidden));
  $("close-natural").addEventListener("click", () => { naturalPanel(false); $("natural-toggle").focus(); });
  $("features-form").addEventListener("change", e => {
    if (e.target.id === "feature-brief_enabled" && !e.target.checked) { $("feature-brief_auto").checked = false; $("feature-llm_enabled").checked = false; }
    dependencies();
    $("features-note").textContent = "Modifications non enregistrées.";
  });
  $("new-connection").addEventListener("click", () => {
    window.MailayaWorkspace.newConnection(); $("connection-form").hidden = false;
    $("connection-form-title").textContent = "Nouvelle connexion"; $("llm-name").focus();
  });
  $("new-rule").addEventListener("click", () => { $("rule-form").hidden = false; $("rule-name").focus(); });
  $("cancel-rule").addEventListener("click", () => { $("rule-form").hidden = true; $("rule-form").reset(); });
  $("cancel-connection").addEventListener("click", () => { $("connection-form").hidden = true; });
  $("cancel-clear").addEventListener("click", () => { $("clear-confirm").hidden = true; });
  $("dismiss-feedback").addEventListener("click", () => { $("workspace-note").textContent = ""; const heading = $("page-" + page).querySelector("h1"); heading.tabIndex=-1; heading.focus({preventScroll:true}); });
  new MutationObserver(() => { $("workspace-feedback").hidden = !$("workspace-note").textContent; }).observe($("workspace-note"), {childList:true,characterData:true,subtree:true});
  window.addEventListener("hashchange", () => { const [next, section] = location.hash.slice(1).split("/"); if (Object.hasOwn(names, next)) show(next, section); });
  const [initial, section] = location.hash.slice(1).split("/"); show(initial || "messages", section, false);
  if (state.user) session(state.user);
  else availability();
})();
