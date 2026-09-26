(() => {
  const nodes = [1, 2, 3].map(id => ({ id, base: "http://127.0.0.1:800" + id }));
  const overrides = {};
  let files = [];
  let previousOnline = {};
  let firstHealthCheck = true;

  const $ = (selector, root = document) => root.querySelector(selector);
  const formatBytes = value => {
    if (!value) return "0 B";
    const units = ["B", "KB", "MB", "GB", "TB"];
    const index = Math.min(Math.floor(Math.log(value) / Math.log(1024)), units.length - 1);
    return (value / Math.pow(1024, index)).toFixed(index ? 1 : 0) + " " + units[index];
  };
  const safeDate = value => value ? new Date(value).toLocaleString() : "—";

  function logActivity(message) {
    const panel = $("#activity");
    if (!panel) return;
    let list = $("#nidusActivityLog", panel);
    if (!list) {
      list = document.createElement("div");
      list.id = "nidusActivityLog";
      list.className = "mt-4 space-y-2";
      panel.append(list);
    }
    const entry = document.createElement("p");
    entry.className = "text-[11px] text-muted";
    entry.textContent = new Date().toLocaleTimeString() + " — " + message;
    list.prepend(entry);
    while (list.children.length > 6) list.removeChild(list.lastChild);
  }

  async function readJson(response) {
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.detail ? JSON.stringify(data.detail) : response.status + " " + response.statusText);
    return data;
  }

  async function fetchFromAnyNode(path, options) {
    let lastError;
    for (const node of nodes) {
      try {
        return await fetch(node.base + path, options); // node responded (even with an error status) — trust it, don't mask app-level errors by falling back
      } catch (error) {
        lastError = error; // network failure — this node is unreachable, try the next one
      }
    }
    throw lastError || new Error("No nodes reachable");
  }

  function setKpis(onlineCount) {
    const cards = [...document.querySelectorAll(".stats-grid article")];
    if (cards.length < 4) return;
    const values = cards.map(card => $("p.mt-4", card));
    if (values[0]) values[0].textContent = "Not reported";
    const note = $("p.mt-2", cards[0]);
    if (note) note.textContent = "Disk capacity is not provided by the API";
    if (values[1]) values[1].innerHTML = onlineCount + ' <span class="text-base font-semibold text-muted">/ 3</span>';
    if (values[2]) values[2].textContent = String(files.length);
    const total = Math.max(1, files.length * 3);
    const ok = files.reduce((sum, file) => {
      const map = overrides[file.id] || file.replicas || {};
      return sum + Object.values(map).filter(value => value === "ok").length;
    }, 0);
    const percent = files.length ? ((ok / total) * 100).toFixed(1) : "—";
    if (values[3]) values[3].innerHTML = percent + '<span class="text-base">%</span>';
    const captions = cards.map(card => $("p.mt-4:not(.text-3xl)", card));
    if (captions[1]) {
      const nodesHealthy = onlineCount === nodes.length;
      captions[1].className = "mt-4 flex items-center gap-2 text-[11px] font-semibold " + (nodesHealthy ? "text-healthy" : "text-danger");
      const downCount = nodes.length - onlineCount;
      captions[1].innerHTML = '<span class="status-dot ' + (nodesHealthy ? "bg-healthy" : "bg-danger") + '"></span>' + (nodesHealthy ? "All nodes responding" : downCount + " node" + (downCount > 1 ? "s" : "") + " unreachable");
    }
    if (captions[2]) captions[2].textContent = "From node 1 metadata";
    if (captions[3]) captions[3].textContent = files.length ? ok + " of " + (files.length * 3) + " replica slots healthy" : "No uploaded files yet";    const pending = files.reduce((sum, file) => {
      const map = overrides[file.id] || file.replicas || {};
      return sum + Object.values(map).filter(value => value !== "ok").length;
    }, 0);
    const replicationRows = [...document.querySelectorAll("#replication .mt-5.space-y-4 > div")];
    if (replicationRows[1]?.lastElementChild) replicationRows[1].lastElementChild.textContent = String(pending);
    if (replicationRows[3]?.lastElementChild) replicationRows[3].lastElementChild.textContent = pending ? pending + " pending" : "Clear";
    const nodeNote = $("#nodes > p");
    if (nodeNote) nodeNote.textContent = "3 simulated nodes · disk capacity not reported by the API";
    const statusPill = $("header .inline-flex");
    if (statusPill) {
      const allOnline = onlineCount === nodes.length;
      statusPill.innerHTML = '<span class="status-dot ' + (allOnline ? "bg-healthy" : "bg-danger") + '"></span>' + (allOnline ? "All 3 nodes online" : onlineCount + "/3 nodes online");
    }
    const capacityBar = $(".stats-grid article:first-child .bar");
    if (capacityBar) capacityBar.style.display = "none";
  }

  function renderNodes(statuses) {
    const container = $("#nodes .space-y-4");
    if (!container) return;
    container.replaceChildren();
    nodes.forEach(node => {
      const online = !!statuses[node.id];
      const row = document.createElement("div");
      row.className = "flex items-center gap-3";
      const icon = document.createElement("span");
      icon.className = "grid h-10 w-10 place-items-center rounded-xl";
      icon.style.background = online ? "#387B5A18" : "#B7473718";
      icon.style.color = online ? "#387B5A" : "#B74737";
      icon.textContent = "N" + node.id;
      const body = document.createElement("div");
      body.className = "min-w-0 flex-1";
      const top = document.createElement("div");
      top.className = "flex flex-wrap items-center justify-between gap-2";
      const label = document.createElement("p");
      label.className = "text-xs font-bold";
      label.textContent = "Node 0" + node.id + " · port " + (8000 + node.id);
      const status = document.createElement("span");
      status.className = "pill";
      status.style.background = online ? "#387B5A18" : "#B7473718";
      status.style.color = online ? "#387B5A" : "#B74737";
      status.textContent = online ? "Online" : "Offline";
      top.append(label, status);
      const detail = document.createElement("p");
      detail.className = "mt-1.5 text-[10px] text-muted";
      detail.textContent = online ? "Health endpoint responding" : "Health endpoint unavailable";
      body.append(top, detail);
      row.append(icon, body);
      container.append(row);
    });
  }

  function makeButton(label, action, danger = false) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = danger
      ? "rounded-lg border border-[#B74737] text-[#B74737] px-3 py-2 text-[10px] font-bold hover:bg-[#B74737] hover:text-white"
      : "rounded-lg border border-bordercream bg-softcream px-3 py-2 text-[10px] font-bold hover:border-studio";
    button.textContent = label;
    button.addEventListener("click", action);
    return button;
  }

  function renderFiles() {
    const table = $("#fileTable");
    if (!table) return;
    table.replaceChildren();
    const query = ($("#fileSearch")?.value || "").trim().toLowerCase();
    const visible = files.filter(file => (file.original_filename || "").toLowerCase().includes(query) || file.id.toLowerCase().includes(query));
    visible.forEach(file => {
      const map = overrides[file.id] || file.replicas || {};
      const healthy = Object.values(map).filter(value => value === "ok").length;
      const row = document.createElement("tr");
      row.className = "file-row border-b border-bordercream/70";
      const nameCell = document.createElement("td");
      nameCell.className = "py-4 pl-2";
      const name = document.createElement("div");
      name.className = "font-bold";
      name.textContent = file.original_filename || file.id;
      const id = document.createElement("div");
      id.className = "mt-1 text-[10px] text-muted";
      id.textContent = file.id;
      nameCell.append(name, id);
      const sizeCell = document.createElement("td");
      sizeCell.className = "py-4 text-muted";
      sizeCell.textContent = formatBytes(file.size_bytes);
      const dateCell = document.createElement("td");
      dateCell.className = "py-4 text-muted";
      dateCell.textContent = safeDate(file.created_at);
      const statusCell = document.createElement("td");
      statusCell.className = "py-4";
      const badge = document.createElement("span");
      badge.className = "pill";
      badge.style.background = healthy === 3 ? "#387B5A18" : "#B8792418";
      badge.style.color = healthy === 3 ? "#387B5A" : "#B87924";
      badge.textContent = healthy + "/3 replicas" + (healthy < 3 ? " · degraded" : "");
      const replicaLine = document.createElement("div");
      replicaLine.className = "mt-1 text-[10px] text-muted";
      replicaLine.textContent = nodes.map(node => "N" + node.id + ": " + (map[node.id] || "unknown")).join(" · ");
      statusCell.append(badge, replicaLine);
      const actionCell = document.createElement("td");
      actionCell.className = "py-4 pr-2 text-right";
      const actionWrap = document.createElement("div");
      actionWrap.className = "flex flex-wrap justify-end gap-2";
      actionWrap.append(
        makeButton("Download", () => downloadFile(file)),
        makeButton("Verify / repair", () => verifyAndRepair(file)),
        makeButton("Delete", () => deleteFile(file), true)
      );
      actionCell.append(actionWrap);
      row.append(nameCell, sizeCell, dateCell, statusCell, actionCell);
      table.append(row);
    });
    const empty = $("#noFiles");
    if (empty) {
      empty.textContent = files.length ? "No matching files found." : "No files uploaded yet.";
      empty.classList.toggle("hidden", visible.length > 0);
    }
    const hint = $("#files > p.mt-4");
    if (hint) hint.textContent = "Live file metadata and replica status from node 1.";
    setKpis(window.__nidusOnlineCount || 0);
    if (window.lucide) window.lucide.createIcons();
  }

  async function refreshFiles() {
    const perNode = await Promise.all(nodes.map(async node => {
      try {
        const data = await readJson(await fetch(node.base + "/files"));
        return data.files || [];
      } catch (_) {
        return [];
      }
    }));
    const merged = new Map();
    for (const list of perNode) {
      for (const file of list) {
        if (!merged.has(file.id)) merged.set(file.id, file);
      }
    }
    files = [...merged.values()];
    renderFiles();
  }

  async function refreshNodes() {
    const results = await Promise.all(nodes.map(async node => {
      try {
        const response = await fetch(node.base + "/health", { cache: "no-store" });
        return [node.id, response.ok];
      } catch (_) {
        return [node.id, false];
      }
    }));
    const statuses = Object.fromEntries(results);
    window.__nidusOnlineCount = Object.values(statuses).filter(Boolean).length;
    renderNodes(statuses);
    setKpis(window.__nidusOnlineCount);

    if (!firstHealthCheck) {
      for (const node of nodes) {
        const wasOnline = previousOnline[node.id];
        const isOnline = statuses[node.id];
        if (wasOnline === true && isOnline === false) {
          logActivity("Node " + node.id + " went offline");
        } else if (wasOnline === false && isOnline === true) {
          logActivity("Node " + node.id + " back online — checking replicas…");
          autoRepairNode(node.id);
        }
      }
    }
    firstHealthCheck = false;
    previousOnline = statuses;
  }

  async function autoRepairNode(nodeId) {
    for (const file of files) {
      await verifyAndRepair(file, true);
    }
    logActivity("Node " + nodeId + " — auto-repair sweep complete");
  }

  async function uploadSelected(fileInput) {
    const selected = [...fileInput.files];
    if (!selected.length) return;
    for (const file of selected) {
      const form = new FormData();
      form.append("file", file);
      try {
        const result = await readJson(await fetchFromAnyNode("/files", { method: "POST", body: form }));
        const copies = Object.values(result.replicas || {}).filter(value => value === "ok").length;
        alert(file.name + " uploaded: " + copies + "/3 replicas." + (result.replication_complete ? " Fully replicated." : " Degraded; repair pending."));
      } catch (error) {
        alert("Upload failed for " + file.name + ": " + error.message);
      }
    }
    fileInput.value = "";
    await refreshFiles();
    await refreshNodes();
  }

  async function downloadFile(file) {
    for (const node of nodes) {
      try {
        const response = await fetch(node.base + "/files/" + encodeURIComponent(file.id));
        if (!response.ok) continue;
        const blob = await response.blob();
        const link = document.createElement("a");
        link.href = URL.createObjectURL(blob);
        link.download = file.original_filename || file.id;
        link.click();
        URL.revokeObjectURL(link.href);
        return;
      } catch (_) {}
    }
    alert("No live node could provide a readable copy.");
  }

  async function deleteFile(file) {
    const label = file.original_filename || file.id;
    if (!confirm('Delete "' + label + '" from every node? This cannot be undone.')) return;
    const results = await Promise.allSettled(nodes.map(node => fetch(node.base + "/files/" + encodeURIComponent(file.id), { method: "DELETE" })));
    const succeeded = results.filter(result => result.status === "fulfilled" && result.value.ok).length;
    if (succeeded === 0) {
      alert('Could not delete "' + label + '" — no node accepted the delete request. Your backend may not have a DELETE /files/:id endpoint yet.');
      return;
    }
    delete overrides[file.id];
    logActivity(label + " deleted (" + succeeded + "/" + nodes.length + " nodes confirmed)");
    await refreshFiles();
  }

  async function verifyAndRepair(file, silent = false) {
    const status = {};
    const messages = [];
    for (const node of nodes) {
      try {
        const check = await readJson(await fetch(node.base + "/files/" + encodeURIComponent(file.id) + "/check", { method: "POST" }));
        status[node.id] = check.local_status;
        if (!check.ok) {
          const repair = await readJson(await fetch(node.base + "/files/" + encodeURIComponent(file.id) + "/repair", { method: "POST" }));
          status[node.id] = repair.local_status || "ok";
          messages.push("Node " + node.id + ": " + (repair.repaired ? "repaired from node " + repair.source_node : repair.message));
        }
      } catch (_) {
        status[node.id] = "offline";
        messages.push("Node " + node.id + ": unavailable");
      }
    }
    overrides[file.id] = Object.assign({}, file.replicas || {}, status);
    renderFiles();
    if (silent) {
      if (messages.length) logActivity((file.original_filename || file.id) + " — " + messages.join("; "));
    } else {
      alert(messages.length ? messages.join("\n") : "All three copies passed their checksum checks.");
    }
  }

  function connectUi() {
    const objectBrowser = $("#object-browser");
    const dashboard = $("#dashboardPage");
    if (objectBrowser) objectBrowser.classList.add("hidden");
    if (dashboard) dashboard.classList.remove("hidden");
    document.querySelectorAll('[data-page="object-browser"]').forEach(link => link.remove());
    const footer = $("footer");
    if (footer) footer.lastElementChild.textContent = "Live demo · local 3-node cluster";
    const sampleActivity = $("#activity");
    if (sampleActivity) sampleActivity.innerHTML = '<h2 class="text-base font-extrabold">Cluster activity</h2><p class="mt-2 text-xs text-muted">Use the file actions to verify checksums and repair replicas.</p>';
    const repairButton = $("#repairNow");
    if (repairButton) repairButton.textContent = "Verify & Repair Files";
    const fileInput = $("#fileInput");
    fileInput?.addEventListener("change", event => {
      event.stopImmediatePropagation();
      uploadSelected(fileInput);
    }, true);
    repairButton?.addEventListener("click", event => {
      event.preventDefault();
      event.stopImmediatePropagation();
      (async () => {
        for (const file of files) await verifyAndRepair(file);
      })();
    }, true);
    $("#fileSearch")?.addEventListener("input", renderFiles);
    const replicationRows = [...document.querySelectorAll("#replication .mt-5.space-y-4 > div")];
    if (replicationRows[0]?.lastElementChild) replicationRows[0].lastElementChild.textContent = "3 target · 2 minimum";
    if (replicationRows[2]?.lastElementChild) replicationRows[2].lastElementChild.textContent = "Run Verify / repair";
    const intro = $("#replication .rounded-2xl .text-muted");
    if (intro) intro.textContent = "Uploads target all three nodes; two healthy copies are required.";
  }

  connectUi();
  refreshNodes();
  refreshFiles().catch(error => alert("Could not load backend file list: " + error.message));
  window.setInterval(refreshNodes, 5000);
})();