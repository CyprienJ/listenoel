const t = (key, substitutions) => browser.i18n.getMessage(key, substitutions);

browser.action.onClicked.addListener(async (tab) => {
  if (!tab.id || !tab.windowId) {
    return;
  }

  const key = `capture:${tab.windowId}`;
  const settingLoadingState = browser.storage.session.set({
    [key]: { status: "loading", tabId: tab.id }
  });

  // Firefox's activeTab grant can disappear during shop redirects. Request access
  // only to this shop so refreshes remain reliable without an all-sites install grant.
  const openingSidebar = browser.sidebarAction.open();
  const requestingPermission = requestTabPermission(tab.url);
  const [, , permissionResult] = await Promise.allSettled([
    openingSidebar,
    settingLoadingState,
    requestingPermission
  ]);

  try {
    if (permissionResult.status === "rejected") throw permissionResult.reason;
    const granted = permissionResult.value;
    if (!granted) {
      throw new Error(t("siteAccessNotGranted"));
    }
    await scanTab(tab, key);
  } catch (error) {
    const message = t("permissionNeeded", error.message || String(error));
    await browser.storage.session.set({
      [key]: { status: "error", tabId: tab.id, message }
    });
  }
});

browser.runtime.onMessage.addListener((message) => {
  if (message?.type !== "rescan-product" || !message.tabId || !message.windowId) {
    return undefined;
  }
  return scanTab({ id: message.tabId, windowId: message.windowId }, `capture:${message.windowId}`);
});

async function scanTab(tab, key) {
  const settingLoadingState = browser.storage.session.set({
    [key]: { status: "loading", tabId: tab.id }
  });

  try {
    // Call executeScript before awaiting anything so activeTab cannot expire first.
    const execution = browser.scripting.executeScript({
      target: { tabId: tab.id, allFrames: false },
      files: ["extractor.js"]
    });
    const [, results] = await Promise.all([settingLoadingState, execution]);
    const injection = results.find((item) => item.frameId === 0) || results[0];
    if (injection?.error) {
      throw new Error(t("extractorFailed", formatInjectionError(injection.error)));
    }
    const product = injection?.result;
    if (product?.extractionError) {
      throw new Error(t("extractorFailed", product.extractionError));
    }
    if (!product?.title || !product?.url) {
      throw new Error(t("noProductInformation"));
    }
    if (!product.detection?.isProduct) {
      throw new Error(t("notProductPage"));
    }
    await browser.storage.session.set({
      [key]: { status: "ready", tabId: tab.id, product }
    });
    return { ok: true };
  } catch (error) {
    await settingLoadingState;
    const message = friendlyError(error);
    await browser.storage.session.set({
      [key]: {
        status: "error",
        tabId: tab.id,
        message
      }
    });
    return { ok: false, error: message };
  }
}

function formatInjectionError(error) {
  if (typeof error === "string") return error;
  return error?.stack || error?.message || JSON.stringify(error) || String(error);
}

function friendlyError(error) {
  const message = String(error?.message || error);
  if (message.includes("Missing host permission") || message.includes("Cannot access")) {
    return t("firefoxBlockedAccess", message);
  }
  return message || t("couldNotExtract");
}

function requestTabPermission(urlValue) {
  try {
    const url = new URL(urlValue);
    if (!["http:", "https:"].includes(url.protocol)) {
      return Promise.reject(new Error(t("unsupportedPage")));
    }
    // Firefox match patterns intentionally omit ports.
    const origin = `${url.protocol}//${url.hostname}/*`;
    return browser.permissions.request({ origins: [origin] });
  } catch (error) {
    return Promise.reject(error);
  }
}
