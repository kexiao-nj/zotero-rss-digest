window.addEventListener("load", () => {
  try {
    const root = document.getElementById("rss-digest-prefs");
    Zotero.RSSDigest.initPreferences(root);
  } catch (e) {
    Zotero.logError(e);
  }
});
