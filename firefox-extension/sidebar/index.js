const DEFAULT_BASE_URL = "https://noscadeaux.fr";

const elements = {
  account: document.querySelector("#account"),
  connect: document.querySelector("#connect"),
  refresh: document.querySelector("#refresh"),
  disconnect: document.querySelector("#disconnect"),
  settings: document.querySelector("#settings"),
  notice: document.querySelector("#notice"),
  form: document.querySelector("#product-form"),
  title: document.querySelector("#title"),
  url: document.querySelector("#url"),
  imageUrl: document.querySelector("#image-url"),
  imageFrame: document.querySelector("#image-frame"),
  productImage: document.querySelector("#product-image"),
  price: document.querySelector("#price"),
  currency: document.querySelector("#currency"),
  titleCandidates: document.querySelector("#title-candidates"),
  imageCandidates: document.querySelector("#image-candidates"),
  priceCandidates: document.querySelector("#price-candidates"),
  groups: document.querySelector("#groups"),
  groupList: document.querySelector("#group-list"),
  submit: document.querySelector("#submit"),
  success: document.querySelector("#success"),
  openList: document.querySelector("#open-list")
};

let baseUrl = DEFAULT_BASE_URL;
let accessToken = null;
let currentUser = null;
let currentWindowId = null;

await initialize();

async function initialize() {
  const settings = await browser.storage.local.get(["apiBaseUrl", "accessToken"]);
  baseUrl = normalizeBaseUrl(settings.apiBaseUrl || DEFAULT_BASE_URL);
  accessToken = settings.accessToken || null;
  currentWindowId = (await browser.windows.getCurrent()).id;

  await loadCapture();
  if (accessToken) await loadAccount();

  browser.storage.onChanged.addListener((changes, area) => {
    if (area === "session") {
      const change = changes[`capture:${currentWindowId}`];
      if (change?.newValue) renderCapture(change.newValue);
    }
    if (area === "local") {
      if (changes.apiBaseUrl?.newValue) baseUrl = normalizeBaseUrl(changes.apiBaseUrl.newValue);
      if (changes.accessToken) {
        accessToken = changes.accessToken.newValue || null;
        if (!accessToken) renderDisconnected();
      }
    }
  });
}

async function loadCapture() {
  const key = `capture:${currentWindowId}`;
  const stored = await browser.storage.session.get(key);
  if (stored[key]) renderCapture(stored[key]);
}

function renderCapture(capture) {
  elements.success.hidden = true;
  if (capture.status === "loading") {
    showNotice("Extracting product information…");
    elements.form.hidden = true;
    return;
  }
  if (capture.status === "error") {
    showNotice(capture.message, true);
    elements.form.hidden = true;
    return;
  }

  const product = capture.product;
  elements.title.value = product.title || "";
  elements.url.value = product.url || "";
  elements.imageUrl.value = product.imageUrl || "";
  elements.price.value = product.price || "";
  elements.currency.value = product.currency || "EUR";
  fillDatalist(elements.titleCandidates, product.candidates?.titles?.map((item) => item.value));
  fillDatalist(elements.imageCandidates, product.candidates?.images?.map((item) => item.value));
  fillDatalist(
    elements.priceCandidates,
    product.candidates?.prices?.map((item) => item.value)
  );
  updateImage();
  elements.form.hidden = false;
  showNotice(accessToken ? "Review the extracted information before adding." : "Connect to add this product.");
}

function fillDatalist(element, values = []) {
  element.replaceChildren(...[...new Set(values)].map((value) => {
    const option = document.createElement("option");
    option.value = value;
    return option;
  }));
}

function updateImage() {
  const value = elements.imageUrl.value.trim();
  if (!value) {
    elements.imageFrame.hidden = true;
    elements.productImage.removeAttribute("src");
    return;
  }
  elements.productImage.src = value;
  elements.productImage.referrerPolicy = "no-referrer";
  elements.imageFrame.hidden = false;
}

async function loadAccount() {
  try {
    const data = await api("/api/extension/me/");
    currentUser = data.user;
    elements.account.textContent = data.user.nickname;
    elements.connect.hidden = true;
    elements.disconnect.hidden = false;
    renderGroups(data.groups);
  } catch (error) {
    if (error.status === 401) await clearToken();
    showNotice(error.message, true);
  }
}

function renderGroups(groups) {
  elements.groupList.replaceChildren(...groups.map((group) => {
    const label = document.createElement("label");
    label.className = "group-option";
    const checkbox = document.createElement("input");
    checkbox.type = "checkbox";
    checkbox.name = "visible_in";
    checkbox.value = String(group.id);
    label.append(checkbox, document.createTextNode(group.name));
    return label;
  }));
  elements.groups.hidden = groups.length === 0;
}

elements.connect.addEventListener("click", async () => {
  elements.connect.disabled = true;
  try {
    await ensureServerPermission();
    const verifier = randomUrlSafe(64);
    const challenge = await sha256UrlSafe(verifier);
    const state = randomUrlSafe(24);
    const redirectUri = browser.identity.getRedirectURL();
    const authorizationUrl = new URL("/extension/authorize/", baseUrl);
    authorizationUrl.searchParams.set("redirect_uri", redirectUri);
    authorizationUrl.searchParams.set("state", state);
    authorizationUrl.searchParams.set("code_challenge", challenge);

    const result = await browser.identity.launchWebAuthFlow({
      interactive: true,
      url: authorizationUrl.href
    });
    const resultUrl = new URL(result);
    if (resultUrl.searchParams.get("state") !== state) throw new Error("Authorization state mismatch.");
    const code = resultUrl.searchParams.get("code");
    if (!code) throw new Error("The authorization code is missing.");

    const response = await serverFetch("/api/extension/token/", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ code, code_verifier: verifier, redirect_uri: redirectUri })
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || "Could not connect the extension.");
    accessToken = data.access_token;
    await browser.storage.local.set({ accessToken });
    await loadAccount();
    showNotice("Connected. Review the extracted information before adding.");
  } catch (error) {
    showNotice(error.message || "Connection cancelled.", true);
  } finally {
    elements.connect.disabled = false;
  }
});

elements.refresh.addEventListener("click", async () => {
  elements.refresh.disabled = true;
  try {
    const [tab] = await browser.tabs.query({ active: true, currentWindow: true });
    if (!tab?.id) throw new Error("No active page was found.");
    const response = await browser.runtime.sendMessage({
      type: "rescan-product",
      tabId: tab.id,
      windowId: tab.windowId
    });
    if (response?.error) throw new Error(response.error);
  } catch (error) {
    showNotice(error.message || "The page could not be scanned again.", true);
  } finally {
    elements.refresh.disabled = false;
  }
});

elements.form.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!accessToken) {
    showNotice("Connect the extension before adding a product.", true);
    return;
  }
  elements.submit.disabled = true;
  try {
    const data = await api("/api/extension/quick-add/", {
      method: "POST",
      body: JSON.stringify({
        title: elements.title.value,
        url: elements.url.value,
        image_url: elements.imageUrl.value,
        price: elements.price.value,
        currency: elements.currency.value,
        visible_in: [...document.querySelectorAll('input[name="visible_in"]:checked')]
          .map((input) => Number(input.value))
      })
    });
    elements.form.hidden = true;
    elements.notice.hidden = true;
    elements.success.hidden = false;
    elements.openList.dataset.path = data.gift.list_url;
  } catch (error) {
    showNotice(error.message, true);
  } finally {
    elements.submit.disabled = false;
  }
});

elements.imageUrl.addEventListener("change", updateImage);
elements.productImage.addEventListener("error", () => { elements.imageFrame.hidden = true; });
elements.openList.addEventListener("click", () => {
  browser.tabs.create({ url: new URL(elements.openList.dataset.path, baseUrl).href });
});
elements.settings.addEventListener("click", () => browser.runtime.openOptionsPage());
elements.disconnect.addEventListener("click", async () => {
  try {
    await api("/api/extension/revoke/", { method: "POST", body: "{}" });
  } catch {
    // Local disconnection must still work when the server is unavailable.
  }
  await clearToken();
  showNotice("Disconnected.");
});

async function api(path, options = {}) {
  const response = await serverFetch(path, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${accessToken}`,
      ...(options.headers || {})
    }
  });
  const data = response.status === 204 ? null : await response.json().catch(() => null);
  if (!response.ok) {
    const error = new Error(data?.error || `Request failed (${response.status}).`);
    error.status = response.status;
    throw error;
  }
  return data;
}

async function serverFetch(path, options) {
  try {
    return await fetch(new URL(path, baseUrl), options);
  } catch (error) {
    throw new Error(
      `Cannot reach ${baseUrl}. Check that the server is running and that this origin is listed in manifest.json host_permissions. (${error.message})`
    );
  }
}

async function ensureServerPermission() {
  const url = new URL(baseUrl);
  const originPattern = `${url.protocol}//${url.hostname}/*`;
  const allowed = await browser.permissions.contains({ origins: [originPattern] });
  if (!allowed) {
    throw new Error(
      `${baseUrl} is not granted in Firefox. Add ${originPattern} to manifest.json host_permissions, reload the add-on, and accept the permission.`
    );
  }
}

async function clearToken() {
  accessToken = null;
  currentUser = null;
  await browser.storage.local.remove("accessToken");
  renderDisconnected();
}

function renderDisconnected() {
  elements.account.textContent = "Not connected";
  elements.connect.hidden = false;
  elements.disconnect.hidden = true;
  elements.groups.hidden = true;
  elements.groupList.replaceChildren();
}

function showNotice(message, error = false) {
  elements.notice.hidden = false;
  elements.notice.textContent = message;
  elements.notice.classList.toggle("error", error);
}

function normalizeBaseUrl(value) {
  return new URL(value).origin;
}

function randomUrlSafe(length) {
  const bytes = new Uint8Array(length);
  crypto.getRandomValues(bytes);
  return base64Url(bytes);
}

async function sha256UrlSafe(value) {
  const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(value));
  return base64Url(new Uint8Array(digest));
}

function base64Url(bytes) {
  let binary = "";
  for (const byte of bytes) binary += String.fromCodePoint(byte);
  return btoa(binary).replaceAll("+", "-").replaceAll("/", "_").replaceAll("=", "");
}
