/**
 * Zotero 10 bootstrap. Zotero is already initialized when startup() runs.
 * https://www.zotero.org/support/dev/zotero_10_for_developers
 */

var chromeHandle;

function install(data, reason) {}

async function startup({ id, version, resourceURI, rootURI }, reason) {
  var aomStartup = Components.classes[
    "@mozilla.org/addons/addon-manager-startup;1"
  ].getService(Components.interfaces.amIAddonManagerStartup);
  var manifestURI = Services.io.newURI(rootURI + "manifest.json");
  chromeHandle = aomStartup.registerChrome(manifestURI, [
    ["content", "rssdigest", rootURI + "content/"],
    ["locale", "rssdigest", "en-US", rootURI + "locale/en-US/"],
    ["locale", "rssdigest", "zh-CN", rootURI + "locale/zh-CN/"],
  ]);

  Services.scriptloader.loadSubScript(rootURI + "content/rss-digest.js");
  await Zotero.RSSDigest.init({ id, version, rootURI });
}

async function onMainWindowLoad({ window }, reason) {
  await Zotero.RSSDigest?.onMainWindowLoad(window);
}

async function onMainWindowUnload({ window }, reason) {
  if (!window.ZoteroPane) {
    return;
  }
  await Zotero.RSSDigest?.onMainWindowUnload(window);
}

async function shutdown({ id, version, resourceURI, rootURI }, reason) {
  if (reason === APP_SHUTDOWN) {
    return;
  }
  await Zotero.RSSDigest?.shutdown();
  if (chromeHandle) {
    chromeHandle.destruct();
    chromeHandle = null;
  }
}

function uninstall(data, reason) {}
