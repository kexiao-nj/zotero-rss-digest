var RSS_DIGEST_PREF_PREFIX = "extensions.rssdigest.";

Zotero.RSSDigest = {
  pluginID: "rss-digest@zotero-rss-analyzer.local",
  rootURI: null,
  id: null,
  version: null,
  _timer: null,
  _window: null,
  _prefsWindow: null,
  lastScan: null,
  addedMenuIds: [],
  _overlayWanted: false,
  _notifierID: null,
  _scanning: false,
  _progressEnabled: false,
  _scanItemProgress: null,

  async init({ id, version, rootURI }) {
    this.id = id;
    this.version = version;
    this.rootURI = rootURI;
    // Keep settings in our own window. Registering a Zotero PreferencePane
    // repeatedly broke the built-in Settings sidebar in Zotero 10.0.2.
    await Zotero.uiReadyPromise;
    await this.restoreLastScan();
    this._watchTabs();
    for (let win of Zotero.getMainWindows()) {
      this.onMainWindowLoad(win);
    }
    this.startTimer();
    Zotero.debug("RSS Digest initialized for Zotero 10");
  },

  async shutdown() {
    this.stopTimer();
    this._unwatchTabs();
    for (let win of Zotero.getMainWindows()) {
      this.onMainWindowUnload(win);
    }
    if (this._window && !this._window.closed) {
      this._window.close();
    }
    if (this._prefsWindow && !this._prefsWindow.closed) {
      this._prefsWindow.close();
    }
    for (let win of Zotero.getMainWindows()) {
      win.document.getElementById("rss-digest-host")?.remove();
    }
    delete Zotero.RSSDigest;
  },

  initPreferences(root) {
    if (!root || root.getAttribute("data-rss-digest-bound") === "true") {
      return;
    }
    root.setAttribute("data-rss-digest-bound", "true");

    const $ = (id) => root.querySelector("#" + id);
    const fill = (id, key, fallback) => {
      const el = $(id);
      if (!el) {
        return;
      }
      const current = this.pref(key, fallback);
      el.value = current === undefined || current === null ? "" : String(current);
      if (el.classList && el.classList.contains("rd-single")) {
        el.addEventListener("keydown", (e) => {
          if (e.key === "Enter") {
            e.preventDefault();
          }
        });
      }
    };

    fill("rss-digest-api-base", "apiBase", "https://api.openai.com/v1");
    fill("rss-digest-api-key", "apiKey", "");
    fill("rss-digest-model", "model", "gpt-4o-mini");
    fill("rss-digest-interval", "intervalHours", 6);
    fill("rss-digest-collection", "collectionName", "RSS Digest");
    fill("rss-digest-topics", "topics", "");
    fill("rss-digest-include", "includeKeywords", "");
    fill("rss-digest-exclude", "excludeKeywords", "");

    let pendingLang = String(this.pref("language", "zh"));
    const paintLang = () => {
      root.querySelectorAll("[data-lang]").forEach((chip) => {
        chip.classList.toggle("on", chip.getAttribute("data-lang") === pendingLang);
      });
    };
    paintLang();
    root.querySelectorAll("[data-lang]").forEach((chip) => {
      chip.addEventListener("mousedown", (e) => {
        e.stopPropagation();
        pendingLang = chip.getAttribute("data-lang");
        paintLang();
      });
    });

    const status = $("rss-digest-pref-status");
    const setStatus = (text) => {
      if (status) {
        status.textContent = text;
      }
    };

    const saveAll = () => {
      const val = (id, fallback = "") => {
        const el = $(id);
        return el ? String(el.value ?? fallback) : fallback;
      };
      this.setPref("apiBase", val("rss-digest-api-base").trim());
      this.setPref("apiKey", val("rss-digest-api-key").trim());
      this.setPref("model", val("rss-digest-model").trim() || "gpt-4o-mini");
      this.setPref("intervalHours", Number(val("rss-digest-interval")) || 6);
      this.setPref("language", pendingLang || "zh");
      this.setPref("collectionName", val("rss-digest-collection").trim() || "RSS Digest");
      this.setPref("topics", val("rss-digest-topics"));
      this.setPref("includeKeywords", val("rss-digest-include"));
      this.setPref("excludeKeywords", val("rss-digest-exclude"));
      this.startTimer();
      setStatus(this.t("已保存。", "Saved."));
    };

    const saveBtn = $("rss-digest-save-prefs");
    saveBtn?.addEventListener("mousedown", (e) => {
      e.stopPropagation();
      saveAll();
    });

    const testBtn = $("rss-digest-test-llm");
    testBtn?.addEventListener("mousedown", async (e) => {
      e.stopPropagation();
      saveAll();
      setStatus(this.t("正在测试…", "Testing…"));
      try {
        await this.testLLM();
        setStatus(this.t("已保存，LLM 可用。", "Saved. LLM OK."));
      } catch (err) {
        setStatus(this.t("已保存，但 LLM 失败：", "Saved, but LLM failed: ") + err);
      }
    });
  },

  onMainWindowLoad(win) {
    this._installToolsMenu(win);
  },

  onMainWindowUnload(win) {
    if (!win.ZoteroPane) {
      return;
    }
    this._removeToolsMenu(win);
    win.document.getElementById("rss-digest-host")?.remove();
  },

  pref(key, fallback) {
    const value = Zotero.Prefs.get(RSS_DIGEST_PREF_PREFIX + key, true);
    return value === undefined || value === null ? fallback : value;
  },

  setPref(key, value) {
    Zotero.Prefs.set(RSS_DIGEST_PREF_PREFIX + key, value, true);
  },

  isZh() {
    return String(this.pref("language", "zh")).startsWith("zh");
  },

  t(zh, en) {
    return this.isZh() ? zh : en;
  },

  profile() {
    const lines = (key) =>
      String(this.pref(key, ""))
        .split(/\r?\n/)
        .map((s) => s.trim())
        .filter(Boolean);
    return {
      topics: lines("topics"),
      include_keywords: lines("includeKeywords"),
      exclude_keywords: lines("excludeKeywords"),
      require_any_keywords: [],
      journal_whitelist: [],
      feed_allowlist: [],
      feed_blocklist: [],
      min_rule_score: Number(this.pref("minRuleScore", 2)),
      min_llm_score: Number(this.pref("minLlmScore", 3)),
      priority_thresholds: { close_read: 4, skim: 3 },
    };
  },

  statePath() {
    return PathUtils.join(Zotero.DataDirectory.dir, "rss-digest-state.json");
  },

  async loadState() {
    try {
      return JSON.parse(await IOUtils.readUTF8(this.statePath()));
    } catch (e) {
      return { seen_guids: [], last_run: null, runs: [] };
    }
  },

  async saveState(state) {
    await IOUtils.writeUTF8(
      this.statePath(),
      JSON.stringify(state, null, 2) + "\n",
    );
  },

  _installToolsMenu(win) {
    const doc = win.document;
    if (doc.getElementById("rss-digest-tools-menu")) {
      return;
    }
    const popup = doc.getElementById("menu_ToolsPopup");
    if (!popup) {
      return;
    }
    const menu = doc.createXULElement("menu");
    menu.id = "rss-digest-tools-menu";
    menu.setAttribute("label", "RSS Digest");
    const sub = doc.createXULElement("menupopup");
    sub.appendChild(
      this._menuItem(doc, "rss-digest-open", this.t("打开结果", "Open results"), () =>
        this.openOverlay("results"),
      ),
    );
    sub.appendChild(
      this._menuItem(doc, "rss-digest-scan", this.t("立即扫描", "Scan now"), () =>
        this.scanAndShow(),
      ),
    );
    sub.appendChild(
      this._menuItem(doc, "rss-digest-rescan", this.t("重新扫描", "Rescan"), () =>
        this.scanAndShow({ rescan: true }),
      ),
    );
    sub.appendChild(
      this._menuItem(doc, "rss-digest-export", this.t("导出 Markdown", "Export Markdown"), () =>
        this.exportMarkdown(),
      ),
    );
    sub.appendChild(
      this._menuItem(doc, "rss-digest-prefs", this.t("设置", "Settings"), () =>
        this.openOverlay("prefs"),
      ),
    );
    menu.appendChild(sub);
    popup.appendChild(menu);
  },

  _menuItem(doc, id, label, onCommand) {
    const item = doc.createXULElement("menuitem");
    item.id = id;
    item.setAttribute("label", label);
    item.addEventListener("command", onCommand);
    return item;
  },

  _removeToolsMenu(win) {
    win.document.getElementById("rss-digest-tools-menu")?.remove();
  },

  startTimer() {
    this.stopTimer();
    const hours = Math.max(0.25, Number(this.pref("intervalHours", 6)) || 6);
    const ms = hours * 60 * 60 * 1000;
    this._timer = Components.classes["@mozilla.org/timer;1"].createInstance(
      Components.interfaces.nsITimer,
    );
    this._timer.initWithCallback(
      { notify: () => this.scan({ silent: true }).catch((e) => Zotero.logError(e)) },
      ms,
      Components.interfaces.nsITimer.TYPE_REPEATING_SLACK,
    );
  },

  stopTimer() {
    if (this._timer) {
      this._timer.cancel();
      this._timer = null;
    }
  },

  openWindow() {
    return this.openOverlay("results");
  },

  openPrefsWindow() {
    return this.openOverlay("prefs");
  },

  openOverlay(pane) {
    const win = Zotero.getMainWindow();
    if (!win) {
      return null;
    }
    this._overlayWanted = true;
    const host = this._ensureOverlay(win);
    if (!host) {
      return null;
    }
    this._showOverlayPane(host, pane || "results");
    this._paintLastScan();
    this._syncOverlayVisibility();
    this.restoreLastScan().then(() => this._paintLastScan());
    win.focus();
    return host;
  },

  _watchTabs() {
    if (this._notifierID != null) {
      return;
    }
    this._tabObserver = {
      notify: (event) => {
        if (event === "select" || event === "add" || event === "close" || event === "load") {
          this._syncOverlayVisibility();
        }
      },
    };
    this._notifierID = Zotero.Notifier.registerObserver(this._tabObserver, ["tab"], "rss-digest");
  },

  _unwatchTabs() {
    if (this._notifierID == null) {
      return;
    }
    try {
      Zotero.Notifier.unregisterObserver(this._notifierID);
    } catch (e) {}
    this._notifierID = null;
    this._tabObserver = null;
  },

  _isLibraryTab(win) {
    try {
      const tabs = win.Zotero_Tabs;
      if (tabs && tabs.selectedID) {
        return tabs.selectedID === "zotero-pane";
      }
    } catch (e) {}
    return true;
  },

  _syncOverlayVisibility() {
    const win = Zotero.getMainWindow();
    const host = win?.document.getElementById("rss-digest-host");
    if (!host) {
      return;
    }
    const show = this._overlayWanted && this._isLibraryTab(win);
    host.style.display = show ? "flex" : "none";
  },

  _hideOverlay(host) {
    this._overlayWanted = false;
    if (host) {
      host.style.display = "none";
    }
  },

  async restoreLastScan() {
    if (this.lastScan && this.lastScan.related && this.lastScan.related.length) {
      return this.lastScan;
    }
    try {
      const state = await this.loadState();
      if (state.last_scan) {
        this.lastScan = state.last_scan;
      }
    } catch (e) {
      Zotero.debug("RSS Digest: restore last scan failed: " + e);
    }
    return this.lastScan;
  },

  async persistLastScan(result) {
    try {
      const state = await this.loadState();
      state.last_scan = JSON.parse(
        JSON.stringify({
          at: result?.at || null,
          feedCount: result?.feedCount || 0,
          ingested: result?.ingested || 0,
          newCount: result?.newCount || 0,
          related: result?.related || [],
          skipped: [],
          skippedCount: (result?.skipped || []).length,
          themes: result?.themes || [],
          empty: !!result?.empty,
        }),
      );
      await this.saveState(state);
    } catch (e) {
      Zotero.debug("RSS Digest: persist last scan failed: " + e);
    }
  },

  _paintLastScan() {
    if (this.lastScan) {
      this.renderOverlay(this.lastScan);
    }
  },

  _ensureOverlay(win) {
    const doc = win.document;
    const pane = doc.getElementById("zotero-pane");
    if (!pane) {
      Zotero.debug("RSS Digest: zotero-pane missing");
      return null;
    }
    let host = doc.getElementById("rss-digest-host");
    if (host && !host.querySelector("#rd-profile-help")) {
      host.remove();
      host = null;
    }
    if (host) {
      host.style.display = "flex";
      return host;
    }
    const NS = "http://www.w3.org/1999/xhtml";
    host = doc.createElementNS(NS, "div");
    host.id = "rss-digest-host";
    host.innerHTML = this._overlayMarkup();
    const style = doc.createElementNS(NS, "style");
    style.textContent = this._overlayCSS();
    host.prepend(style);
    pane.appendChild(host);

    const $ = (id) => host.querySelector("#" + id);
    const on = (id, fn) => {
      const el = $(id);
      if (!el) {
        return;
      }
      el.addEventListener("mousedown", (e) => {
        e.stopPropagation();
        fn();
      });
    };
    on("rd-btn-scan", () => this.scanAndShow());
    on("rd-btn-rescan", () => this.scanAndShow({ rescan: true }));
    on("rd-btn-export", () => this.exportMarkdown());
    on("rd-btn-results", () => this._showOverlayPane(host, "results"));
    on("rd-btn-prefs", () => this._showOverlayPane(host, "prefs"));
    on("rd-btn-close", () => this._hideOverlay(host));
    host.addEventListener("mousedown", (e) => e.stopPropagation());
    host.addEventListener("keydown", (e) => e.stopPropagation());
    host.addEventListener("keyup", (e) => e.stopPropagation());
    this.initPreferences($("rss-digest-prefs"));
    if (this.lastScan) {
      this.renderOverlay(this.lastScan);
    } else {
      this._setOverlayStatus(this.t("点击「立即扫描」读取订阅", "Click Scan now to read feeds"));
    }
    return host;
  },

  _showOverlayPane(host, pane) {
    host.style.display = "flex";
    const prefs = host.querySelector("#rd-pane-prefs");
    const results = host.querySelector("#rd-pane-results");
    const isPrefs = pane === "prefs";
    prefs.style.display = isPrefs ? "block" : "none";
    results.style.display = isPrefs ? "none" : "block";
    host.querySelector("#rd-btn-prefs").setAttribute("aria-pressed", isPrefs ? "true" : "false");
    host.querySelector("#rd-btn-results").setAttribute("aria-pressed", isPrefs ? "false" : "true");
  },

  _setOverlayStatus(text) {
    const el = Zotero.getMainWindow()?.document.getElementById("rd-status");
    if (el) {
      el.textContent = text;
    }
  },

  _overlayMarkup() {
    const zh = this.isZh();
    return `
<div class="rd-toolbar">
  <strong>RSS Digest</strong>
  <div class="rd-btn" id="rd-btn-scan">${zh ? "立即扫描" : "Scan now"}</div>
  <div class="rd-btn" id="rd-btn-rescan">${zh ? "重新扫描" : "Rescan"}</div>
  <div class="rd-btn" id="rd-btn-export">${zh ? "导出 Markdown" : "Export MD"}</div>
  <div class="rd-btn" id="rd-btn-results">${zh ? "结果" : "Results"}</div>
  <div class="rd-btn" id="rd-btn-prefs">${zh ? "设置" : "Settings"}</div>
  <span id="rd-status"></span>
  <div class="rd-btn" id="rd-btn-close">${zh ? "关闭" : "Close"}</div>
</div>
<div id="rd-pane-prefs">
  <div id="rss-digest-prefs" class="rd-form">
    <h2>LLM API</h2>
    <label>Base URL</label>
    <textarea id="rss-digest-api-base" class="rd-single" rows="1"></textarea>
    <p class="rd-hint">OpenAI-compatible endpoint. DeepSeek / OpenRouter / local vLLM all work.</p>
    <label>API Key</label>
    <textarea id="rss-digest-api-key" class="rd-single" rows="1"></textarea>
    <label>Model</label>
    <textarea id="rss-digest-model" class="rd-single" rows="1"></textarea>
    <h2>Scan</h2>
    <div class="rd-row">
      <div>
        <label>Interval (hours)</label>
        <textarea id="rss-digest-interval" class="rd-single" rows="1"></textarea>
      </div>
      <div>
        <label>Digest language</label>
        <div class="rd-lang">
          <div class="rd-btn" data-lang="zh">中文</div>
          <div class="rd-btn" data-lang="en">English</div>
        </div>
      </div>
    </div>
    <p class="rd-hint">${zh ? "选择中文后，标题、摘要和提炼卡片都会译成中文，原标题仍保留。" : "When Chinese is selected, title, abstract and digest cards are translated. The original title is kept."}</p>
    <label>Save-to collection name</label>
    <textarea id="rss-digest-collection" class="rd-single" rows="1"></textarea>
    <h2>Research profile</h2>
    <p class="rd-hint" id="rd-profile-help">${
      zh
        ? "Topics 和 Keywords 用来判断一篇订阅论文和你的课题有多相关。先按关键词算规则分（0–5），有 API Key 时再让 LLM 按 Topics 重打一版。卡片上的 Score 优先显示 LLM 分。"
        : "Topics and keywords decide how relevant a feed paper is to you. A rule score (0–5) comes from keyword hits; if an API key is set, the LLM rescores against your topics. The card Score prefers the LLM value."
    }</p>
    <label>Topics (one per line)</label>
    <textarea id="rss-digest-topics" rows="4"></textarea>
    <p class="rd-hint">${
      zh
        ? "课题方向，例如 spatial omics。会和 Include keywords 一起在标题、摘要、期刊、作者里做不区分大小写的子串匹配，用来加规则分；同时作为 LLM 的研究画像（告诉模型你在做什么）。"
        : "Research directions, e.g. spatial omics. Combined with include keywords for case-insensitive substring matching in title/abstract/journal/authors (rule score). Also sent to the LLM as your research profile."
    }</p>
    <label>Include keywords (one per line)</label>
    <textarea id="rss-digest-include" rows="4"></textarea>
    <p class="rd-hint">${
      zh
        ? "希望留下的词。规则分 = min(5, 2 + 命中了几个不同的词/Topic)。一个都没命中 → 0 分，不进结果。规则分低于 2 也会丢掉。Topics 和 Include 都留空时，每篇先给 3 分。"
        : "Terms that should keep a paper. Rule score = min(5, 2 + number of distinct hits, including Topics). No hits → 0, dropped. Scores below 2 are also dropped. If Topics and Include are both empty, every item starts at 3."
    }</p>
    <label>Exclude keywords (one per line)</label>
    <textarea id="rss-digest-exclude" rows="3"></textarea>
    <p class="rd-hint">${
      zh
        ? "黑名单。标题或摘要里出现任一排除词 → 0 分并直接跳过，不再送给 LLM。"
        : "Blocklist. Any hit in title or abstract → score 0 and skip, never sent to the LLM."
    }</p>
    <p class="rd-hint">${
      zh
        ? "最终 Score：有 API Key 时用 LLM 的 0–5 整数（只处理规则分过关的前 30 篇）；否则用规则分。LLM 分低于 3 的不显示。建议：≥4 精读，≥3 扫摘要，更低忽略。"
        : "Final Score: with an API key, an LLM integer 0–5 (first 30 items that passed the rule filter); otherwise the rule score. LLM scores below 3 are hidden. Suggestions: ≥4 read closely, ≥3 skim, lower skip."
    }</p>
    <div class="rd-actions">
      <div class="rd-btn" id="rss-digest-save-prefs">${zh ? "保存设置" : "Save settings"}</div>
      <div class="rd-btn" id="rss-digest-test-llm">Test LLM</div>
      <span id="rss-digest-pref-status"></span>
    </div>
  </div>
</div>
<div id="rd-pane-results">
  <div id="rd-progress" class="rd-progress">
    <div id="rd-progress-label" class="rd-progress-label"></div>
    <div class="rd-progress-track"><div id="rd-progress-bar" class="rd-progress-bar"></div></div>
    <div id="rd-progress-meta" class="rd-progress-meta"></div>
  </div>
  <div id="summary" class="rd-summary"></div>
  <div id="cards" class="rd-cards"></div>
</div>`;
  },

  _overlayCSS() {
    return `
#rss-digest-host {
  position: fixed;
  top: 56px;
  right: 24px;
  bottom: 24px;
  left: 24px;
  z-index: 1000;
  display: flex;
  flex-direction: column;
  background: Canvas;
  color: CanvasText;
  border: 1px solid #8a8a8a;
  border-radius: 10px;
  box-shadow: 0 12px 40px rgba(0,0,0,.28);
  overflow: hidden;
  font: 13px/1.45 system-ui, sans-serif;
}
#rss-digest-host .rd-toolbar {
  display: flex;
  gap: 8px;
  align-items: center;
  flex-wrap: wrap;
  padding: 10px 12px;
  border-bottom: 1px solid #c6c6c6;
  background: #f4f4f4;
  color: #111;
}
#rss-digest-host .rd-toolbar strong { margin-right: 8px; flex-shrink: 0; }
#rss-digest-host #rd-status {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  pointer-events: none;
}
#rss-digest-host .rd-btn {
  display: inline-block;
  padding: 4px 10px;
  border: 1px solid #8a8a8a;
  border-radius: 6px;
  background: #fff;
  color: #111;
  cursor: default;
  user-select: none;
  white-space: nowrap;
  flex-shrink: 0;
  position: relative;
  z-index: 2;
}
#rss-digest-host #rd-btn-close {
  margin-left: 8px;
}
#rss-digest-host .rd-btn.on,
#rss-digest-host .rd-btn[aria-pressed="true"] {
  background: #1f4e79;
  color: #fff;
  border-color: #1f4e79;
}
#rss-digest-host .rd-lang { display: flex; gap: 8px; margin-top: 4px; }
#rss-digest-host #rd-pane-prefs,
#rss-digest-host #rd-pane-results {
  flex: 1;
  overflow: auto;
  padding: 12px 16px 20px;
}
#rss-digest-host .rd-form label { display: block; margin: 8px 0 2px; font-weight: 650; }
#rss-digest-host .rd-form input,
#rss-digest-host .rd-form select,
#rss-digest-host .rd-form textarea { width: 100%; box-sizing: border-box; }
#rss-digest-host .rd-form textarea { min-height: 72px; font-family: inherit; }
#rss-digest-host .rd-form textarea.rd-single {
  min-height: 28px;
  height: 28px;
  resize: none;
  overflow: hidden;
  white-space: nowrap;
}
#rss-digest-host .rd-row { display: flex; gap: 12px; }
#rss-digest-host .rd-row > * { flex: 1; }
#rss-digest-host .rd-hint { opacity: .75; font-size: 12px; margin: 2px 0 8px; }
#rss-digest-host .rd-progress {
  display: none;
  margin: 0 0 12px;
  padding: 10px 12px;
  border: 1px solid #d0d7de;
  border-radius: 8px;
  background: #f6f8fa;
}
#rss-digest-host .rd-progress-label {
  font-weight: 650;
  margin-bottom: 6px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
#rss-digest-host .rd-progress-track {
  height: 8px;
  background: #e6e8eb;
  border-radius: 99px;
  overflow: hidden;
}
#rss-digest-host .rd-progress-bar {
  height: 100%;
  width: 0;
  background: #1f4e79;
  border-radius: 99px;
}
#rss-digest-host .rd-progress-meta { margin-top: 4px; font-size: 12px; opacity: .75; }
#rss-digest-host .rd-btn.busy { opacity: .55; pointer-events: none; }
#rss-digest-host .rd-actions { margin-top: 12px; display: flex; gap: 8px; align-items: center; }
#rss-digest-host .rd-cards { display: flex; flex-direction: column; gap: 12px; }
#rss-digest-host .card { border: 1px solid #d0d7de; border-radius: 8px; padding: 12px 14px; background: #fff; color: #111; }
#rss-digest-host .card h3 { margin: 0 0 6px; font-size: 15px; }
#rss-digest-host .orig-title { font-size: 12px; opacity: .75; margin: 0 0 8px; }
#rss-digest-host .meta, #rss-digest-host .orig, #rss-digest-host .ai { font-size: 12.5px; margin: 4px 0; }
#rss-digest-host .label { font-weight: 650; color: #1f4e79; }
#rss-digest-host .empty { padding: 24px; color: #666; }
`;
  },

  renderOverlay(result) {
    const win = Zotero.getMainWindow();
    const host = win?.document.getElementById("rss-digest-host");
    if (!host) {
      return;
    }
    const zh = this.isZh();
    const summary = host.querySelector("#summary");
    const cards = host.querySelector("#cards");
    if (!result || result.empty) {
      summary.textContent = "";
      cards.innerHTML =
        '<div class="empty">' +
        (zh ? "没有新的相关条目。" : "No new relevant items.") +
        "</div>";
      this._setOverlayStatus(zh ? "无新条目" : "No new items");
      return;
    }
    let head =
      (zh ? "新条目 " : "New ") +
      result.newCount +
      (zh ? " · 相关 " : " · relevant ") +
      result.related.length +
      (zh ? " · 跳过 " : " · skipped ") +
      result.skipped.length;
    if (result.themes?.length) {
      head +=
        "<div><b>" +
        (zh ? "本轮主题" : "Themes") +
        ":</b> " +
        result.themes.map((t) => this._esc(t)).join(" · ") +
        "</div>";
    }
    summary.innerHTML = head;
    cards.innerHTML = "";
    for (const scored of result.related) {
      cards.appendChild(this._overlayCard(scored, zh));
    }
    this._setOverlayStatus(zh ? "扫描完成" : "Scan complete");
  },

  _overlayCard(scored, zh) {
    const it = scored.item;
    const card = scored.card || {};
    const el = Zotero.getMainWindow().document.createElementNS(
      "http://www.w3.org/1999/xhtml",
      "div",
    );
    el.className = "card";
    const displayTitle = (zh && card.title_zh) || it.title || "(untitled)";
    const row = (label, value, html) =>
      `<div class="meta"><span class="label">${this._esc(label)}: </span>` +
      (html ? value : this._esc(value)) +
      "</div>";
    const origBits = [
      zh && card.title_zh && it.title && card.title_zh !== it.title
        ? row(zh ? "原标题" : "Original title", it.title)
        : "",
      row(zh ? "订阅" : "Feed", it.feedName + (it.publicationTitle ? " / " + it.publicationTitle : "")),
      row(zh ? "作者" : "Authors", it.authorLine || "—"),
      row(zh ? "日期" : "Date", it.date || it.dateAdded || "—"),
      it.doi ? row("DOI", it.doi) : "",
      it.url
        ? row(zh ? "链接" : "URL", `<a href="${this._esc(it.url)}">${this._esc(it.url)}</a>`, true)
        : "",
      row(zh ? "摘要" : "Abstract", (zh && card.abstract_zh) || it.abstract || "—"),
      zh && card.abstract_zh && it.abstract ? row("原文摘要", it.abstract) : "",
    ].join("");
    const aiBits = [
      card.one_liner ? row(zh ? "一句话" : "One-liner", card.one_liner) : "",
      card.why_relevant ? row(zh ? "为何相关" : "Why relevant", card.why_relevant) : "",
      card.conclusion ? row(zh ? "要点" : "Takeaway", card.conclusion) : "",
      row(zh ? "建议" : "Suggestion", card.suggestion || "—"),
      row("Score", String(scored.llmScore ?? scored.ruleScore)),
    ].join("");
    el.innerHTML =
      `<h3>${this._esc(displayTitle)}</h3>` +
      `<div class="orig">${origBits}</div>` +
      `<div class="ai">${aiBits}</div>` +
      `<div class="rd-actions">
        <div class="rd-btn save">${zh ? "添加到我的文库" : "Add to My Library"}</div>
        <span class="saved"></span>
      </div>`;
    el.querySelector(".save").addEventListener("mousedown", async (ev) => {
      ev.stopPropagation();
      const btn = ev.currentTarget;
      if (btn.getAttribute("data-busy") === "1") {
        return;
      }
      btn.setAttribute("data-busy", "1");
      try {
        await this.saveToLibrary(it.id);
        el.querySelector(".saved").textContent = zh ? "已保存" : "Saved";
      } catch (e) {
        el.querySelector(".saved").textContent = String(e);
        btn.removeAttribute("data-busy");
      }
    });
    return el;
  },

  _esc(s) {
    return String(s || "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  },

  _trim(text, max) {
    const s = String(text || "").replace(/\s+/g, " ").trim();
    if (s.length <= max) {
      return s;
    }
    return s.slice(0, Math.max(0, max - 1)) + "…";
  },

  async _tick() {
    if (Zotero.Promise && typeof Zotero.Promise.delay === "function") {
      await Zotero.Promise.delay(1);
    } else {
      await new Promise((resolve) => setTimeout(resolve, 0));
    }
  },

  _setScanBusy(busy) {
    const doc = Zotero.getMainWindow()?.document;
    if (!doc) {
      return;
    }
    for (const id of ["rd-btn-scan", "rd-btn-rescan"]) {
      doc.getElementById(id)?.classList.toggle("busy", !!busy);
    }
  },

  _phasePercent(phase, current, total) {
    const spans = {
      feeds: [2, 40],
      score: [40, 48],
      llm: [48, 86],
      translate: [86, 93],
      cluster: [93, 97],
      save: [97, 100],
    };
    const [lo, hi] = spans[phase] || [0, 100];
    if (!total) {
      return lo;
    }
    return Math.round(lo + ((hi - lo) * current) / total);
  },

  async _reportProgress({ phase, current, total, detail } = {}) {
    if (!this._progressEnabled) {
      return;
    }
    const zh = this.isZh();
    const names = {
      feeds: zh ? "读取订阅" : "Reading feeds",
      score: zh ? "规则筛选" : "Filtering",
      llm: zh ? "LLM 提炼" : "LLM distill",
      translate: zh ? "补译中文" : "Translating",
      cluster: zh ? "归纳主题" : "Clustering themes",
      save: zh ? "保存状态" : "Saving",
    };
    const pct = this._phasePercent(phase, current, total);
    const bits = [names[phase] || (zh ? "扫描中" : "Scanning")];
    if (total) {
      bits.push((current || 0) + "/" + total);
    }
    if (detail) {
      bits.push(this._trim(detail, 56));
    }
    const line = bits.join(" · ");
    this._setOverlayStatus(line);
    this._paintScanProgress(line, pct);
    if (this._scanItemProgress) {
      try {
        this._scanItemProgress.setProgress(pct);
        this._scanItemProgress.setText(line);
      } catch (e) {}
    }
    await this._tick();
  },

  _paintScanProgress(line, pct) {
    const host = Zotero.getMainWindow()?.document.getElementById("rss-digest-host");
    const wrap = host?.querySelector("#rd-progress");
    if (!wrap) {
      return;
    }
    wrap.style.display = "block";
    const label = host.querySelector("#rd-progress-label");
    const bar = host.querySelector("#rd-progress-bar");
    const meta = host.querySelector("#rd-progress-meta");
    if (label) {
      label.textContent = line;
    }
    if (bar) {
      bar.style.width = Math.max(2, Math.min(100, pct || 0)) + "%";
    }
    if (meta) {
      meta.textContent = (pct || 0) + "%";
    }
  },

  _hideScanProgress() {
    const wrap = Zotero.getMainWindow()?.document.querySelector("#rd-progress");
    if (wrap) {
      wrap.style.display = "none";
    }
    this._scanItemProgress = null;
  },

  async scanAndShow(options = {}) {
    this.openOverlay("results");
    if (this._scanning) {
      this._setOverlayStatus(this.t("扫描仍在进行…", "Scan already running…"));
      return;
    }
    this._scanning = true;
    this._setScanBusy(true);
    try {
      const result = await this.scan({ silent: false, rescan: !!options.rescan });
      this.renderOverlay(result);
      return result;
    } catch (e) {
      this._setOverlayStatus(String(e));
      Zotero.logError(e);
      throw e;
    } finally {
      this._scanning = false;
      this._progressEnabled = false;
      this._setScanBusy(false);
      this._hideScanProgress();
    }
  },

  normalizeItem(item, feed) {
    const creators = item.getCreators ? item.getCreators() : [];
    const authors = creators.map((c) => {
      if (c.fieldMode === 1) {
        return c.lastName || "";
      }
      return [c.firstName, c.lastName].filter(Boolean).join(" ");
    }).filter(Boolean);
    const abstract = this._clean(item.getField("abstractNote") || "");
    const doi = String(item.getField("DOI") || "")
      .replace("https://doi.org/", "")
      .trim();
    return {
      id: item.id,
      key: item.key,
      guid: item.guid || item.getField("url") || item.key,
      libraryID: item.libraryID,
      feedName: feed.name || "",
      feedURL: feed.url || "",
      title: this._clean(item.getField("title") || ""),
      abstract,
      url: item.getField("url") || "",
      doi,
      publicationTitle: this._clean(item.getField("publicationTitle") || ""),
      date: this._date(item.getField("date") || item.dateAdded || ""),
      dateAdded: item.dateAdded || "",
      language: item.getField("language") || "",
      authors,
      authorLine:
        authors.length > 3
          ? authors.slice(0, 3).join(", ") + " et al."
          : authors.join(", "),
      metadataThin: abstract.length < 80,
    };
  },

  _clean(value) {
    return String(value || "")
      .replace(/<[^>]+>/g, " ")
      .replace(/&amp;/g, "&")
      .replace(/&lt;/g, "<")
      .replace(/&gt;/g, ">")
      .replace(/\s+/g, " ")
      .trim();
  },

  _date(raw) {
    const m = String(raw || "").match(/(\d{4}-\d{2}-\d{2})/);
    return m ? m[1] : String(raw || "").trim();
  },

  async listFeedItems(onProgress) {
    if (!Zotero.Feeds || typeof Zotero.Feeds.getAll !== "function") {
      throw new Error("Zotero.Feeds is unavailable in this Zotero build");
    }
    const feeds = Zotero.Feeds.getAll();
    const rows = [];
    const totalFeeds = feeds.length;
    if (onProgress) {
      await onProgress({
        phase: "feeds",
        current: 0,
        total: totalFeeds || 1,
        detail: this.t("共 " + totalFeeds + " 个订阅", totalFeeds + " feeds"),
      });
    }
    for (let i = 0; i < feeds.length; i++) {
      const feed = feeds[i];
      if (onProgress) {
        await onProgress({
          phase: "feeds",
          current: i + 1,
          total: totalFeeds,
          detail: feed.name || "",
        });
      }
      let items = [];
      try {
        // Zotero.Items.getAll(libraryID, onlyTopLevel, includeDeleted, asIDs)
        // The 4th argument is asIDs — it must stay false or we get numeric IDs.
        items = await Zotero.Items.getAll(feed.libraryID, false, false, false);
      } catch (e) {
        Zotero.debug("RSS Digest: getAll failed for feed " + feed.name + ": " + e);
        continue;
      }
      let n = 0;
      for (let item of items || []) {
        n++;
        if (typeof item === "number" || typeof item === "string") {
          item = await Zotero.Items.getAsync(item);
        }
        if (!item) {
          continue;
        }
        if (typeof item.loadAllData === "function") {
          try {
            await item.loadAllData();
          } catch (e) {}
        }
        if (typeof item.getField !== "function") {
          continue;
        }
        if (typeof item.isFeedItem === "boolean" && !item.isFeedItem) {
          continue;
        }
        rows.push(this.normalizeItem(item, feed));
        if (onProgress && n % 40 === 0) {
          await onProgress({
            phase: "feeds",
            current: i + 1,
            total: totalFeeds,
            detail: (feed.name || "") + " · " + n,
          });
        }
      }
    }
    rows.sort((a, b) => String(b.date).localeCompare(String(a.date)));
    return { feeds, rows };
  },

  _hits(text, keywords) {
    const found = [];
    const hay = text.toLowerCase();
    for (const raw of keywords) {
      const kw = String(raw || "").trim().toLowerCase();
      if (kw && hay.includes(kw)) {
        found.push(raw);
      }
    }
    return found;
  },

  scoreItem(item, profile) {
    const text = [
      item.title,
      item.abstract,
      item.publicationTitle,
      item.feedName,
      item.authors.join(" "),
      item.doi,
    ]
      .join("\n")
      .toLowerCase();
    const include = (profile.include_keywords || []).concat(profile.topics || []);
    const exclude = this._hits(text, profile.exclude_keywords || []);
    if (exclude.length) {
      return {
        item,
        ruleScore: 0,
        skipped: true,
        skipReason: "exclude_keywords",
        reasons: ["exclude: " + exclude.join(", ")],
      };
    }
    const includeHits = this._hits(text, include);
    const configured = include.filter((k) => String(k || "").trim());
    let ruleScore;
    const reasons = [];
    if (!configured.length) {
      ruleScore = 3;
      reasons.push("no include_keywords; keeping item");
    } else if (!includeHits.length) {
      ruleScore = 0;
    } else {
      const unique = [...new Set(includeHits.map((h) => h.toLowerCase()))];
      ruleScore = Math.min(5, 2 + unique.length);
      reasons.push("keywords: " + [...new Set(includeHits)].join(", "));
    }
    const skipped = ruleScore < Number(profile.min_rule_score || 2) && configured.length > 0;
    return {
      item,
      ruleScore,
      llmScore: null,
      skipped,
      skipReason: skipped ? "below_min_rule_score" : "",
      reasons,
      card: null,
    };
  },

  fallbackCard(scored) {
    const item = scored.item;
    const score = scored.llmScore ?? scored.ruleScore;
    const snippet = (item.abstract || item.title || "").slice(0, 280);
    let suggestion = this.t("忽略", "Skip");
    if (score >= 4) {
      suggestion = this.t("精读", "Read closely");
    } else if (score >= 3) {
      suggestion = this.t("扫摘要", "Skim abstract");
    }
    return {
      title_zh: "",
      abstract_zh: "",
      one_liner: (snippet.split(". ")[0] || item.title).slice(0, 160),
      problem: "",
      method: "",
      conclusion: snippet,
      why_relevant: scored.reasons.join("; ") || this.t("规则筛选命中", "Matched rules"),
      suggestion,
    };
  },

  _looksEnglish(text) {
    const s = String(text || "").trim();
    if (s.length < 6) {
      return false;
    }
    const cjk = (s.match(/[\u3400-\u9fff]/g) || []).length;
    if (cjk / s.length >= 0.12) {
      return false;
    }
    return /[A-Za-z]{5,}/.test(s);
  },

  _cardNeedsZh(card) {
    if (!this.isZh()) {
      return false;
    }
    const c = card || {};
    if (!c.title_zh && !c.abstract_zh && !c.one_liner && !c.conclusion) {
      return true;
    }
    if (!c.title_zh || this._looksEnglish(c.title_zh)) {
      return true;
    }
    return [c.one_liner, c.conclusion, c.abstract_zh].some(
      (t) => t && this._looksEnglish(t),
    );
  },

  _normalizeSuggestion(card) {
    if (!card) {
      return;
    }
    const raw = String(card.suggestion || "").toLowerCase();
    if (this.isZh()) {
      if (/精读|close|read closely/.test(raw)) {
        card.suggestion = "精读";
      } else if (/扫|skim/.test(raw)) {
        card.suggestion = "扫摘要";
      } else if (/忽略|skip|ignore/.test(raw)) {
        card.suggestion = "忽略";
      }
    } else if (/精读/.test(raw)) {
      card.suggestion = "Read closely";
    } else if (/扫/.test(raw)) {
      card.suggestion = "Skim abstract";
    } else if (/忽略/.test(raw)) {
      card.suggestion = "Skip";
    }
  },

  _applyCardData(scored, data) {
    const prev = scored.card || {};
    scored.card = {
      title_zh: data.title_zh || data.title || prev.title_zh || "",
      abstract_zh: data.abstract_zh || data.abstract || prev.abstract_zh || "",
      one_liner: data.one_liner || prev.one_liner || "",
      problem: data.problem || prev.problem || "",
      method: data.method || prev.method || "",
      conclusion: data.conclusion || prev.conclusion || "",
      why_relevant: data.why_relevant || data.reason || prev.why_relevant || "",
      suggestion: data.suggestion || prev.suggestion || "",
    };
    this._normalizeSuggestion(scored.card);
  },

  async translateCard(scored) {
    if (!this.isZh() || !this.pref("apiKey", "")) {
      return scored;
    }
    const item = scored.item;
    const card = scored.card || this.fallbackCard(scored);
    try {
      const raw = await this.chatCompletion([
        {
          role: "system",
          content:
            "你把论文卡片译成简体中文。只返回 JSON，不要英文句子。",
        },
        {
          role: "user",
          content:
            "把下面论文信息译成简体中文。只返回 JSON：" +
            '{"title_zh","abstract_zh","one_liner","why_relevant","conclusion","suggestion"}\n' +
            "suggestion 只能是：精读、扫摘要、忽略。\n" +
            "不要把英文原句复制进任何字段。\n" +
            "Title: " +
            item.title +
            "\nAbstract: " +
            (item.abstract || "").slice(0, 2000) +
            "\nOne-liner: " +
            (card.one_liner || "") +
            "\nWhy: " +
            (card.why_relevant || "") +
            "\nConclusion: " +
            (card.conclusion || "") +
            "\nSuggestion: " +
            (card.suggestion || ""),
        },
      ]);
      this._applyCardData(scored, this._extractJSON(raw));
    } catch (e) {
      Zotero.debug("RSS Digest translate failed: " + e);
      scored.card = card;
      this._normalizeSuggestion(scored.card);
    }
    return scored;
  },

  async ensureCardLanguage(scored) {
    scored.card = scored.card || this.fallbackCard(scored);
    this._normalizeSuggestion(scored.card);
    if (this._cardNeedsZh(scored.card)) {
      await this.translateCard(scored);
    }
    return scored;
  },

  async chatCompletion(messages) {
    const base = String(this.pref("apiBase", "https://api.openai.com/v1")).replace(/\/$/, "");
    const key = String(this.pref("apiKey", ""));
    const model = String(this.pref("model", "gpt-4o-mini"));
    if (!key) {
      throw new Error("LLM API key is not set");
    }
    const xhr = await Zotero.HTTP.request("POST", base + "/chat/completions", {
      headers: {
        "Content-Type": "application/json",
        Authorization: "Bearer " + key,
      },
      body: JSON.stringify({
        model,
        temperature: 0.2,
        max_tokens: 1200,
        messages,
      }),
      timeout: 90000,
      successCodes: [200],
    });
    const text = xhr.responseText || xhr.response || "";
    const data = JSON.parse(text);
    return data.choices[0].message.content;
  },

  _extractJSON(text) {
    const fenced = String(text).match(/```(?:json)?\s*([\s\S]*?)\s*```/);
    let raw = fenced ? fenced[1] : String(text).trim();
    try {
      return JSON.parse(raw);
    } catch (e) {
      const start = raw.indexOf("{");
      const end = raw.lastIndexOf("}");
      return JSON.parse(raw.slice(start, end + 1));
    }
  },

  async distillItem(scored, profile) {
    const item = scored.item;
    const zh = this.isZh();
    const lang = zh ? "Simplified Chinese (简体中文)" : "English";
    const topics = (profile.topics || []).join(", ") || "(unspecified)";
    try {
      const raw = await this.chatCompletion([
        {
          role: "system",
          content: zh
            ? "你筛选论文并写中文卡片。只返回 JSON。所有叙述字段必须是简体中文，禁止照抄英文原句。"
            : "You extract structured paper cards. JSON only. Write all narrative fields in English.",
        },
        {
          role: "user",
          content:
            "Screen this RSS paper against a research profile.\n" +
            "Return ONLY JSON: {score, reason, title_zh, abstract_zh, one_liner, problem, method, conclusion, why_relevant, suggestion}\n" +
            "score is 0-5 integer.\n" +
            (zh
              ? "title_zh 和 abstract_zh 必须是中文翻译。one_liner / reason / why_relevant / conclusion / problem / method 必须是简体中文。suggestion 只能是：精读、扫摘要、忽略。\n"
              : "title_zh may repeat the English title. suggestion is Read closely|Skim abstract|Skip.\n") +
            "Write text fields in " +
            lang +
            ".\nResearch topics: " +
            topics +
            "\nTitle: " +
            item.title +
            "\nFeed/Journal: " +
            item.feedName +
            " / " +
            item.publicationTitle +
            "\nAuthors: " +
            item.authorLine +
            "\nDate: " +
            item.date +
            "\nDOI: " +
            item.doi +
            "\nAbstract: " +
            item.abstract.slice(0, 2500) +
            "\nRule hits: " +
            scored.reasons.join("; "),
        },
      ]);
      const data = this._extractJSON(raw);
      scored.llmScore = Math.max(0, Math.min(5, Number(data.score ?? scored.ruleScore)));
      this._applyCardData(scored, data);
      if (data.reason) {
        scored.reasons.push(String(data.reason));
      }
      if (zh && this._cardNeedsZh(scored.card)) {
        await this.translateCard(scored);
      }
    } catch (e) {
      Zotero.debug("RSS Digest LLM failed: " + e);
      scored.card = this.fallbackCard(scored);
      if (zh && this.pref("apiKey", "")) {
        await this.translateCard(scored);
      }
    }
    return scored;
  },

  async clusterItems(related) {
    if (related.length < 3 || !this.pref("apiKey", "")) {
      return [];
    }
    const lang = this.isZh() ? "Chinese" : "English";
    const lines = related
      .slice(0, 30)
      .map((s, i) => `${i + 1}. ${s.item.title} [${s.item.feedName}] score=${s.llmScore ?? s.ruleScore}`);
    try {
      const raw = await this.chatCompletion([
        { role: "system", content: "JSON only." },
        {
          role: "user",
          content:
            "Cluster these papers into 3-7 themes.\nReturn JSON: {\"themes\": [\"theme — one sentence\", ...]}\n" +
            (this.isZh()
              ? "每个 theme 必须是简体中文。\n"
              : "Write each theme in English.\n") +
            "Language: " +
            lang +
            ".\nPapers:\n" +
            lines.join("\n"),
        },
      ]);
      const data = this._extractJSON(raw);
      return (data.themes || []).map(String).filter(Boolean);
    } catch (e) {
      Zotero.debug("RSS Digest cluster failed: " + e);
      return [];
    }
  },

  _onOrAfter(item, start) {
    for (const raw of [item.date, item.dateAdded]) {
      const m = String(raw || "").match(/(\d{4}-\d{2}-\d{2})/);
      if (m) {
        return m[1] >= start;
      }
    }
    return true;
  },

  async scan({ silent, rescan } = {}) {
    this._progressEnabled = !silent;
    const popup = new Zotero.ProgressWindow({ closeOnClick: true });
    popup.changeHeadline("RSS Digest");
    this._scanItemProgress = null;
    if (!silent) {
      popup.show();
      try {
        this._scanItemProgress = new popup.ItemProgress(
          null,
          this.t("正在读取订阅…", "Reading feeds…"),
        );
      } catch (e) {
        popup.addLines([this.t("正在读取订阅…", "Reading feeds…")]);
      }
    }
    await this._reportProgress({
      phase: "feeds",
      current: 0,
      total: 1,
      detail: this.t("正在读取订阅…", "Reading feeds…"),
    });
    const { feeds, rows } = await this.listFeedItems(
      silent ? null : (info) => this._reportProgress(info),
    );
    const state = await this.loadState();
    const seen = new Set(state.seen_guids || []);
    const lookback = Number(this.pref("firstLookbackDays", 7));
    const start = new Date();
    start.setDate(start.getDate() - lookback);
    const startISO = start.toISOString().slice(0, 10);
    let fresh;
    if (rescan || !seen.size) {
      fresh = rows.filter((it) => this._onOrAfter(it, startISO));
    } else {
      fresh = rows.filter((it) => !seen.has(it.guid));
    }

    await this._reportProgress({
      phase: "score",
      current: 1,
      total: 1,
      detail: this.t(
        "新条目 " + fresh.length + " / 共 " + rows.length,
        fresh.length + " new / " + rows.length + " total",
      ),
    });

    const profile = this.profile();
    const kept = [];
    const skipped = [];
    for (const item of fresh) {
      const scored = this.scoreItem(item, profile);
      if (scored.skipped) {
        skipped.push(scored);
      } else {
        kept.push(scored);
      }
    }
    kept.sort((a, b) => b.ruleScore - a.ruleScore);

    const cap = Number(this.pref("llmBatchCap", 30));
    const minLlm = Number(this.pref("minLlmScore", 3));
    const useLLM = Boolean(this.pref("apiKey", ""));
    const related = [];
    if (useLLM && kept.length) {
      const batch = kept.slice(0, cap);
      const overflow = kept.slice(cap);
      for (const scored of overflow) {
        scored.card = this.fallbackCard(scored);
        if (scored.ruleScore >= minLlm) {
          related.push(scored);
        } else {
          scored.skipped = true;
          scored.skipReason = "below_min_llm_score";
          skipped.push(scored);
        }
      }
      for (let i = 0; i < batch.length; i++) {
        const scored = batch[i];
        await this._reportProgress({
          phase: "llm",
          current: i + 1,
          total: batch.length,
          detail: scored.item.title || "",
        });
        await this.distillItem(scored, profile);
        const score = scored.llmScore ?? scored.ruleScore;
        if (score >= minLlm) {
          related.push(scored);
        } else {
          scored.skipped = true;
          scored.skipReason = "below_min_llm_score";
          skipped.push(scored);
        }
      }
    } else {
      for (const scored of kept) {
        scored.card = this.fallbackCard(scored);
        related.push(scored);
      }
    }
    related.sort((a, b) => (b.llmScore ?? b.ruleScore) - (a.llmScore ?? a.ruleScore));
    if (this.isZh() && useLLM && related.length) {
      const need = related.filter((s) => this._cardNeedsZh(s.card || {}));
      for (let i = 0; i < need.length; i++) {
        await this._reportProgress({
          phase: "translate",
          current: i + 1,
          total: need.length,
          detail: need[i].item.title || "",
        });
        await this.ensureCardLanguage(need[i]);
      }
    }
    await this._reportProgress({
      phase: "cluster",
      current: 1,
      total: 1,
      detail: this.t("正在归纳主题…", "Clustering themes…"),
    });
    const themes = await this.clusterItems(related);

    await this._reportProgress({
      phase: "save",
      current: 1,
      total: 1,
      detail: this.t("写入状态…", "Saving state…"),
    });
    const allGuids = rows.map((r) => r.guid);
    state.seen_guids = [...new Set([...(state.seen_guids || []), ...allGuids])].sort();
    state.last_run = new Date().toISOString();
    await this.saveState(state);

    const result = {
      at: state.last_run,
      feedCount: feeds.length,
      ingested: rows.length,
      newCount: fresh.length,
      related,
      skipped,
      themes,
      empty: !fresh.length,
    };
    const keepPrevious =
      !rescan && result.empty && this.lastScan && (this.lastScan.related || []).length;
    if (!keepPrevious) {
      this.lastScan = result;
      await this.persistLastScan(result);
    }
    if (!silent) {
      popup.addLines([
        this.t(
          `新条目 ${result.newCount}，相关 ${related.length}`,
          `${result.newCount} new, ${related.length} relevant`,
        ),
      ]);
      popup.startCloseTimer(4000);
    }
    if (related.length) {
      await this.writeDigestNote(result).catch((e) => Zotero.debug("digest note: " + e));
    }
    return result;
  },

  async ensureCollection() {
    const name = String(this.pref("collectionName", "RSS Digest") || "RSS Digest");
    const libraryID = Zotero.Libraries.userLibraryID;
    const existing = Zotero.Collections.getByLibrary(libraryID, false).find(
      (c) => c.name === name,
    );
    if (existing) {
      return existing;
    }
    const col = new Zotero.Collection();
    col.libraryID = libraryID;
    col.name = name;
    await col.saveTx();
    return col;
  },

  async saveToLibrary(itemID) {
    const feedItem = await Zotero.Items.getAsync(itemID);
    if (!feedItem) {
      throw new Error("Feed item not found: " + itemID);
    }
    const collection = await this.ensureCollection();
    if (typeof feedItem.translate === "function") {
      await feedItem.translate(Zotero.Libraries.userLibraryID, collection.id);
    } else {
      const cloned = feedItem.clone(Zotero.Libraries.userLibraryID);
      cloned.addToCollection(collection.id);
      await cloned.saveTx();
    }
    const scored = (this.lastScan?.related || []).find((s) => s.item.id === itemID);
    const libraryItem = await this._findSavedItem(feedItem);
    if (libraryItem && scored?.card) {
      const note = new Zotero.Item("note");
      note.libraryID = Zotero.Libraries.userLibraryID;
      note.parentID = libraryItem.id;
      note.setNote(this._cardNoteHTML(scored));
      await note.saveTx();
    }
    return libraryItem;
  },

  async _findSavedItem(feedItem) {
    const s = new Zotero.Search();
    s.libraryID = Zotero.Libraries.userLibraryID;
    const doi = feedItem.getField("DOI");
    if (doi) {
      s.addCondition("DOI", "is", doi);
    } else {
      s.addCondition("title", "is", feedItem.getField("title"));
    }
    const ids = await s.search();
    return ids.length ? Zotero.Items.get(ids[ids.length - 1]) : null;
  },

  _cardNoteHTML(scored) {
    const c = scored.card || {};
    const esc = (s) =>
      String(s || "")
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;");
    return (
      "<h2>RSS Digest</h2>" +
      (c.one_liner ? "<p><b>" + esc(c.one_liner) + "</b></p>" : "") +
      (c.why_relevant ? "<p>" + esc(c.why_relevant) + "</p>" : "") +
      (c.conclusion ? "<p>" + esc(c.conclusion) + "</p>" : "") +
      "<p>" +
      esc(c.suggestion || "") +
      " · score " +
      (scored.llmScore ?? scored.ruleScore) +
      "</p>"
    );
  },

  async writeDigestNote(result) {
    const collection = await this.ensureCollection();
    const day = new Date().toISOString().slice(0, 10);
    const title = "RSS Digest · " + day;
    let html = "<h1>" + title + "</h1>";
    html +=
      "<p>" +
      this.t("新条目", "New") +
      ": " +
      result.newCount +
      " · " +
      this.t("相关", "Relevant") +
      ": " +
      result.related.length +
      "</p>";
    if (result.themes.length) {
      html += "<h2>" + this.t("本轮主题", "Themes") + "</h2><ul>";
      for (const theme of result.themes) {
        html += "<li>" + this._esc(theme) + "</li>";
      }
      html += "</ul>";
    }
    html += "<h2>" + this.t("相关文献", "Papers") + "</h2>";
    for (const scored of result.related) {
      const it = scored.item;
      html += "<h3>" + this._esc(it.title) + "</h3><p>";
      html += this._esc(it.feedName);
      if (it.publicationTitle) {
        html += " / " + this._esc(it.publicationTitle);
      }
      html += "<br/>" + this._esc(it.authorLine || "—");
      html += "<br/>" + this._esc(it.date || "");
      if (it.doi) {
        html += "<br/>DOI: " + this._esc(it.doi);
      }
      if (it.url) {
        html += '<br/><a href="' + this._esc(it.url) + '">' + this._esc(it.url) + "</a>";
      }
      html += "</p>";
      if (scored.card) {
        html += "<p>" + this._esc(scored.card.one_liner || scored.card.conclusion || "") + "</p>";
      }
    }
    const note = new Zotero.Item("note");
    note.libraryID = Zotero.Libraries.userLibraryID;
    note.setNote(html);
    note.addToCollection(collection.id);
    await note.saveTx();
  },

  _esc(s) {
    return String(s || "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  },

  async exportMarkdown() {
    this.openOverlay("results");
    const result = this.lastScan;
    if (!result || !(result.related || []).length) {
      this._setOverlayStatus(
        this.t("没有可导出的结果，请先扫描。", "No results to export. Scan first."),
      );
      return;
    }
    const md = this._resultToMarkdown(result);
    const day = String(result.at || new Date().toISOString()).slice(0, 10);
    const filename = "rss-digest-" + day + ".md";
    try {
      const path = await this._pickSavePath(filename);
      if (!path) {
        this._setOverlayStatus(this.t("已取消导出。", "Export cancelled."));
        return;
      }
      await IOUtils.writeUTF8(path, md);
      this._setOverlayStatus(this.t("已导出：" + path, "Exported: " + path));
    } catch (e) {
      this._setOverlayStatus(String(e));
      Zotero.logError(e);
    }
  },

  async _pickSavePath(filename) {
    const win = Zotero.getMainWindow();
    try {
      const { FilePicker } = ChromeUtils.importESModule(
        "chrome://zotero/content/modules/filePicker.mjs",
      );
      const fp = new FilePicker();
      fp.init(win, this.t("导出 Markdown", "Export Markdown"), fp.modeSave);
      fp.appendFilter("Markdown", "*.md");
      fp.defaultString = filename;
      const rv = await fp.show();
      if (rv === fp.returnOK || rv === fp.returnReplace) {
        const file = fp.file;
        return typeof file === "string" ? file : file.path;
      }
      return null;
    } catch (e) {
      Zotero.debug("RSS Digest FilePicker: " + e);
    }
    try {
      const nsIFilePicker = Components.interfaces.nsIFilePicker;
      const fp = Components.classes["@mozilla.org/filepicker;1"].createInstance(nsIFilePicker);
      const ctx = win.browsingContext || win;
      fp.init(ctx, this.t("导出 Markdown", "Export Markdown"), nsIFilePicker.modeSave);
      fp.appendFilter("Markdown", "*.md");
      fp.defaultString = filename;
      const rv = await new Promise((resolve) => fp.open(resolve));
      if (rv === nsIFilePicker.returnOK || rv === nsIFilePicker.returnReplace) {
        return fp.file.path;
      }
      return null;
    } catch (e) {
      Zotero.debug("RSS Digest nsIFilePicker: " + e);
    }
    return PathUtils.join(Zotero.DataDirectory.dir, filename);
  },

  _resultToMarkdown(result) {
    const zh = this.isZh();
    const L = (a, b) => (zh ? a : b);
    const lines = [];
    const day = String(result.at || new Date().toISOString()).slice(0, 10);
    lines.push("# RSS Digest · " + day);
    lines.push("");
    lines.push("- " + L("订阅", "Feeds") + ": " + (result.feedCount || 0));
    lines.push("- " + L("新条目", "New") + ": " + (result.newCount || 0));
    lines.push("- " + L("相关", "Relevant") + ": " + (result.related || []).length);
    lines.push("- " + L("跳过", "Skipped") + ": " + (result.skippedCount || (result.skipped || []).length || 0));
    lines.push("");
    if (result.themes?.length) {
      lines.push("## " + L("本轮主题", "Themes"));
      lines.push("");
      for (const theme of result.themes) {
        lines.push("- " + theme);
      }
      lines.push("");
    }
    lines.push("## " + L("相关文献", "Papers"));
    lines.push("");
    (result.related || []).forEach((scored, i) => {
      const it = scored.item || {};
      const card = scored.card || {};
      const title = card.title_zh || it.title || "(untitled)";
      lines.push("### " + (i + 1) + ". " + title);
      lines.push("");
      if (card.title_zh && it.title && card.title_zh !== it.title) {
        lines.push("- **" + L("原标题", "Original title") + ":** " + it.title);
      }
      const venue = [it.feedName, it.publicationTitle].filter(Boolean).join(" / ");
      if (venue) {
        lines.push("- **" + L("订阅", "Feed") + ":** " + venue);
      }
      if (it.authorLine) {
        lines.push("- **" + L("作者", "Authors") + ":** " + it.authorLine);
      }
      if (it.date || it.dateAdded) {
        lines.push("- **" + L("日期", "Date") + ":** " + (it.date || it.dateAdded));
      }
      if (it.doi) {
        lines.push("- **DOI:** " + it.doi);
      }
      if (it.url) {
        lines.push("- **" + L("链接", "URL") + ":** " + it.url);
      }
      lines.push(
        "- **Score:** " +
          (scored.llmScore ?? scored.ruleScore) +
          (card.suggestion ? " · " + card.suggestion : ""),
      );
      lines.push("");
      if (card.one_liner) {
        lines.push("**" + L("一句话", "One-liner") + ":** " + card.one_liner);
        lines.push("");
      }
      if (card.why_relevant) {
        lines.push("**" + L("为何相关", "Why relevant") + ":** " + card.why_relevant);
        lines.push("");
      }
      if (card.conclusion) {
        lines.push("**" + L("要点", "Takeaway") + ":** " + card.conclusion);
        lines.push("");
      }
      const abs = card.abstract_zh || it.abstract;
      if (abs) {
        lines.push("**" + L("摘要", "Abstract") + ":**");
        lines.push("");
        lines.push(abs);
        lines.push("");
      }
      if (card.abstract_zh && it.abstract && card.abstract_zh !== it.abstract) {
        lines.push("<details><summary>" + L("原文摘要", "Original abstract") + "</summary>");
        lines.push("");
        lines.push(it.abstract);
        lines.push("");
        lines.push("</details>");
        lines.push("");
      }
    });
    return lines.join("\n");
  },

  async testLLM() {
    const text = await this.chatCompletion([
      { role: "user", content: 'Reply with JSON {"ok": true} and nothing else.' },
    ]);
    return this._extractJSON(text);
  },
};
