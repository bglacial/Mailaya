/* Personal workspace. Keep untrusted mail/model text in textContent only. */
(() => {
  const w = { data: null, emails: [], loaded: false, offset: 0, total: 0, todo: false, review: false,
    runId: null, conversation: "", demoOnly: false, sequence: 0, dirty: false, featureScope: 0, lastRefresh: 0, lastRunKey: null, notified: new Set(), briefs: [], briefScope: null, editingConnection: null, selectedEmail: null, readerEmail: null };
  const base = "/api/workspace";
  const booleanFields = ["sync_enabled", "brief_enabled", "brief_auto", "llm_enabled", "natural_search_enabled", "comparison_enabled", "notifications_enabled"];
  const numberFields = ["sync_minutes", "sync_limit", "brief_hour"];
  const mappings = { q: "mail-query", account_id: "mail-account", sender: "filter-sender", category: "filter-category",
    since: "filter-since", until: "filter-until", priority_min: "filter-priority", action_min: "filter-action",
    spam_max: "filter-spam", task: "filter-task", sort: "filter-sort", conversations: "filter-conversations" };
  const accountId = (context = "settings") => Number($(({brief:"brief-account", natural:"natural-account", rules:"rule-account"})[context] || "feature-account").value || 0);
  const profile = (context = "settings") => w.data?.profiles?.[String(accountId(context))];
  async function request(path, options) {
    const generation = state.generation, user = state.user?.id;
    const result = await api(base + path, options);
    if (generation !== state.generation || user !== state.user?.id) throw new Error("Votre espace a changé. Relancez la demande.");
    return result;
  }
  async function action(button, note, callback) {
    if (button) { button.disabled = true; button.dataset.busy = "true"; button.setAttribute("aria-busy", "true"); }
    const list = note === "workspace-note";
    delete $(note).dataset.kind;
    $(note).textContent = list ? "" : "En cours…";
    if (list) $("mail-workspace").setAttribute("aria-busy", "true");
    try { await callback(); } catch (error) { $(note).textContent = error.message; $(note).dataset.kind = "error"; }
    finally {
      if (list) $("mail-workspace").removeAttribute("aria-busy");
      if (button) { button.disabled = false; delete button.dataset.busy; button.removeAttribute("aria-busy"); }
      window.MailayaUI?.update(w.data);
      if (button?.id === "compare-models" && w.data) renderSettings();
    }
  }
  const json = (method, body) => ({ method, body: JSON.stringify(body) });
  function select(id, options, first) {
    const element = $(id), value = element.value;
    element.replaceChildren(new Option(first, ""));
    for (const [label, key] of options) element.add(new Option(label, String(key)));
    element.value = [...element.options].some(o => o.value === value) ? value : "";
  }
  function filters() {
    const value = { offset: w.offset, limit: 50, todo: w.todo, review: w.review, run_id: w.runId, conversation: w.conversation, demo_only: w.demoOnly };
    for (const [key, id] of Object.entries(mappings)) {
      value[key] = $(id).type === "checkbox" ? $(id).checked : $(id).value;
    }
    value.account_id = value.account_id ? Number(value.account_id) : null;
    for (const key of ["priority_min", "spam_max", "action_min"]) value[key] = Number(value[key]);
    return value;
  }
  function applyFilters(value) {
    $("natural-result").textContent = "";
    w.offset = 0; w.demoOnly = Boolean(value.demo_only); w.conversation = value.conversation || ""; w.todo = Boolean(value.todo); w.review = Boolean(value.review); w.runId = value.run_id || null;
    for (const [key, id] of Object.entries(mappings)) {
      if ($(id).type === "checkbox") $(id).checked = Boolean(value[key]);
      else $(id).value = value[key] ?? ({ spam_max: 100, task: "all", sort: "date" }[key] ?? "");
    }
    $("run-history").value = w.runId || "";
    tabs();
  }
  function tabs() {
    $("view-all").setAttribute("aria-pressed", String(!w.todo && !w.review));
    $("view-todo").setAttribute("aria-pressed", String(w.todo));
    $("view-review").setAttribute("aria-pressed", String(w.review));
  }
  async function search(forceRender = true) {
    if (!state.user) return;
    const seq = ++w.sequence;
    const params = new URLSearchParams(Object.entries(filters()).filter(([, v]) => v !== null));
    const result = await request("/messages?" + params);
    if (seq !== w.sequence) return;
    w.emails = result.emails; w.total = result.total; w.loaded = true;
    w.forceRender = forceRender; renderRows([]); w.forceRender = false;
    $("page-count").textContent = result.total ? `${w.offset + 1}–${Math.min(w.offset + 50, result.total)} sur ${result.total}` : "";
    $("previous-page").disabled = w.offset === 0;
    $("next-page").disabled = w.offset + 50 >= result.total;
    $("results-summary").textContent = `${result.total} message${result.total > 1 ? "s" : ""}${w.runId ? ` · analyse #${w.runId}` : w.demoOnly ? " · démonstration personnelle" : " · historique personnel"}`;
    window.MailayaUI?.filterSummary(filters(), result.total);
  }
  function field(label, input) {
    const node = text("label", ""); node.append(text("span", label), input); return node;
  }
  function localInput(value) {
    const date = new Date(value); return new Date(date - date.getTimezoneOffset() * 60000).toISOString().slice(0,16);
  }
  function editor(email) {
    const section = text("section", "", "mail-editor"); section.setAttribute("aria-labelledby", "reader-task-heading");
    const heading = text("h3", "Mon suivi"); heading.id = "reader-task-heading";
    const note = text("p", "Le suivi reste dans Mailaya. Aucun mail n’est modifié.", "editor-note"); note.setAttribute("role", "status");
    async function save(changes, message, control) {
      if (control) control.disabled = true;
      try {
        await request(`/messages/${email.id}`, json("PUT", { category: email.correction.category || null, priority: email.correction.priority ?? null,
          task: email.task, snoozed_until: email.task === "snoozed" ? email.snoozed_until : null, ...changes }));
        for (const form of section.querySelectorAll("form")) form.dataset.dirty = "false";
        w.readerEmail = await request(`/messages/${email.id}`);
        await search(); renderReader(w.readerEmail, true);
        $("reader-content").querySelector(".editor-note").textContent = message;
      } catch (error) { note.textContent = error.message; }
      finally { if (control) control.disabled = false; }
    }
    const group = text("div", "", "segmented"); group.setAttribute("role", "group"); group.setAttribute("aria-labelledby", heading.id);
    const until = document.createElement("input"); until.type = "datetime-local"; until.required = true;
    if (email.snoozed_until) until.value = localInput(email.snoozed_until);
    const snooze = text("form", "", "snooze-form"); snooze.hidden = email.task !== "snoozed";
    const snoozeButton = text("button", email.task === "snoozed" ? "Modifier le report" : "Reporter", "secondary-button"); snoozeButton.type = "submit";
    snooze.append(field("Jusqu’au, heure de votre navigateur", until), snoozeButton);
    snooze.addEventListener("input", () => { snooze.dataset.dirty = "true"; });
    snooze.addEventListener("submit", event => {
      event.preventDefault();
      if (!until.value) { note.textContent = "Choisissez une date de report."; return; }
      save({ task: "snoozed", snoozed_until: new Date(until.value).toISOString() }, "Message reporté.", snoozeButton);
    });
    for (const [label, value] of [["À faire", "todo"], ["Traité", "done"], ["Reporté…", "snoozed"]]) {
      const choice = text("button", label); choice.type = "button"; choice.setAttribute("aria-pressed", String(email.task === value));
      choice.addEventListener("click", () => {
        if (value === "snoozed") {
          snooze.hidden = false;
          if (!until.value) { const tomorrow = new Date(); tomorrow.setDate(tomorrow.getDate() + 1); tomorrow.setHours(8, 0, 0, 0); until.value = localInput(tomorrow); }
          until.focus(); return;
        }
        if (email.task === value) { snooze.hidden = true; return; }
        save({ task: value, snoozed_until: null }, value === "done" ? "Marqué comme traité." : "Remis à faire.", choice);
      });
      group.append(choice);
    }
    if (email.task === "snoozed" && email.snoozed_until) note.textContent = `Reporté jusqu’au ${new Date(email.snoozed_until).toLocaleString("fr-FR", { dateStyle: "medium", timeStyle: "short" })}.`;
    const category = document.createElement("input"); category.value = email.correction.category || ""; category.maxLength = 100;
    const priority = document.createElement("input"); priority.type = "number"; priority.min = 0; priority.max = 100; priority.value = email.correction.priority ?? "";
    const corrections = document.createElement("details"); corrections.className = "correction-details";
    const correctionForm = text("form", "", "correction-form");
    const saveCorrection = text("button", "Enregistrer la correction", "secondary-button"); saveCorrection.type = "submit";
    const cancel = text("button", "Annuler", "text-button"); cancel.type = "button";
    cancel.addEventListener("click", () => { category.value = email.correction.category || ""; priority.value = email.correction.priority ?? ""; correctionForm.dataset.dirty = "false"; note.textContent = "Modifications annulées."; });
    const actions = text("div", "", "editor-actions"); actions.append(saveCorrection, cancel);
    if (email.correction.category || email.correction.priority != null) {
      const reset = text("button", "Retirer mes corrections", "text-button"); reset.type = "button";
      reset.addEventListener("click", () => save({ category: null, priority: null }, "Corrections retirées. La prédiction du modèle s’applique.", reset));
      actions.append(reset);
    }
    correctionForm.append(field("Ma catégorie, facultatif", category), field("Ma priorité / 100, facultatif", priority), actions);
    correctionForm.addEventListener("input", () => { correctionForm.dataset.dirty = "true"; note.textContent = "Correction non enregistrée."; });
    correctionForm.addEventListener("submit", event => {
      event.preventDefault();
      save({ category: category.value.trim() || null, priority: priority.value === "" ? null : Number(priority.value) }, "Correction enregistrée. La prédiction initiale est conservée.", saveCorrection);
    });
    corrections.append(text("summary", "Corriger le classement"), correctionForm);
    section.append(heading, group, snooze, note, corrections);
    return section;
  }
  function readerDirty() { return Boolean($("reader-content").querySelector('form[data-dirty="true"]')); }
  function renderReader(email, force=false) {
    if (!email) return;
    if (!force && readerDirty()) return;
    const content = $("reader-content"); content.replaceChildren();
    content.append(text("div",email.sender_name,"sender-name"),text("h2",email.subject,"reader-heading"),text("p",`${email.sender_address} · ${new Date(email.received_at).toLocaleString("fr-FR")}`,"reader-meta"));
    if (email.status === "complete") {
      const tags = text("p", "", "reader-classification"), level = priorityLabel(email.effective_priority || 0);
      const priorityTag = text("span", "Priorité " + level.label.toLocaleLowerCase("fr-FR"), "priority-label"); priorityTag.dataset.level = level.level;
      tags.append(text("span", email.effective_category, "tag"), priorityTag);
      if (email.needs_review) tags.append(text("span", "À vérifier", "review-label"));
      if (email.decision_source !== "model") tags.append(text("span", email.decision_source === "manual" ? "Corrigé" : "Règle", "review-label"));
      content.append(tags);
    }
    content.append(text("p",email.body_preview,"mail-preview"));
    if (email.status === "complete") content.append(editor(email));
    if (email.error) content.append(text("p",email.error));
    const details = document.createElement("details"); details.className = "classification-details";
    details.append(text("summary","Comprendre le classement"));
    const decision = email.decision_source === "manual" ? "Votre correction" : email.decision_source.startsWith("rule:") ? "Règle : " + email.decision_source.slice(6) : "Modèle";
    details.append(text("p",`Décision affichée : ${decision}. Prédiction initiale : ${email.category || "en attente"}, priorité ${email.priority_score ?? "–"}/100.`),text("p",`Spam ${formatNumber(email.spam_score)} % · Action ${formatNumber(email.action_score)} % · Inférence ${formatNumber(email.duration_ms,1)} ms.`));
    const scores = text("ul", "");
    for (const [name, score] of Object.entries(email.category_scores).sort((a,b)=>b[1]-a[1])) { const li=text("li",""); li.append(text("span",name),text("span",`${formatNumber(score*100,1)} %`)); scores.append(li); }
    details.append(scores); content.append(details);
    if (email.conversation_ids?.length > 1) content.append(button("Ouvrir cette conversation", b => action(b,"workspace-note",async()=>{w.conversation=email.conversation; $("filter-conversations").checked=false; w.offset=0; await search(); $("workspace-note").textContent="Conversation ouverte.";})));
    $("message-reader").hidden = false; $("mail-workspace").classList.add("reader-open");
  }
  function openReader(email) {
    if (readerDirty() && email.id !== w.selectedEmail) { $("reader-content").querySelector(".editor-note").textContent = "Enregistrez ou annulez vos modifications avant de changer de message."; return; }
    const changed = w.selectedEmail !== email.id;
    w.selectedEmail = email.id; w.readerEmail = email; rows();
    if (changed) {
      $("message-reader").scrollTop = 0;
      const heading = $("reader-content").querySelector("h2"); heading.tabIndex = -1; heading.focus({ preventScroll: true });
      if (window.matchMedia("(max-width: 900px)").matches) $("message-reader").scrollIntoView({ block: "start", behavior: "auto" });
    }
  }
  function closeReader() {
    if (readerDirty()) { $("reader-content").querySelector(".editor-note").textContent = "Enregistrez ou annulez vos modifications avant de fermer."; return; }
    const index = w.emails.findIndex(email => email.id === w.selectedEmail);
    w.selectedEmail = null; w.readerEmail = null; $("message-reader").hidden = true; $("mail-workspace").classList.remove("reader-open"); rows();
    const subjects = $("mail-rows").querySelectorAll(".mail-subject");
    if (index >= 0) subjects[index]?.focus();
    else $("mail-query").focus();
  }
  function rows() {
    if (!state.user || !w.loaded) return false;
    const tbody=$("mail-rows"); tbody.replaceChildren(); $("empty-state").hidden=w.emails.length>0;
    for (const email of w.emails) {
      const row=document.createElement("tr"); row.dataset.status=email.status; row.dataset.selected=String(w.selectedEmail===email.id);
      const message=text("div","");
      const subject=text("button",email.subject,"mail-subject"); subject.type="button"; subject.setAttribute("aria-expanded",String(w.selectedEmail===email.id)); subject.setAttribute("aria-controls","message-reader"); subject.addEventListener("click",()=>openReader(email));
      const line=text("div","","mail-line"), time=text("time",shortDate(email.received_at),"mail-date"); time.dateTime=email.received_at; time.title=new Date(email.received_at).toLocaleString("fr-FR");
      line.append(text("span",email.sender_name,"sender-name"),time);
      message.append(line,subject,text("div",email.body_preview.slice(0,140),"preview"));
      if(email.conversation_count) message.append(text("small",`${email.conversation_count} messages`));
      const category=text("div",email.effective_category||(email.status==="failed"?"Échec":"En attente"));
      if(email.needs_review) category.append(text("small","À vérifier"));
      if(email.decision_source!=="model") category.append(text("small",email.decision_source==="manual"?"Corrigé":"Règle"));
      const priority=priorityLabel(email.effective_priority||0), priorityNode=text("span",priority.label,"priority-label"); priorityNode.dataset.level=priority.level; priorityNode.title=`${email.effective_priority||0}/100`;
      const status=email.task==="todo"?text("span","","task-label"):text("span",({done:"Traité",snoozed:"Reporté"})[email.task],"task-label"); status.dataset.task=email.task;
      if(email.task==="todo") status.append(text("span","À faire","sr-only"));
      row.dataset.task=email.task; row.addEventListener("click",event=>{ if(!event.target.closest("button,a")) openReader(email); });
      row.append(makeCell(message,"message-cell"),makeCell(category,"category-cell"),makeCell(priorityNode),makeCell(status)); tbody.append(row);
    }
    if(w.selectedEmail) renderReader(w.emails.find(e=>e.id===w.selectedEmail)||w.readerEmail);
    return true;
  }
  function shortDate(value) {
    const date = new Date(value), now = new Date();
    if (date.toDateString() === now.toDateString()) return date.toLocaleTimeString("fr-FR", { hour: "2-digit", minute: "2-digit" });
    return date.toLocaleDateString("fr-FR", { day: "numeric", month: "short", ...(date.getFullYear() !== now.getFullYear() ? { year: "numeric" } : {}) });
  }
  function fillOptions() {
    const value = profile()?.options;
    if (!value) return;
    for (const key of booleanFields) $("feature-" + key).checked = value[key];
    for (const key of [...numberFields, "sync_model", "timezone"]) $("feature-" + key).value = value[key];
    const connectionId = String(value.connection_id || "");
    $("feature-connection_id").value = [...$("feature-connection_id").options].some(option => option.value === connectionId) ? connectionId : "";
    $("feature-sync_enabled").disabled = accountId() === 0;
    w.dirty = false; w.featureScope = accountId(); locationCopy(); window.MailayaUI?.dependencies();
    const runtime = profile().runtime;
    $("features-note").textContent = runtime.sync_error || runtime.brief_error || (runtime.last_sync ? `Dernier passage : ${new Date(runtime.last_sync * 1000).toLocaleString("fr-FR")}` : "Réglages propres à ce compte.");
  }
  function locationCopy() {
    const connection = w.data?.connections.find(c => c.id === Number($("feature-connection_id").value));
    $("processing-location").textContent = connection ? `${connection.allow_remote ? "Fournisseur externe autorisé" : "Serveur local ou réseau privé"} : ${connection.name} · ${connection.model}. Le brief envoie uniquement les aperçus sélectionnés ; la recherche envoie votre demande et les catégories disponibles.` : "Sans connexion LLM : brief préparé par règles locales. La recherche naturelle nécessite une connexion.";
  }
  function button(label, callback) {
    const result = text("button", label, "text-button"); result.type = "button"; result.addEventListener("click", () => callback(result)); return result;
  }
  function renderSettings() {
    const accounts = w.data.accounts.map(a => [a.name, a.id]);
    select("mail-account", accounts, "Toutes les boîtes");
    for (const id of ["feature-account","brief-account","natural-account","rule-account"]) {
      const old=$(id).value||"0"; $(id).replaceChildren(new Option("Démonstration personnelle","0"));
      for (const [name,key] of accounts) $(id).add(new Option(name,String(key)));
      $(id).value=[...$(id).options].some(o=>o.value===old)?old:"0";
    }
    select("feature-connection_id", w.data.connections.map(c => [`${c.name} · ${c.model}`, c.id]), "Aucune");
    select("saved-view", w.data.views.map(v => [v.name, v.id]), w.data.views.length ? "Choisir une vue" : "Aucune vue enregistrée");
    $("delete-view").hidden = !$("saved-view").value;
    select("run-history", w.data.history.map(r => [`#${r.id} · ${r.model_backend === "laya-pytorch" ? "LAYA" : "Julia"} · ${{complete:"Terminé",paused:"En pause",failed:"Échec",running:"En cours",queued:"En file",fetching:"Importation",empty:"Vide"}[r.status] || r.status} · ${r.processed}/${r.total} messages`, r.id]), "Dernière analyse");
    if (!w.dirty) fillOptions();
    const connections = $("llm-connections"); connections.replaceChildren();
    for (const c of w.data.connections) {
      const node = text("div", "", "imap-item"); node.append(text("strong", c.name), text("p", `${c.protocol} · ${c.model} · ${c.allow_remote ? "externe autorisé" : "local/réseau privé"}`),
        button("Modifier", () => {
          w.editingConnection = c.id; $("llm-name").value = c.name; $("llm-protocol").value = c.protocol; $("llm-url").value = c.base_url;
          $("llm-key").value = ""; $("llm-remote").checked = Boolean(c.allow_remote);
          $("llm-model").replaceChildren(new Option(c.model, c.model)); $("cancel-connection").hidden = false;
          $("connection-note").textContent = "Clé vide : conserver la clé si le fournisseur et l’adresse restent identiques."; window.MailayaUI?.editConnection();
        }), button("Supprimer", b => action(b, "connection-note", async () => {
          await request(`/connections/${c.id}`, { method: "DELETE" }); await refresh(null, state.generation, true);
          $("connection-note").textContent = "Connexion supprimée. Sélectionnez-en une autre sur les comptes concernés.";
        }))); connections.append(node);
    }
    const rules = $("personal-rules"); rules.replaceChildren();
    for (const rule of w.data.rules.filter(r => r.account_id === accountId("rules"))) {
      const node = text("div", "", "imap-item"); node.append(text("strong", rule.name), text("p", `${({sender:"Expéditeur",subject:"Objet",text:"Objet et aperçu"})[rule.field]} contient « ${rule.contains} » → ${rule.category || "catégorie inchangée"}, priorité ${rule.priority ?? "inchangée"}`),
        button("Supprimer", b => action(b, "workspace-note", async () => { await request(`/rules/${rule.id}`, { method: "DELETE" }); await refresh(null, state.generation, true); $("workspace-note").textContent = "Règle supprimée."; })));
      rules.append(node);
    }
    if (!w.data.connections.length) connections.append(text("p","Aucune connexion IA. Le tri et le brief local fonctionnent sans LLM."));
    if (!rules.hasChildNodes()) rules.append(text("p","Aucune règle pour cette boîte. Le modèle propose le classement, vous gardez la main."));
    const target=w.data.history.find(r=>r.id===(w.runId||state.dashboard?.run?.id));
    const compareAllowed=Boolean(target&&w.data.profiles[String(target.imap_account_id||0)]?.options.comparison_enabled);
    $("compare-models").disabled=!compareAllowed||!["complete","failed"].includes(target?.status)||$("compare-models").dataset.busy==="true";
    $("comparison-availability").textContent=compareAllowed?"L’autre modèle reçoit exactement les mêmes aperçus. Les calculs restent séquentiels.":"Activez la comparaison dans Paramètres, Fonctions par boîte, pour la boîte de ce lot.";
    window.MailayaUI?.update(w.data);
  }
  function notify(key, account, title) {
    if (!w.data?.profiles[String(account)]?.options.notifications_enabled || !("Notification" in window) || Notification.permission !== "granted" || w.notified.has(key)) return;
    w.notified.add(key);
    try { new Notification(title, { body: "Votre espace Mailaya a été mis à jour.", tag: key }); } catch (_) { /* Browser may require a service worker. */ }
  }
  async function refresh(payload, generation, force = false) {
    if (!state.user) return;
    syncIncremental();
    const runKey = payload?.run ? `${payload.run.id}:${payload.run.status}` : "idle";
    if (!force && runKey === w.lastRunKey && Date.now() - w.lastRefresh < 1800) return;
    w.lastRefresh = Date.now();
    w.lastRunKey = runKey;
    const data = await request("");
    if (generation !== state.generation) return;
    const previous = w.data;
    w.data = data; renderSettings(); await search(false);
    if (previous) {
      for (const run of data.history) {
        const old = previous.history.find(r => r.id === run.id);
        if (old && ["queued", "fetching", "running"].includes(old.status) && ["complete", "empty", "failed"].includes(run.status)) {
          notify(`run-${run.id}`, run.imap_account_id || 0, run.status === "failed" ? "Mailaya : analyse en échec" : "Mailaya : analyse terminée");
        }
      }
      for (const [id, p] of Object.entries(data.profiles)) {
        if (p.runtime.last_brief_day && p.runtime.last_brief_day !== previous.profiles[id]?.runtime.last_brief_day) {
          notify(`brief-${id}-${p.runtime.last_brief_day}`, id, "Mailaya : votre brief est prêt");
        }
      }
    }
    const run = payload?.run || state.dashboard?.run;
    const selected=w.runId?w.data.history.find(r=>r.id===w.runId):run;
    if (selected?.reference_run_id) await renderComparison(selected.id);
    const briefChanged = profile("brief")?.runtime.last_brief_day !== previous?.profiles[String(accountId("brief"))]?.runtime.last_brief_day;
    if (profile("brief")?.options.brief_enabled && (w.briefScope!==accountId("brief") || briefChanged)) await loadBriefHistory();
    if (!run || !["queued", "fetching", "running"].includes(run.status)) {
      clearTimeout(state.pollTimer); state.pollTimer = setTimeout(loadDashboard, 15000);
    }
  }
  async function openMail(id) {
    const email=await request(`/messages/${id}`); window.MailayaUI?.show("messages"); openReader(email);
    $("workspace-note").textContent = "";
  }
  function renderBrief(brief) {
    const container = $("brief-content"); container.replaceChildren();
    const day = new Date(brief.day + "T12:00:00").toLocaleDateString("fr-FR", { weekday: "long", day: "numeric", month: "long", year: "numeric" });
    $("brief-mode-copy").textContent = brief.mode === "llm" ? `Résumés enrichis avec ${brief.model}. Relisez les messages sources avant d’agir.` : "Synthèse locale, sans LLM, d’après les messages importés.";
    container.append(text("p", `${day} · ${brief.new_messages} nouveaux messages · ${brief.pending_actions} demandes en attente`, "brief-summary"));
    for (const item of brief.items) {
      const line = text("article", "", "brief-item");
      line.append(button(item.subject, b => action(b, "workspace-note", () => openMail(item.email_id))), text("p", `${item.sender} · priorité ${item.priority}/100`, "brief-meta"));
      const insight = brief.insights.find(i => i.email_id === item.email_id);
      line.append(text("p", insight?.summary || item.summary)); container.append(line);
    }
    if (!brief.items.length) container.append(text("p", "Aucune demande à traiter dans les messages classés de ce compte."));
    for (const deadline of brief.deadlines) container.append(text("p", "Échéance à vérifier : " + deadline.excerpt));
    container.append(text("p", brief.note, "brief-footnote"));
  }
  async function loadBriefHistory() {
    const scope = accountId("brief");
    const result = await request(`/briefs/${scope}`);
    if (scope !== accountId("brief")) return;
    w.briefScope=scope;
    w.briefs = result.briefs;
    select("brief-history", w.briefs.map(b => [b.day, b.id]), "Choisir un jour");
    const selected = w.briefs.find(b => b.id === Number($("brief-history").value)) || w.briefs[0];
    if (selected) { $("brief-history").value = String(selected.id); renderBrief(selected.payload); }
    else { $("brief-mode-copy").textContent = "Demandes encore à faire, d’après les messages importés."; $("brief-content").replaceChildren(text("p","Aucun brief conservé pour cette boîte. Préparez le premier à partir des messages importés.","brief-footnote")); }
  }
  async function renderComparison(id) {
    const result = await request(`/runs/${id}/comparison`);
    $("comparison-panel").hidden = false;
    const node = $("comparison-content"); node.replaceChildren();
    node.append(text("p", `${result.reference.model_backend} → ${result.run.model_backend} · ${result.compared} messages comparés · ${result.disagreements} désaccords · ${result.run.status}.`));
    node.append(text("p", result.labeled ? `Sur ${result.labeled} catégories corrigées : ${formatNumber(result.left_accuracy * 100, 1)} % contre ${formatNumber(result.right_accuracy * 100, 1)} % de correspondance. Échantillon personnel, pas un benchmark général.` : "Corrigez des catégories pour mesurer la qualité. Un accord entre modèles ne prouve pas qu’ils ont raison."));
    const table = document.createElement("table"), head = document.createElement("tr");
    const thead = document.createElement("thead"), tbody = document.createElement("tbody");
    for (const label of ["Objet", "Modèle initial", "Autre modèle", "Temps initial/autre"]) head.append(text("th", label));
    thead.append(head); table.append(thead, tbody);
    for (const pair of result.pairs) {
      const row = document.createElement("tr"); row.append(makeCell(pair.subject), makeCell(pair.left), makeCell(pair.right), makeCell(`${formatNumber(pair.left_ms)} / ${formatNumber(pair.right_ms)} ms`)); tbody.append(row);
    }
    const scroll = text("div", "", "table-scroll"); scroll.append(table); node.append(scroll);
  }
  function syncIncremental() { $("incremental-field").hidden = !state.user || $("source").value !== "imap"; }
  function session(user) {
    for (const id of ["triage-tools", "workspace-settings", "history-panel"]) $(id).hidden = !user;
    $("category-filter").closest("label").hidden = Boolean(user);
    syncIncremental(); window.MailayaUI?.session(user);
    if (!user) { $("brief-panel").hidden = true; $("comparison-panel").hidden = true; }
  }
  function reset() {
    w.sequence++; w.data = null; w.emails = []; w.loaded = false; w.offset = 0; w.runId = null; w.conversation = ""; w.demoOnly = false;
    w.lastRefresh = 0; w.lastRunKey = null; w.todo = false; w.review = false; w.dirty = false; w.briefs = []; w.notified.clear(); w.editingConnection = null; w.briefScope=null; w.selectedEmail=null; w.readerEmail=null; window.MailayaUI?.reset();
    $("search-form").reset(); $("features-form").reset(); $("connection-form").reset(); $("natural-form").reset(); $("rule-form").reset();
    for (const id of ["brief-content", "comparison-content", "llm-connections", "personal-rules"]) $(id).replaceChildren();
    for (const id of ["workspace-note", "features-note", "connection-note", "natural-result"]) $(id).textContent = "";
    $("comparison-panel").hidden = true; $("brief-panel").hidden = true;
    for (const id of ["mail-account", "saved-view", "run-history", "feature-connection_id", "brief-history"]) $(id).replaceChildren(new Option("Choisir", ""));
    for (const id of ["feature-account", "brief-account", "natural-account", "rule-account"]) $(id).replaceChildren(new Option("Démonstration personnelle", "0"));
    w.featureScope = 0; tabs();
  }
  window.MailayaWorkspace = { renderRows: rows, refresh, session, reset, newConnection() { w.editingConnection=null; $("connection-form").reset(); $("cancel-connection").hidden=false; } };
  $("close-reader").addEventListener("click",closeReader);
  $("clear-filters").addEventListener("click",()=>action(null,"workspace-note",async()=>{applyFilters({}); await search();}));
  $("brief-account").addEventListener("change",()=>action(null,"workspace-note",async()=>{w.briefScope=null; window.MailayaUI?.update(w.data); await loadBriefHistory();}));
  $("natural-account").addEventListener("change",()=>window.MailayaUI?.update(w.data));
  $("rule-account").addEventListener("change",()=>renderSettings());
  $("search-form").addEventListener("submit", e => { e.preventDefault(); $("natural-result").textContent=""; w.offset = 0; w.conversation = ""; w.demoOnly = false; action(null, "workspace-note", async () => { await search(); $("search-form").querySelector(".advanced-filters").open = false; }); });
  for (const [id, todo, review] of [["view-all", false, false], ["view-todo", true, false], ["view-review", false, true]]) $(id).addEventListener("click", () => action($(id), "workspace-note", async () => { w.todo = todo; w.review = review; w.offset = 0; tabs(); await search(); if (review) $("workspace-note").textContent = "À vérifier : seuil heuristique, pas une confiance calibrée."; }));
  for (const [id, delta] of [["previous-page", -50], ["next-page", 50]]) $(id).addEventListener("click", () => action($(id), "workspace-note", async () => { w.offset = Math.max(0, w.offset + delta); await search(); }));
  $("features-form").addEventListener("input", () => { w.dirty = true; locationCopy(); });
  $("feature-account").addEventListener("change", () => {
    if (w.dirty) { $("feature-account").value = String(w.featureScope); $("features-note").textContent = "Enregistrez ou annulez vos modifications avant de changer de boîte."; return; }
    action(null, "features-note", async () => renderSettings());
  });
  $("cancel-features").addEventListener("click", () => { fillOptions(); $("features-note").textContent = "Modifications annulées."; });
  $("features-form").addEventListener("submit", e => { e.preventDefault(); action(e.submitter, "features-note", async () => {
    const options = {};
    for (const key of booleanFields) options[key] = $("feature-" + key).checked;
    for (const key of numberFields) options[key] = Number($("feature-" + key).value);
    for (const key of ["sync_model", "timezone"]) options[key] = $("feature-" + key).value;
    options.connection_id = $("feature-connection_id").value ? Number($("feature-connection_id").value) : null;
    if (!accountId()) options.sync_enabled = false;
    await request(`/accounts/${accountId()}/options`, json("PUT", options)); w.dirty = false;
    await refresh(null, state.generation, true); $("features-note").textContent = "Fonctions enregistrées pour cette boîte.";
  }); });
  $("request-notifications").addEventListener("click", () => action($("request-notifications"), "features-note", async () => {
    if (!("Notification" in window) || !window.isSecureContext) throw new Error("Ce navigateur nécessite HTTPS ou localhost pour les notifications.");
    const permission = await Notification.requestPermission(); $("features-note").textContent = permission === "granted" ? "Notifications autorisées. Activez-les pour les comptes souhaités puis enregistrez." : "Notifications non autorisées. Vous pouvez modifier ce choix dans les réglages du navigateur.";
  }));
  function connectionBody() { return { name: $("llm-name").value, protocol: $("llm-protocol").value, base_url: $("llm-url").value, model: $("llm-model").value, api_key: $("llm-key").value || null, allow_remote: $("llm-remote").checked }; }
  $("llm-protocol").addEventListener("change", () => { $("llm-url").value = ({ omlx: "http://127.0.0.1:11435/v1", ollama: "http://127.0.0.1:11434", openai: "https://api.openai.com/v1" })[$("llm-protocol").value]; $("llm-model").replaceChildren(new Option("Récupérez les modèles", "")); });
  $("discover-models").addEventListener("click", () => action($("discover-models"), "connection-note", async () => {
    const body = connectionBody();
    const unchanged = w.data?.connections.find(c => c.id === w.editingConnection && c.base_url === body.base_url && c.protocol === body.protocol);
    const result = unchanged && !body.api_key ? await request(`/connections/${w.editingConnection}/models`) : await request("/connections/discover", json("POST", body));
    select("llm-model", result.models.map(m => [m, m]), "Choisir un modèle");
    $("connection-note").textContent = `${result.models.length} modèles disponibles. Choisissez un modèle puis enregistrez.`;
  }));
  $("connection-form").addEventListener("submit", e => { e.preventDefault(); action(e.submitter, "connection-note", async () => {
    await request(`/connections${w.editingConnection ? `/${w.editingConnection}` : ""}`, json(w.editingConnection ? "PUT" : "POST", connectionBody()));
    $("llm-key").value = ""; w.editingConnection = null; $("cancel-connection").hidden = true; $("connection-form").hidden=true;
    await refresh(null, state.generation, true); $("connection-note").textContent = "Connexion enregistrée. Associez-la à une boîte dans Paramètres, Fonctions par boîte.";
  }); });
  $("cancel-connection").addEventListener("click", () => { w.editingConnection = null; $("connection-form").reset(); $("cancel-connection").hidden = true; });
  $("rule-form").addEventListener("submit", e => { e.preventDefault(); action(e.submitter, "workspace-note", async () => {
    await request("/rules", json("POST", { account_id: accountId("rules"), name: $("rule-name").value, field: $("rule-field").value,
      contains: $("rule-contains").value, category: $("rule-category").value.trim() || null,
      priority: $("rule-priority").value === "" ? null : Number($("rule-priority").value) }));
    $("rule-form").reset(); $("rule-form").hidden=true; await refresh(null, state.generation, true); $("workspace-note").textContent = "Règle ajoutée au compte sélectionné.";
  }); });
  $("save-view").addEventListener("click", () => action($("save-view"), "workspace-note", async () => {
    const name = $("view-name").value.trim(); if (!name) throw new Error("Donnez un nom à la vue.");
    await request("/views", json("POST", { name, filters: { ...filters(), offset: 0 } })); await refresh(null, state.generation, true); $("workspace-note").textContent = "Vue enregistrée dans votre compte.";
  }));
  $("saved-view").addEventListener("change", () => action(null, "workspace-note", async () => { $("delete-view").hidden = !$("saved-view").value; const view = w.data.views.find(v => v.id === Number($("saved-view").value)); if (view) { applyFilters(view.filters); await search(); $("workspace-note").textContent = `Vue « ${view.name} » appliquée.`; } }));
  $("delete-view").addEventListener("click", () => action($("delete-view"), "workspace-note", async () => { const id = $("saved-view").value; if (!id) throw new Error("Choisissez une vue à supprimer."); await request(`/views/${id}`, { method: "DELETE" }); await refresh(null, state.generation, true); $("workspace-note").textContent = "Vue supprimée."; }));
  $("run-history").addEventListener("change", () => action(null, "workspace-note", async () => { w.runId = Number($("run-history").value) || null; w.offset = 0; renderSettings(); await search(); if (w.runId && w.data.history.find(r => r.id === w.runId)?.reference_run_id) await renderComparison(w.runId); else $("comparison-panel").hidden = true; $("workspace-note").textContent = w.runId ? `Historique de l’analyse #${w.runId}.` : "Historique personnel, dernier résultat de chaque message."; }));
  $("compare-models").addEventListener("click", () => action($("compare-models"), "workspace-note", async () => { const id = w.runId || state.dashboard?.run?.id; if (!id) throw new Error("Choisissez une analyse terminée."); const result = await request(`/runs/${id}/compare`, { method: "POST" }); w.runId = result.run_id; await loadDashboard(); await renderComparison(result.run_id); $("workspace-note").textContent = "Comparaison lancée sur le même lot. Résultats mis à jour pendant l’analyse."; }));
  $("natural-form").addEventListener("submit", e => { e.preventDefault(); action(e.submitter, "workspace-note", async () => {
    const scope = accountId("natural");
    const result = await request("/natural-search", json("POST", { account_id: scope, query: $("natural-query").value }));
    if (scope !== accountId("natural")) throw new Error("La boîte sélectionnée a changé. Relancez votre demande.");
    applyFilters(result.filters); await search();
    $("natural-result").textContent = result.interpretation + " · Vérifiez ou ajustez le résultat dans Filtres.";
    $("natural-panel").hidden = true; $("natural-toggle").setAttribute("aria-expanded", "false"); $("natural-toggle").focus();
    $("workspace-note").textContent = "";
  }); });
  $("generate-brief").addEventListener("click", () => action($("generate-brief"), "workspace-note", async () => { const scope = accountId("brief"); const brief = await request("/brief", json("POST", { account_id: scope, refresh: true })); if (scope !== accountId("brief")) throw new Error("La boîte sélectionnée a changé. Le brief reste conservé sur la boîte d’origine."); renderBrief(brief); await loadBriefHistory(); notify(`brief-${scope}-${brief.day}`, scope, "Mailaya : votre brief est prêt"); $("workspace-note").textContent = "Brief préparé. Vérifiez les messages sources avant d’agir."; }));
  $("brief-history").addEventListener("change", () => { const brief = w.briefs.find(b => b.id === Number($("brief-history").value)); if (brief) renderBrief(brief.payload); });
  for (const format of ["csv", "json"]) $("export-" + format).addEventListener("click", () => action($("export-" + format), "workspace-note", async () => {
    const generation = state.generation;
    const response = await fetch(apiBase + base + "/export", { ...json("POST", { filters: filters(), format }), headers: { "Content-Type": "application/json", "X-Mailaya-Request": "1" } });
    if (!response.ok) throw new Error("L’export a échoué. Vérifiez votre session et les filtres.");
    const blob = await response.blob(); if (generation !== state.generation) return;
    const url = URL.createObjectURL(blob), link = document.createElement("a"); link.href = url; link.download = `mailaya.${format}`; link.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
    $("workspace-note").textContent = "Export de tous les messages correspondant aux filtres, au-delà de la page affichée.";
  }));
  $("source").addEventListener("change", syncIncremental);
  session(state.user);
})();
