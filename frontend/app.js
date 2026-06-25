/**
 * WebIntel-Agent v2.0 — 前端交互
 */

(function () {
  "use strict";

  // DOM
  const $ = (sel) => document.querySelector(sel);
  const form = $("#analyzeForm");
  const urlInput = $("#urlInput");
  const submitBtn = $("#submitBtn");
  const btnText = submitBtn.querySelector(".btn-text");
  const btnLoading = submitBtn.querySelector(".btn-loading");
  const errorMsg = $("#errorMsg");
  const loadingSection = $("#loadingSection");
  const resultSection = $("#resultSection");
  const historyToggle = $("#historyToggle");
  const historyPanel = $("#historyPanel");
  const historyOverlay = $("#historyOverlay");
  const historyList = $("#historyList");
  const closeHistory = $("#closeHistory");
  const clearHistoryBtn = $("#clearHistory");
  const llmStatus = $("#llmStatus");

  // ====== Health Check ======
  async function checkHealth() {
    try {
      const res = await fetch("/api/health");
      const data = await res.json();
      const dot = llmStatus.querySelector(".llm-dot");
      const text = llmStatus.querySelector(".llm-text");
      if (data.llm_configured) {
        dot.className = "llm-dot active";
        text.textContent = "LLM 就绪";
      } else {
        dot.className = "llm-dot inactive";
        text.textContent = "模拟模式";
      }
    } catch (_) {
      const dot = llmStatus.querySelector(".llm-dot");
      const text = llmStatus.querySelector(".llm-text");
      dot.className = "llm-dot inactive";
      text.textContent = "离线";
    }
  }
  checkHealth();

  // ====== Loading Animation ======
  function showLoading() {
    loadingSection.hidden = false;
    resultSection.hidden = true;
    errorMsg.hidden = true;
    const steps = loadingSection.querySelectorAll(".loading-step");
    steps.forEach((s) => s.classList.remove("active", "done"));
    steps[0].classList.add("active");

    // 动态步骤推进
    setTimeout(() => {
      if (!loadingSection.hidden) {
        steps[0].classList.add("done");
        steps[0].classList.remove("active");
        steps[1].classList.add("active");
      }
    }, 2000);

    setTimeout(() => {
      if (!loadingSection.hidden) {
        steps[1].classList.add("done");
        steps[1].classList.remove("active");
        steps[2].classList.add("active");
      }
    }, 5000);
  }

  function hideLoading() {
    loadingSection.hidden = true;
    // 重置进度条
    const fill = loadingSection.querySelector(".loading-bar-fill");
    fill.style.animation = "none";
    fill.offsetHeight; // trigger reflow
    fill.style.animation = "";
  }

  // ====== Render Result ======
  function renderResult(data) {
    const a = data.analysis;

    // Meta
    $("#resultTitle").textContent = data.title || "无标题";
    const urlEl = $("#resultUrl");
    urlEl.href = data.url;
    urlEl.textContent = data.url;
    $("#pageType").textContent = data.page_type || "article";
    $("#contentLength").textContent = formatLength(data.content_length);

    // Summary
    $("#resultSummary").textContent = a.summary;

    // Sentiment
    const score = a.sentiment_score;
    const gaugeFill = $("#gaugeFill");
    const gaugeIndicator = $("#gaugeIndicator");
    gaugeFill.style.width = (score * 100) + "%";
    gaugeIndicator.style.left = (score * 100) + "%";
    const scoreEl = $("#sentimentScore");
    scoreEl.textContent = (score * 100).toFixed(0) + "%";
    scoreEl.style.color = score > 0.6 ? "var(--positive)" : score < 0.4 ? "var(--negative)" : "var(--neutral)";

    // Insights
    const insightsEl = $("#resultInsights");
    insightsEl.innerHTML = "";
    (a.key_insights || []).forEach((ins) => {
      const item = document.createElement("div");
      item.className = "insight-item";
      item.innerHTML =
        '<div class="insight-confidence">' + Math.round(ins.confidence * 100) + '%</div>' +
        '<div class="insight-point">' + escapeHtml(ins.point) + '</div>';
      insightsEl.appendChild(item);
    });

    // Tech Stack
    const techEl = $("#resultTech");
    techEl.innerHTML = "";
    if (a.tech_stack && a.tech_stack.length > 0) {
      const list = document.createElement("div");
      list.className = "tech-list";
      a.tech_stack.forEach((t) => {
        const tag = document.createElement("div");
        tag.className = "tech-tag";
        tag.innerHTML = escapeHtml(t.name) + ' <span class="tech-category">' + escapeHtml(t.category) + '</span>';
        list.appendChild(tag);
      });
      techEl.appendChild(list);
    } else {
      techEl.innerHTML = '<span style="color:var(--text-tertiary);font-size:0.875rem;">未识别到技术栈</span>';
    }

    // Keywords
    const kwEl = $("#resultKeywords");
    kwEl.innerHTML = "";
    (a.keywords || []).forEach((kw) => {
      const tag = document.createElement("span");
      tag.className = "keyword-tag";
      tag.textContent = kw;
      kwEl.appendChild(tag);
    });

    resultSection.hidden = false;
    resultSection.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  // ====== Submit ======
  function setLoading(loading) {
    submitBtn.disabled = loading;
    btnText.hidden = loading;
    btnLoading.hidden = !loading;
  }

  function showError(msg) {
    errorMsg.textContent = msg;
    errorMsg.hidden = false;
    resultSection.hidden = true;
    hideLoading();
  }

  async function handleSubmit(e) {
    e.preventDefault();
    errorMsg.hidden = true;

    let url = urlInput.value.trim();
    if (!url) return showError("请输入网址");
    if (!/^https?:\/\//i.test(url)) url = "https://" + url;

    setLoading(true);
    showLoading();

    try {
      const res = await fetch("/api/analyze", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url }),
      });

      hideLoading();

      if (!res.ok) {
        let detail = "请求失败";
        try { detail = (await res.json()).detail; } catch (_) {}
        throw new Error(detail);
      }

      const data = await res.json();
      renderResult(data);
      loadHistory();
    } catch (err) {
      showError(err.message || "分析失败，请稍后重试");
    } finally {
      setLoading(false);
    }
  }

  // ====== History ======
  async function loadHistory() {
    try {
      const res = await fetch("/api/history?limit=50");
      const data = await res.json();
      renderHistory(data.history || []);
    } catch (_) {}
  }

  function renderHistory(items) {
    historyList.innerHTML = "";
    if (items.length === 0) {
      historyList.innerHTML = '<p class="history-empty">暂无历史记录</p>';
      return;
    }
    items.forEach((item) => {
      const el = document.createElement("div");
      el.className = "history-item";
      const dotColor = item.sentiment_label === "positive" ? "var(--positive)"
        : item.sentiment_label === "negative" ? "var(--negative)" : "var(--neutral)";
      const label = item.sentiment_label === "positive" ? "积极"
        : item.sentiment_label === "negative" ? "消极" : "中性";
      el.innerHTML =
        '<div class="history-item-title">' + escapeHtml(item.title || "无标题") + '</div>' +
        '<div class="history-item-url">' + escapeHtml(item.url) + '</div>' +
        '<div class="history-item-meta">' +
          '<span class="history-sentiment"><span class="history-sentiment-dot" style="background:' + dotColor + '"></span>' + label + ' ' + (item.sentiment_score * 100).toFixed(0) + '%</span>' +
          '<span>' + formatTime(item.fetched_at) + '</span>' +
        '</div>';
      el.addEventListener("click", () => {
        urlInput.value = item.url;
        closeHistoryPanel();
      });
      historyList.appendChild(el);
    });
  }

  function openHistoryPanel() {
    historyPanel.classList.add("open");
    historyOverlay.hidden = false;
    loadHistory();
  }

  function closeHistoryPanel() {
    historyPanel.classList.remove("open");
    historyOverlay.hidden = true;
  }

  // ====== Utils ======
  function formatLength(len) {
    if (len >= 10000) return (len / 10000).toFixed(1) + " 万字";
    return len.toLocaleString() + " 字符";
  }

  function formatTime(iso) {
    if (!iso) return "";
    try {
      const d = new Date(iso);
      return d.toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit" });
    } catch (_) {
      return "";
    }
  }

  function escapeHtml(str) {
    if (!str) return "";
    return str.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
  }

  // ====== Events ======
  form.addEventListener("submit", handleSubmit);
  historyToggle.addEventListener("click", openHistoryPanel);
  closeHistory.addEventListener("click", closeHistoryPanel);
  historyOverlay.addEventListener("click", closeHistoryPanel);
  clearHistoryBtn.addEventListener("click", async () => {
    await fetch("/api/history", { method: "DELETE" });
    loadHistory();
  });

  // ====== Settings Panel ======
  const settingsToggle = $("#settingsToggle");
  const settingsPanel = $("#settingsPanel");
  const settingsOverlay = $("#settingsOverlay");
  const closeSettingsBtn = $("#closeSettings");
  const saveSettingsBtn = $("#saveSettings");
  const settingProvider = $("#settingProvider");
  const settingApiKey = $("#settingApiKey");
  const settingBaseUrl = $("#settingBaseUrl");
  const settingModel = $("#settingModel");
  const apiKeyStatus = $("#apiKeyStatus");
  const settingsMsg = $("#settingsMsg");
  const toggleKeyBtn = $("#toggleKeyVisibility");

  async function loadSettings() {
    try {
      const res = await fetch("/api/settings");
      const data = await res.json();
      settingProvider.value = data.llm_provider || "deepseek";
      settingBaseUrl.value = data.llm_base_url || "";
      settingModel.value = data.llm_model || "";
      apiKeyStatus.textContent = data.llm_api_key_masked || "未配置";
      apiKeyStatus.className = "setting-status" + (data.llm_api_key_set ? " active" : "");
    } catch (_) {}
  }

  function openSettingsPanel() {
    settingsPanel.classList.add("open");
    settingsOverlay.hidden = false;
    loadSettings();
  }

  function closeSettingsPanel() {
    settingsPanel.classList.remove("open");
    settingsOverlay.hidden = true;
    settingsMsg.hidden = true;
  }

  // 快捷预设
  document.querySelectorAll(".preset-btn").forEach(function (btn) {
    btn.addEventListener("click", function () {
      settingProvider.value = btn.dataset.provider;
      settingBaseUrl.value = btn.dataset.url;
      settingModel.value = btn.dataset.model;
    });
  });

  // 显示/隐藏 API Key
  toggleKeyBtn.addEventListener("click", function () {
    settingApiKey.type = settingApiKey.type === "password" ? "text" : "password";
  });

  // 保存设置
  saveSettingsBtn.addEventListener("click", async function () {
    const body = {};
    if (settingApiKey.value.trim()) body.llm_api_key = settingApiKey.value.trim();
    body.llm_provider = settingProvider.value;
    body.llm_base_url = settingBaseUrl.value.trim();
    body.llm_model = settingModel.value.trim();

    try {
      const res = await fetch("/api/settings", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      const data = await res.json();
      if (res.ok) {
        settingsMsg.className = "settings-msg success";
        settingsMsg.textContent = "配置已保存！" + (data.llm_api_key_set ? " API Key 已配置。" : "");
        apiKeyStatus.textContent = data.llm_api_key_masked || "未配置";
        apiKeyStatus.className = "setting-status" + (data.llm_api_key_set ? " active" : "");
        settingApiKey.value = "";
        checkHealth();
      } else {
        settingsMsg.className = "settings-msg error";
        settingsMsg.textContent = data.detail || "保存失败";
      }
    } catch (err) {
      settingsMsg.className = "settings-msg error";
      settingsMsg.textContent = "网络错误";
    }
    settingsMsg.hidden = false;
  });

  settingsToggle.addEventListener("click", openSettingsPanel);
  closeSettingsBtn.addEventListener("click", closeSettingsPanel);
  settingsOverlay.addEventListener("click", closeSettingsPanel);

  // 初始加载历史
  loadHistory();
})();
