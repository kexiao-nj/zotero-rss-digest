var RSSDigestWindow = {
  async init() {
    document.getElementById("btn-scan").addEventListener("command", () => this.scan());
      document.getElementById("btn-prefs").addEventListener("command", () => {
        Zotero.RSSDigest.openPrefsWindow();
      });
    if (Zotero.RSSDigest?.lastScan) {
      this.render(Zotero.RSSDigest.lastScan);
    } else {
      this.setStatus(Zotero.RSSDigest.t("点击「立即扫描」读取订阅", "Click Scan now to read feeds"));
    }
  },

  setStatus(text) {
    document.getElementById("status").value = text;
  },

  async scan() {
    this.setStatus(Zotero.RSSDigest.t("扫描中…", "Scanning…"));
    try {
      const result = await Zotero.RSSDigest.scan({ silent: false });
      this.render(result);
    } catch (e) {
      this.setStatus(String(e));
      Zotero.logError(e);
    }
  },

  render(result) {
    const zh = Zotero.RSSDigest.isZh();
    const summary = document.getElementById("summary");
    const cards = document.getElementById("cards");
    if (!result || result.empty) {
      summary.textContent = "";
      cards.innerHTML =
        '<div class="empty">' +
        (zh ? "没有新的相关条目。" : "No new relevant items.") +
        "</div>";
      this.setStatus(zh ? "无新条目" : "No new items");
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
        result.themes.map((t) => this.esc(t)).join(" · ") +
        "</div>";
    }
    summary.innerHTML = head;
    cards.innerHTML = "";
    for (const scored of result.related) {
      cards.appendChild(this._card(scored, zh));
    }
    this.setStatus(zh ? "扫描完成" : "Scan complete");
  },

  _card(scored, zh) {
    const it = scored.item;
    const card = scored.card || {};
    const el = document.createElementNS("http://www.w3.org/1999/xhtml", "div");
    el.className = "card";
    const origBits = [
      this.row(zh ? "订阅" : "Feed", it.feedName + (it.publicationTitle ? " / " + it.publicationTitle : "")),
      this.row(zh ? "作者" : "Authors", it.authorLine || "—"),
      this.row(zh ? "日期" : "Date", it.date || it.dateAdded || "—"),
      it.doi ? this.row("DOI", it.doi) : "",
      it.url ? this.row(zh ? "链接" : "URL", `<a href="${this.esc(it.url)}">${this.esc(it.url)}</a>`, true) : "",
      this.row(zh ? "摘要" : "Abstract", it.abstract || "—"),
    ].join("");
    const aiBits = [
      card.one_liner ? this.row(zh ? "一句话" : "One-liner", card.one_liner) : "",
      card.why_relevant ? this.row(zh ? "为何相关" : "Why relevant", card.why_relevant) : "",
      card.conclusion ? this.row(zh ? "要点" : "Takeaway", card.conclusion) : "",
      this.row(zh ? "建议" : "Suggestion", card.suggestion || "—"),
      this.row("Score", String(scored.llmScore ?? scored.ruleScore)),
    ].join("");
    el.innerHTML =
      `<h3>${this.esc(it.title || "(untitled)")}</h3>` +
      `<div class="orig">${origBits}</div>` +
      `<div class="ai">${aiBits}</div>` +
      `<div class="actions">
        <button type="button" class="save">${zh ? "添加到我的文库" : "Add to My Library"}</button>
        <span class="saved"></span>
      </div>`;
    el.querySelector(".save").addEventListener("click", async (ev) => {
      const btn = ev.currentTarget;
      btn.disabled = true;
      try {
        await Zotero.RSSDigest.saveToLibrary(it.id);
        el.querySelector(".saved").textContent = zh ? "已保存" : "Saved";
      } catch (e) {
        el.querySelector(".saved").textContent = String(e);
        btn.disabled = false;
      }
    });
    return el;
  },

  row(label, value, html) {
    return (
      `<div class="meta"><span class="label">${this.esc(label)}: </span>` +
      (html ? value : this.esc(value)) +
      "</div>"
    );
  },

  esc(s) {
    return String(s || "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  },
};

