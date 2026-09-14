"use strict";
const $ = (id) => document.getElementById(id);
const ENGINE_ORIGIN = "http://127.0.0.1:28661";
const engineUrl = (path) => new URL(path, ENGINE_ORIGIN).href;
let selectedFile = null,
  currentId = null,
  result = null,
  dirty = false,
  busy = false,
  ready = false,
  modelUpdateAvailable = false,
  softwareUpdateAvailable = false;
let view = "new",
  records = [],
  polling = false,
  modelData = null,
  playUntil = null,
  toastTimer;
const statusNames = {
  running: "statusRunning",
  complete: "statusComplete",
  cancelled: "statusCancelled",
  error: "statusError",
  interrupted: "statusInterrupted",
};
function statusLabel(status) {
  return tr(statusNames[status] || status || "preparing");
}
const audio = $("audio");

// 软件更新由 Tauri 负责下载和验签；此卡片与模型更新分开显示。
const appUpdateCard = document.createElement("div");
appUpdateCard.className = "card app-update-card";
appUpdateCard.innerHTML = `
  <div class="row">
    <div>
      <h2 id="app-update-title"></h2>
      <p id="app-update-description" class="muted"></p>
    </div>
    <span id="app-version" class="pill">1.1.1</span>
  </div>
  <div class="model-actions">
    <button id="check-app-update" class="primary"></button>
    <button id="install-app-update" class="secondary attention-button" hidden></button>
  </div>
  <label class="check-label"><input id="app-check-on-start" type="checkbox"><span id="app-check-on-start-label"></span></label>
  <div id="app-update-status" class="update-status" role="status"></div>
  <div id="app-update-notes" class="app-update-notes" hidden></div>
`;
$("view-models").querySelector(".card").before(appUpdateCard);

const appUpdateDialog = document.createElement("dialog");
appUpdateDialog.id = "app-update-progress-dialog";
appUpdateDialog.innerHTML = `
  <div class="update-dialog-heading">
    <span class="update-dialog-icon" aria-hidden="true">↓</span>
    <div>
      <h2 id="app-progress-title"></h2>
      <p id="app-progress-phase" class="muted"></p>
    </div>
  </div>
  <div class="row update-progress-numbers">
    <strong id="app-progress-percent">0%</strong>
    <span id="app-progress-speed" class="muted">—</span>
  </div>
  <progress id="app-progress-bar" max="100" value="0"></progress>
  <div class="row update-progress-detail">
    <span id="app-progress-downloaded" class="muted">—</span>
    <span id="app-progress-total" class="muted">—</span>
  </div>
  <p id="app-progress-error" class="error" hidden></p>
  <div class="actions"><button id="app-progress-close" class="secondary" hidden></button></div>
`;
document.body.append(appUpdateDialog);
let appUpdateProgressTimer = null;

function tauriInvoke(command) {
  const invoke = window.__TAURI_INTERNALS__?.invoke;
  if (!invoke) throw Error(tr("appUpdateDesktopOnly"));
  return invoke(command);
}
// 模型下载入口统一放在“模型与更新”页；首页只保留快捷跳转。
document.querySelector(".model-actions").prepend($("download-models"));
const goModels = document.createElement("button");
goModels.id = "go-models";
goModels.className = "secondary attention-button";
goModels.hidden = true;
goModels.onclick = () => $("nav-models").click();
$("readiness").parentElement.append(goModels);
$("download-models").classList.add("attention-button");

function updateModelsNav() {
  const needsAttention = !ready || modelUpdateAvailable || softwareUpdateAvailable;
  $("nav-models").classList.toggle("has-notification", needsAttention);
  $("nav-models").querySelector(".nav-models-label").textContent = tr("models");
}
// Shared translations and display-language state are loaded from /i18n.js.
// 这里集中保存页面状态；result 是当前录音的可编辑转写结果。
function replaceLabelText(label, text) {
  const node = [...label.childNodes].find((child) => child.nodeType === Node.TEXT_NODE && child.textContent.trim());
  if (node) node.textContent = text;
}
function installDisplayLanguagePicker() {
  const footer = document.querySelector(".sidebar-footer");
  if (!footer || $("display-language")) return;
  if (!$("display-language-style")) {
    const style = document.createElement("style");
    style.id = "display-language-style";
    style.textContent = ".display-language-control{display:flex;align-items:center;gap:8px;margin-bottom:12px}.display-language-control select{min-width:108px}";
    document.head.append(style);
  }
  const wrap = document.createElement("label");
  wrap.className = "display-language-control";
  wrap.innerHTML = '<span id="display-language-label"></span><select id="display-language"><option value="zh">中文</option><option value="ja">日本語</option><option value="en">English</option></select>';
  footer.insertBefore(wrap, footer.firstChild);
  $("display-language").value = displayLanguage;
  $("display-language").onchange = (event) => {
    displayLanguage = event.target.value;
    localStorage.setItem("hearnotes.displayLanguage", displayLanguage);
    applyDisplayLanguage();
  };
}
function applyDisplayLanguage() {
  // 切换界面语言时重新写入静态文案、下拉选项和当前视图内容。
  installDisplayLanguagePicker();
  document.documentElement.lang = displayLanguage === "zh" ? "zh-CN" : displayLanguage;
  document.title = tr("pageTitle");
  $("display-language-label").textContent = tr("displayLanguage");
  const brandText = $("brand").querySelector("span:nth-child(2)");
  if (brandText) replaceLabelText(brandText, tr("appName"));
  const footerText = document.querySelector(".sidebar-footer > span");
  if (footerText) footerText.textContent = tr("footer");
  $("confirm-no").textContent = tr("confirmNo");
  $("confirm-yes").textContent = tr("confirmYes");
  $("readiness").textContent = ready ? tr("readyLocal") : tr("missingComponents");
  $("download-models").textContent = tr("downloadModels");
  $("go-models").textContent = tr("goModels");
  $("nav-new").textContent = tr("newTranscript");
  updateModelsNav();
  replaceLabelText(document.querySelector(".local-label"), tr("localOnly"));
  const historyTitle = document.querySelector(".history-title");
  if (historyTitle) historyTitle.innerHTML = `${tr("recent")} <span id="history-count">${records.length}</span>`;
  $("quit").textContent = tr("quit");
  $("view-new").querySelector(".eyebrow").textContent = tr("eyebrowNew");
  $("view-new").querySelector("h1").textContent = tr("newTitle");
  $("view-new").querySelector(".lead").textContent = tr("newLead");
  const labels = $("view-new").querySelectorAll(".upload-card > .section-label");
  if (labels[0]) labels[0].textContent = tr("importLabel");
  if (labels[1]) labels[1].textContent = tr("settingsLabel");
  $("file-title").textContent = selectedFile ? selectedFile.name : tr("dropTitle");
  if (!selectedFile) $("file-description").textContent = tr("dropChoose");
  $("dropzone").querySelector("small").innerHTML = `${tr("formats")}<br>${tr("limits")}`;
  replaceLabelText($("language").closest("label"), tr("recordingLanguage"));
  replaceLabelText($("speakers").closest("label"), tr("speakerCount"));
  const languageLabels = {
    "": tr("autoLanguage"),
    ja: tr("langJa"),
    zh: tr("langZh"),
    en: tr("langEn"),
    ko: tr("langKo"),
  };
  for (const option of $("language").options) {
    option.textContent = languageLabels[option.value] || option.textContent;
  }
  $("speakers").options[0].textContent = tr("autoSpeakers");
  $("speakers").options[1].textContent = trf("speakerOne", { n: 1 });
  $("speakers").options[2].textContent = tr("commonMeeting");
  for (let i = 3; i < $("speakers").options.length; i++) {
    const count = $("speakers").options[i].value;
    $("speakers").options[i].textContent = trf("speakerMany", { n: count });
  }
  $("view-new").querySelector(".form-grid + .field-help").textContent = tr("speakerHint");
  $("view-new").querySelector("summary").textContent = tr("moreSettings");
  const moreLabels = $("view-new").querySelectorAll("details label");
  if (moreLabels[0]) replaceLabelText(moreLabels[0], tr("processing"));
  if (moreLabels[1]) replaceLabelText(moreLabels[1], tr("quality"));
  if (moreLabels[2]) replaceLabelText(moreLabels[2], tr("glossary"));
  $("device").options[0].textContent = tr("gpuCpu");
  $("device").options[1].textContent = tr("allGpu");
  $("device").options[2].textContent = tr("cpuOnly");
  $("quality").options[0].textContent = tr("qualityBalanced");
  $("quality").options[1].textContent = tr("qualityAccurate");
  $("quality").options[2].textContent = tr("qualityFast");
  $("glossary").placeholder = tr("glossary");
  $("view-new").querySelector("details .field-help").textContent = tr("glossaryHint");
  $("start").textContent = selectedFile ? tr("start") : tr("startChoose");
  const feature = $("view-new").querySelector(".feature-card");
  feature.querySelector(".pill").textContent = tr("featurePill");
  feature.querySelector("h2").textContent = tr("featureTitle");
  const sample = feature.querySelectorAll(".sample-line");
  if (sample[0]) { sample[0].querySelector("b").textContent = tr("sampleA"); sample[0].querySelector("p").textContent = tr("samplePrompt"); }
  if (sample[1]) { sample[1].querySelector("b").textContent = tr("sampleB"); sample[1].querySelector("p").textContent = tr("sampleAnswer"); }
  feature.querySelector(".caption").textContent = tr("mock");
  const benefitTexts = feature.querySelectorAll(".benefits li");
  [["oneName", "oneNameDetail"], ["replay", "replayDetail"], ["offline", "offlineDetail"]].forEach(([title, detail], i) => { if (benefitTexts[i]) { benefitTexts[i].querySelector("b").textContent = tr(title); benefitTexts[i].querySelector("span").textContent = tr(detail); } });
  document.querySelector(".privacy-note").textContent = tr("privacy");
  applyJobLanguage();
  applyModelsLanguage();
  renderHistory();
  if (result) renderEditor();
  if (view === "models" && modelData) renderModels();
}
function applyJobLanguage() {
  const viewJob = $("view-job");
  viewJob.querySelector(".eyebrow").textContent = tr("recordingDesk");
  $("save-indicator").textContent = dirty ? tr("unsaved") : tr("allSaved");
  $("stage").textContent = tr("preparing");
  $("progress-note").textContent = tr("keepAwake");
  $("cancel").textContent = tr("cancel"); $("retry").textContent = tr("retry"); $("retry-cpu").textContent = tr("retryCpu");
  viewJob.querySelector(".names-card h2").textContent = tr("namesTitle");
  viewJob.querySelector(".names-card p").textContent = tr("namesHint");
  $("add-speaker").textContent = tr("addSpeaker");
  viewJob.querySelector(".player > span").textContent = tr("audioReplay");
  replaceLabelText($("speed").closest("label"), tr("speed"));
  $("search").placeholder = tr("search");
  $("only-review").parentElement.lastChild.textContent = tr("onlyReview");
  $("save").textContent = tr("save"); $("export").textContent = tr("export");
  $("export-format").options[0].textContent = tr("txt"); $("export-format").options[1].textContent = tr("md"); $("export-format").options[2].textContent = tr("srt"); $("export-format").options[3].textContent = tr("json");
  viewJob.querySelector(".transcript-caption span:last-child").textContent = tr("timeSpeakerHint");
}
function applyModelsLanguage() {
  const viewModels = $("view-models");
  viewModels.querySelector(".eyebrow").textContent = tr("modelsEyebrow");
  viewModels.querySelector("h1").textContent = tr("modelsTitle");
  viewModels.querySelector(".lead").textContent = tr("modelsLead");
  $("model-list").closest(".card").querySelector("h2").textContent = tr("modelsUsing");
  $("model-list").closest(".card").querySelector(".pill").textContent = tr("noApi");
  $("app-update-title").textContent = tr("appUpdateTitle");
  $("app-update-description").textContent = tr("appUpdateDescription");
  $("check-app-update").textContent = tr("checkAppUpdate");
  $("install-app-update").textContent = tr("installAppUpdate");
  $("app-check-on-start-label").textContent = tr("appCheckOnStart");
  $("app-progress-title").textContent = tr("appProgressTitle");
  $("app-progress-close").textContent = tr("close");
  $("check-update").textContent = tr("checkUpdate"); $("install-update").textContent = tr("installUpdate"); $("rollback").textContent = tr("rollback");
  $("check-on-start").parentElement.lastChild.textContent = tr("checkOnStart");
  viewModels.querySelector(".notes-card h2").textContent = tr("updateIntro");
  const notes = viewModels.querySelectorAll(".notes-card .benefits li");
  [["completeDownload", "completeDownloadDetail"], ["oldResults", "oldResultsDetail"], ["rollbackTitle", "rollbackDetail"]].forEach(([title, detail], i) => { if (notes[i]) { notes[i].querySelector("b").textContent = tr(title); notes[i].querySelector("span").textContent = tr(detail); } });
  viewModels.querySelector(".notes-card .field-help").textContent = tr("modelFooter");
}
applyDisplayLanguage();
// New recordings start in the safest general-purpose mode. Users can still
// choose a concrete language or speaker count before pressing Start.
$("language").value = "";
$("speakers").value = "0";
function el(tag, cls, text) {
  const n = document.createElement(tag);
  if (cls) n.className = cls;
  if (text !== undefined) n.textContent = text;
  return n;
}
function clock(t) {
  t = Math.floor(t || 0);
  return [Math.floor(t / 3600), Math.floor(t / 60) % 60, t % 60]
    .map((n) => String(n).padStart(2, "0"))
    .join(":");
}
function toast(text) {
  $("toast").textContent = text;
  $("toast").hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => ($("toast").hidden = true), 5500);
}
async function api(path, body) {
  // 所有请求都走同一个本地 API；POST 自动带上本地来源标记。
  const response = await fetch(
    engineUrl(path),
    body === undefined
      ? {}
      : {
          method: "POST",
          headers: { "Content-Type": "application/json", "X-Local-App": "1" },
          body: JSON.stringify(body),
        },
  );
  let data;
  try {
    data = await response.json();
  } catch {
    throw Error(tr("networkDisconnected"));
  }
  if (!response.ok) throw Error(data.error || tr("operationIncomplete"));
  return data;
}
function confirmAction(title, text) {
  return new Promise((resolve) => {
    $("confirm-title").textContent = title;
    $("confirm-text").textContent = text;
    const d = $("confirm-dialog");
    d.showModal();
    let finished = false;
    function done(value) {
      if (finished) return;
      finished = true;
      d.close();
      resolve(value);
    }
    $("confirm-yes").onclick = () => done(true);
    $("confirm-no").onclick = () => done(false);
    d.oncancel = () => done(false);
  });
}
function markDirty() {
  dirty = true;
  $("save-indicator").hidden = false;
  $("save-indicator").textContent = tr("unsavedChanges");
}
async function canLeave() {
  if (!dirty) return true;
  return confirmAction(
    tr("discardTitle"),
    tr("discardText"),
  );
}
function show(next) {
  view = next;
  for (const name of ["new", "job", "models"])
    $("view-" + name).hidden = name !== next;
  for (const name of ["new", "models"])
    $("nav-" + name).classList.toggle("active", next === name);
}
async function newView() {
  if (!(await canLeave())) return;
  dirty = false;
  result = null;
  currentId = null;
  audio.pause();
  show("new");
  renderHistory();
  refreshStart();
}
$("nav-new").onclick = newView;
$("brand").onclick = (e) => {
  e.preventDefault();
  newView();
};
$("nav-models").onclick = async () => {
  if (!(await canLeave())) return;
  dirty = false;
  audio.pause();
  show("models");
  try {
    await renderModels();
  } catch (e) {
    toast(e.message);
  }
};
function choose(file) {
  // 选择或拖入文件后，只记录文件对象，点击开始时才真正上传。
  if (!file) return;
  selectedFile = file;
  $("file-title").textContent = file.name;
  $("file-description").textContent =
    (file.size / 1024 / 1024).toFixed(1) + " MB · " + tr("fileSelected");
  refreshStart();
}
$("file").onchange = (e) => choose(e.target.files[0]);
for (const event of ["dragover", "dragenter"])
  $("dropzone").addEventListener(event, (e) => {
    e.preventDefault();
    $("dropzone").classList.add("dragging");
  });
for (const event of ["dragleave", "drop"])
  $("dropzone").addEventListener(event, (e) => {
    e.preventDefault();
    $("dropzone").classList.remove("dragging");
  });
$("dropzone").addEventListener("drop", (e) => choose(e.dataTransfer.files[0]));
function refreshStart() {
  $("start").disabled = !selectedFile || busy || !ready;
  $("start").textContent = busy
    ? tr("busyStart")
    : selectedFile
      ? tr("start")
      : tr("startChoose");
}
$("start").onclick = () => {
  if (!selectedFile || busy) return;
  if (selectedFile.size > 1024 ** 3) {
    toast(tr("fileTooLarge"));
    return;
  }
  busy = true;
  refreshStart();
  const params = new URLSearchParams({
    name: selectedFile.name,
    language: $("language").value,
    speakers: $("speakers").value,
    device: $("device").value,
    quality: $("quality").value,
    glossary: $("glossary").value,
  });
  const xhr = new XMLHttpRequest();
  xhr.open("POST", engineUrl("/api/upload?" + params));
  xhr.setRequestHeader("X-Local-App", "1");
  xhr.setRequestHeader("Content-Type", "application/octet-stream");
  xhr.upload.onprogress = (e) => {
    if (e.lengthComputable)
      $("start").textContent =
        tr("uploading") + " " + Math.round((e.loaded / e.total) * 100) + "%";
  };
  xhr.onload = async () => {
    try {
      const data = JSON.parse(xhr.responseText);
      if (xhr.status !== 200) throw Error(data.error || tr("uploadError"));
      currentId = data.id;
      result = null;
      dirty = false;
      show("job");
      $("editor").hidden = true;
      $("progress-card").hidden = false;
      $("job-title").textContent = selectedFile.name;
      $("stage").textContent = tr("preparingNow");
      $("progress").value = 0;
      $("percent").textContent = "0%";
      await poll();
    } catch (e) {
      busy = false;
      refreshStart();
      toast(e.message);
    }
  };
  xhr.onerror = () => {
    busy = false;
    refreshStart();
    toast(tr("uploadFailed"));
  };
  xhr.send(selectedFile);
};
function renderHistory() {
  // 历史记录来自 data/jobs 下的摘要文件，不会读取整份音频。
  $("history-count").textContent = records.length;
  const frag = document.createDocumentFragment();
  for (const job of records) {
    const row = el("div", "history-item-row");
    const button = el("button", "history-item");
    button.classList.toggle("selected", currentId === job.id && view === "job");
    button.append(
      el("strong", "", job.filename),
      el(
        "small",
        "",
        new Date(job.created * 1000).toLocaleDateString("zh-CN") +
          " · " +
          statusLabel(job.status) || job.stage,
      ),
    );
    button.title = job.filename;
    button.onclick = () => openJob(job.id);
    const remove = el("button", "history-delete", "×");
    remove.type = "button";
    remove.title = tr("deleteRecording");
    remove.setAttribute("aria-label", `${tr("deleteRecording")} ${job.filename}`);
    remove.onclick = async (event) => {
      event.stopPropagation();
      if (job.status === "running") {
        toast(tr("deleteRunning"));
        return;
      }
      if (!(await confirmAction(tr("deleteTitle"), tr("deleteText")))) return;
      try {
        await api("/api/jobs/" + job.id + "/delete", {});
        if (currentId === job.id) {
          currentId = null;
          result = null;
          dirty = false;
          audio.pause();
          show("new");
        }
        await poll();
        toast(tr("deleteSuccess"));
      } catch (error) {
        toast(error.message);
      }
    };
    row.append(button, remove);
    frag.append(row);
  }
  if (!records.length)
    frag.append(el("p", "muted empty-history", tr("emptyHistory")));
  $("history").replaceChildren(frag);
}
async function openJob(id) {
  if (currentId === id && view === "job") return;
  if (!(await canLeave())) return;
  dirty = false;
  result = null;
  currentId = id;
  audio.pause();
  show("job");
  $("editor").hidden = true;
  $("save-indicator").hidden = true;
  renderHistory();
  try {
    await updateJob(await api("/api/jobs/" + id));
  } catch (e) {
    toast(e.message);
  }
}
async function updateJob(job) {
  $("job-title").textContent = job.filename;
  $("job-subtitle").textContent =
    (job.duration ? clock(job.duration) + " · " : "") +
    (job.language || tr("languageUnknown")) +
    " · " +
    statusLabel(job.status);
  $("progress-card").hidden = job.status === "complete" && job.has_result;
  $("stage").textContent = job.stage;
  $("progress").value = job.progress || 0;
  $("percent").textContent = (job.progress || 0) + "%";
  $("elapsed").textContent = job.elapsed ? tr("elapsed") + " " + clock(job.elapsed) : "";
  $("cancel").hidden = job.status !== "running";
  $("retry").hidden = !["error", "cancelled", "interrupted"].includes(
    job.status,
  );
  $("retry-cpu").hidden = $("retry").hidden;
  $("job-error").hidden = !job.error;
  $("job-error").textContent = job.error || "";
  $("progress-note").textContent =
    job.note ||
    (job.processed
      ? tr("processedTo") + " " + clock(job.processed) + ". " + tr("keepAwakeShort")
      : tr("keepAwake"));
  if (job.status === "complete" && job.has_result && !result) {
    const id = currentId;
    const loaded = await api("/api/jobs/" + id + "/result");
    if (id !== currentId) return;
    result = loaded;
    renderEditor();
  }
}
async function poll() {
  if (polling) return;
  polling = true;
  try {
    records = await api("/api/jobs");
    const cfg = await api("/api/config");
    busy = cfg.busy;
    ready = Object.values(cfg.ready).every(Boolean);
    modelUpdateAvailable = Boolean(cfg.model_update_available);
    $("readiness").textContent = ready ? tr("readyLocal") : tr("missingComponents");
    $("download-models").hidden = ready;
    $("download-models").disabled = cfg.busy;
    $("go-models").hidden = ready;
    updateModelsNav();
    refreshStart();
    renderHistory();
    if (view === "job" && currentId) {
      const job = records.find((j) => j.id === currentId);
      if (job) await updateJob(job);
    }
    if (view === "models") await renderModels();
  } catch (e) {
    $("readiness").textContent = e.message;
  } finally {
    polling = false;
  }
}
$("cancel").onclick = async () => {
  if (
    !(await confirmAction(
      tr("cancelTitle"),
      tr("cancelText"),
    ))
  )
    return;
  try {
    await api("/api/jobs/" + currentId + "/cancel", {});
    await poll();
  } catch (e) {
    toast(e.message);
  }
};
async function retry(device) {
  try {
    await api("/api/jobs/" + currentId + "/retry", { device });
    await poll();
  } catch (e) {
    toast(e.message);
  }
}
$("retry").onclick = () => retry("auto");
$("retry-cpu").onclick = () => retry("cpu");
function speakerTitle(id) {
  return `${id} · ${result.speakers[id] || tr("pendingSpeaker")}`;
}
function fillOptions(select, all = false) {
  const old = select.value;
  select.replaceChildren();
  if (all) {
    const option = el("option", "", tr("allSpeakers"));
    option.value = "all";
    select.append(option);
  }
  for (const id of Object.keys(result.speakers)) {
    const option = el("option", "", speakerTitle(id));
    option.value = id;
    select.append(option);
  }
  if ([...select.options].some((o) => o.value === old)) select.value = old;
}
function renderNames() {
  const frag = document.createDocumentFragment();
  for (const [id, name] of Object.entries(result.speakers)) {
    const label = el("label", "name-field");
    const badge = el("span", "avatar color-" + id, id);
    const input = el("input", "name-input");
    input.value = name;
    input.maxLength = 60;
    input.setAttribute("aria-label", tr("speakerNameAria") + " " + id);
    input.oninput = () => {
      result.speakers[id] = input.value;
      markDirty();
      for (const select of document.querySelectorAll(".speaker-select"))
        fillOptions(select);
      fillOptions($("filter-speaker"), true);
    };
    label.append(badge, input);
    frag.append(label);
  }
  $("speaker-names").replaceChildren(frag);
  fillOptions($("filter-speaker"), true);
}
function renderEditor() {
  // 进入编辑器时建立一次全局改名区域和逐段文字/说话人控件。
  $("editor").hidden = false;
  $("save-indicator").hidden = false;
  $("save-indicator").textContent = tr("saveIndicator");
  dirty = false;
  renderNames();
  audio.crossOrigin = "anonymous";
  audio.src = engineUrl("/api/jobs/" + currentId + "/audio");
  audio.playbackRate = Number($("speed").value);
  $("search").value = "";
  $("only-review").checked = false;
  $("warnings").hidden = !result.warnings.length;
  $("warnings").textContent = result.warnings.join(" ");
  renderSegments();
}
function renderSegments() {
  if (!result) return;
  const term = $("search").value.toLowerCase();
  const filter = $("filter-speaker").value;
  const only = $("only-review").checked;
  const filtered = result.segments.filter(
    (s) =>
      (filter === "all" || filter === s.speaker) &&
      (!term || s.text.toLowerCase().includes(term)) &&
      (!only || (s.flags.length && !s.reviewed)),
  );
  $("segment-count").textContent =
    `${tr("showing")} ${filtered.length} / ${result.segments.length}`;
  const frag = document.createDocumentFragment();
  for (const seg of filtered) {
    const row = el("article", "transcript-row");
    row.dataset.id = seg.id;
    const left = el("div", "segment-left");
    const play = el("button", "time-button", "▶ " + clock(seg.start));
    play.title = tr("replaySegment");
    play.onclick = async () => {
      audio.currentTime = Math.max(0, seg.start - 0.15);
      playUntil = seg.end + 0.25;
      try {
        await audio.play();
      } catch {
        toast(tr("chooseTime"));
      }
    };
    const select = el("select", "speaker-select");
    select.setAttribute("aria-label", clock(seg.start) + " · " + tr("speakerNameAria"));
    fillOptions(select);
    select.value = seg.speaker;
    select.onchange = () => {
      seg.speaker = select.value;
      markDirty();
    };
    left.append(play, select);
    const right = el("div");
    const text = el("textarea", "segment-text");
    text.value = seg.text;
    text.rows = Math.max(2, Math.ceil(seg.text.length / 62));
    text.setAttribute("aria-label", clock(seg.start) + " · " + tr("transcriptText"));
    text.oninput = () => {
      seg.text = text.value;
      markDirty();
    };
    const footer = el("div", "segment-flags");
    footer.append(
      el("span", "flag", seg.reviewed ? "" : seg.flags.join(" · ")),
    );
    const checked = el("label", "check-label");
    const box = el("input");
    box.type = "checkbox";
    box.checked = seg.reviewed;
    box.onchange = () => {
      seg.reviewed = box.checked;
      markDirty();
      footer.querySelector(".flag").textContent = seg.reviewed
        ? ""
        : seg.flags.join(" · ");
    };
    checked.append(box, document.createTextNode(tr("reviewedLabel")));
    footer.append(checked);
    right.append(text, footer);
    row.append(left, right);
    frag.append(row);
  }
  if (!filtered.length)
    frag.append(el("p", "muted", tr("noMatches")));
  $("transcript").replaceChildren(frag);
}
for (const id of ["search", "filter-speaker", "only-review"])
  $(id).addEventListener(id === "search" ? "input" : "change", renderSegments);
$("speed").onchange = () => (audio.playbackRate = Number($("speed").value));
audio.addEventListener("timeupdate", () => {
  if (playUntil !== null && audio.currentTime >= playUntil) {
    audio.pause();
    playUntil = null;
  }
  if (!result) return;
  for (const row of document.querySelectorAll(".transcript-row")) {
    const seg = result.segments.find((s) => s.id === Number(row.dataset.id));
    row.classList.toggle(
      "playing",
      !audio.paused &&
        audio.currentTime >= seg.start &&
        audio.currentTime <= seg.end,
    );
  }
});
audio.addEventListener("seeking", () => {
  if (playUntil !== null && audio.currentTime > playUntil) playUntil = null;
});
$("add-speaker").onclick = () => {
  let id;
  for (let n = 0; n < 26; n++) {
    const letter = String.fromCharCode(65 + n);
    if (!(letter in result.speakers)) {
      id = letter;
      break;
    }
  }
  if (!id) {
    toast(tr("maxSpeakers"));
    return;
  }
  result.speakers[id] = tr("defaultSpeakerName") + " " + id;
  renderNames();
  renderSegments();
  markDirty();
};
async function save() {
  if (!result) return false;
  if (Object.values(result.speakers).some((n) => !n.trim())) {
    toast(tr("namesRequired"));
    return false;
  }
  const payload = {
    revision: result.revision,
    speakers: { ...result.speakers },
    segments: result.segments.map(({ id, speaker, text, reviewed }) => ({
      id,
      speaker,
      text,
      reviewed,
    })),
  };
  $("save").disabled = true;
  try {
    const saved = await api("/api/jobs/" + currentId + "/save", payload);
    result.revision = saved.revision;
    dirty = false;
    $("save-indicator").textContent = tr("saveIndicator");
    toast(tr("savedToast"));
    return true;
  } catch (e) {
    toast(e.message);
    return false;
  } finally {
    $("save").disabled = false;
  }
}
$("save").onclick = save;
$("export").onclick = async () => {
  if (dirty && !(await save())) return;
  try {
    const format = $("export-format").value;
    const response = await fetch(
      engineUrl("/api/jobs/" + currentId + "/export?format=" + format),
    );
    if (!response.ok) throw Error(tr("operationIncomplete"));
    const downloadUrl = URL.createObjectURL(await response.blob());
    const a = el("a");
    a.href = downloadUrl;
    a.download = result.filename.replace(/\.[^.]+$/, "") + "_转写." + format;
    document.body.append(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(downloadUrl);
  } catch (error) {
    toast(error.message);
  }
};
window.addEventListener("beforeunload", (e) => {
  if (dirty) {
    e.preventDefault();
    e.returnValue = "";
  }
});
window.addEventListener("keydown", (e) => {
  if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "s" && result) {
    e.preventDefault();
    save();
  }
});
async function renderModels() {
  // 模型页只展示版本和更新状态；实际下载由服务端后台线程完成。
  const d = await api("/api/models");
  modelData = d;
  modelUpdateAvailable = Boolean(
    d.plan && (d.plan.asr_available || d.plan.voices_available),
  );
  updateModelsNav();
  const frag = document.createDocumentFragment();
  for (const [key, title, subtitle] of [
    ["asr", tr("asr"), tr("asrSub")],
    ["voices", tr("voices"), tr("voicesSub")],
  ]) {
    const row = el("div", "model-line");
    const desc = el("div");
    desc.append(el("b", "", title), el("small", "", subtitle));
    const version = d.state.active[key].revision;
    const installed = Boolean(d.model_ready?.[key]);
    row.append(
      desc,
      el(
        "span",
        "version",
        installed
          ? (version === "bundled" ? tr("currentBundled") : version.slice(0, 16))
          : tr("modelNotInstalled"),
      ),
    );
    frag.append(row);
  }
  $("model-list").replaceChildren(frag);
  $("check-on-start").checked = d.state.check_on_start;
  $("check-on-start").disabled = d.busy;
  $("check-update").disabled = d.busy;
  $("rollback").disabled = d.busy || !d.state.previous;
  $("install-update").disabled =
    d.busy || !d.plan || (!d.plan.asr_available && !d.plan.voices_available);
  $("update-status").textContent =
    d.update.stage + (d.update.error ? "：" + d.update.error : "");
  $("update-progress").hidden = d.update.status !== "running";
  $("update-progress").value = d.update.progress || 0;
  const bytes = d.plan
    ? (d.plan.asr_available ? d.plan.asr_bytes : 0) +
      (d.plan.voices_available ? d.plan.voice_bytes : 0)
    : 0;
  $("update-size").textContent = bytes
    ? tr("modelDownloadIntro") + " " + (bytes / 1024 ** 3).toFixed(2) + " GB。" + tr("modelDownloadDetail")
    : tr("modelFirstCheck");
}
async function modelAction(action) {
  try {
    await api("/api/models/" + action, {});
    await renderModels();
  } catch (e) {
    toast(e.message);
  }
}

async function checkSoftwareUpdate(silent = false) {
  $("check-app-update").disabled = true;
  $("app-update-status").textContent = tr("appUpdateChecking");
  try {
    const info = await tauriInvoke("check_app_update");
    softwareUpdateAvailable = Boolean(info.available);
    $("install-app-update").hidden = !softwareUpdateAvailable;
    $("app-update-notes").hidden = !softwareUpdateAvailable || !info.notes;
    $("app-update-notes").textContent = info.notes || "";
    $("app-update-status").textContent = softwareUpdateAvailable
      ? trf("appUpdateAvailable", { version: info.version })
      : tr("appUpdateCurrent");
    if (softwareUpdateAvailable && !silent) toast(trf("appUpdateAvailable", { version: info.version }));
    updateModelsNav();
  } catch (error) {
    $("app-update-status").textContent = tr("appUpdateFailed") + "：" + error;
  } finally {
    $("check-app-update").disabled = false;
  }
}

function formatUpdateBytes(bytes) {
  if (!Number.isFinite(bytes) || bytes <= 0) return "0 MB";
  if (bytes >= 1024 ** 3) return (bytes / 1024 ** 3).toFixed(2) + " GB";
  return (bytes / 1024 ** 2).toFixed(1) + " MB";
}

function renderAppUpdateProgress(progress) {
  const phaseKeys = {
    checking: "appProgressChecking",
    downloading: "appProgressDownloading",
    verifying: "appProgressVerifying",
    stopping: "appProgressStopping",
    installing: "appProgressInstalling",
    error: "appProgressError",
  };
  const percent = Number.isFinite(progress.percent)
    ? Math.max(0, Math.min(100, progress.percent))
    : null;
  $("app-progress-phase").textContent = tr(phaseKeys[progress.phase] || "appProgressPreparing");
  $("app-progress-percent").textContent = percent === null ? "—" : percent.toFixed(1) + "%";
  $("app-progress-bar").value = percent || 0;
  $("app-progress-bar").classList.toggle("indeterminate", percent === null);
  $("app-progress-downloaded").textContent = trf("appProgressDownloaded", {
    size: formatUpdateBytes(progress.downloaded),
  });
  $("app-progress-total").textContent = progress.total
    ? trf("appProgressTotal", { size: formatUpdateBytes(progress.total) })
    : tr("appProgressTotalUnknown");
  $("app-progress-speed").textContent = progress.bytesPerSecond
    ? trf("appProgressSpeed", { speed: formatUpdateBytes(progress.bytesPerSecond) + "/s" })
    : "—";
}

async function pollAppUpdateProgress() {
  try {
    renderAppUpdateProgress(await tauriInvoke("get_app_update_progress"));
  } catch (_) {
    // 主下载命令会显示最终错误；短暂轮询失败不覆盖它。
  }
}

function stopAppUpdateProgressPolling() {
  if (appUpdateProgressTimer) clearInterval(appUpdateProgressTimer);
  appUpdateProgressTimer = null;
}

$("app-progress-close").onclick = () => appUpdateDialog.close();
appUpdateDialog.addEventListener("cancel", (event) => {
  if ($("app-progress-close").hidden) event.preventDefault();
});

$("check-app-update").onclick = () => checkSoftwareUpdate(false);
$("install-app-update").onclick = async () => {
  if (!(await confirmAction(tr("installAppUpdateTitle"), tr("installAppUpdateText")))) return;
  $("install-app-update").disabled = true;
  $("app-update-status").textContent = tr("appUpdateInstalling");
  $("app-progress-error").hidden = true;
  $("app-progress-close").hidden = true;
  renderAppUpdateProgress({ phase: "checking", downloaded: 0, total: null, bytesPerSecond: 0, percent: null });
  appUpdateDialog.showModal();
  stopAppUpdateProgressPolling();
  appUpdateProgressTimer = setInterval(pollAppUpdateProgress, 250);
  try {
    await tauriInvoke("install_app_update");
  } catch (error) {
    stopAppUpdateProgressPolling();
    $("install-app-update").disabled = false;
    $("app-update-status").textContent = tr("appUpdateFailed") + "：" + error;
    $("app-progress-phase").textContent = tr("appProgressError");
    $("app-progress-error").textContent = String(error);
    $("app-progress-error").hidden = false;
    $("app-progress-close").hidden = false;
  }
};
const appCheckSetting = localStorage.getItem("hearnotes.appCheckOnStart");
$("app-check-on-start").checked = appCheckSetting === null || appCheckSetting === "true";
$("app-check-on-start").onchange = () => {
  localStorage.setItem("hearnotes.appCheckOnStart", String($("app-check-on-start").checked));
  toast(tr("updateSaved"));
};
$("check-update").onclick = () => modelAction("check");
$("download-models").onclick = async () => {
  if (!(await confirmAction(tr("downloadModelsTitle"), tr("downloadModelsText")))) return;
  try {
    await api("/api/models/bootstrap", {});
    await poll();
  } catch (e) {
    toast(e.message);
  }
};
$("install-update").onclick = async () => {
  if (
    await confirmAction(
      tr("confirmInstallTitle"),
      $("update-size").textContent + " " + tr("confirmInstallText"),
    )
  )
    modelAction("install");
};
$("rollback").onclick = async () => {
  if (
    await confirmAction(
      tr("confirmRollbackTitle"),
      tr("confirmRollbackText"),
    )
  )
    modelAction("rollback");
};
$("check-on-start").onchange = async () => {
  try {
    await api("/api/models/settings", {
      check_on_start: $("check-on-start").checked,
    });
    toast(tr("updateSaved"));
  } catch (e) {
    toast(e.message);
    await renderModels();
  }
};
$("quit").onclick = async () => {
  if (
    !(await confirmAction(
      tr("quitTitle"),
      (dirty ? tr("quitUnsaved") : "") + tr("quitRunning"),
    ))
  )
    return;
  try {
    await api("/api/shutdown", {});
    dirty = false;
    document.body.replaceChildren(
      el("main", "", tr("quitText")),
    );
  } catch (e) {
    toast(e.message);
  }
};
poll();
setInterval(poll, 2500);
if ($("app-check-on-start").checked) checkSoftwareUpdate(true);
