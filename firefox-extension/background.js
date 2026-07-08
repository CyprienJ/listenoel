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
      throw new Error("Site access was not granted.");
    }
    await scanTab(tab, key);
  } catch (error) {
    const message = `Quick Add needs permission to read this shop page. Click the toolbar button again and choose Allow. Firefox reported: ${error.message || error}`;
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
      throw new Error(`Extractor execution failed: ${formatInjectionError(injection.error)}`);
    }
    const product = injection?.result;
    if (product?.extractionError) {
      throw new Error(`Extractor execution failed: ${product.extractionError}`);
    }
    if (!product?.title || !product?.url) {
      throw new Error("No product information was found on this page.");
    }
    if (!product.detection?.isProduct) {
      throw new Error("This page does not appear to be a product page.");
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
    return `Firefox blocked access to this page. Wait until it has finished loading, then click the Quick Add toolbar button again. Firefox reported: ${message}`;
  }
  return message || "The product could not be extracted.";
}

function requestTabPermission(urlValue) {
  try {
    const url = new URL(urlValue);
    if (!["http:", "https:"].includes(url.protocol)) {
      return Promise.reject(new Error("This type of Firefox page cannot be scanned."));
    }
    // Firefox match patterns intentionally omit ports.
    const origin = `${url.protocol}//${url.hostname}/*`;
    return browser.permissions.request({ origins: [origin] });
  } catch (error) {
    return Promise.reject(error);
  }
}
