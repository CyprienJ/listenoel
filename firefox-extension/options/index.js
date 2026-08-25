const DEFAULT_BASE_URL = "https://noscadeaux.fr";
const t = (key, substitutions) => browser.i18n.getMessage(key, substitutions);

document.documentElement.lang = browser.i18n.getUILanguage().split("-")[0];
for (const element of document.querySelectorAll("[data-i18n]")) {
  element.textContent = t(element.dataset.i18n);
}
const form = document.querySelector("#settings-form");
const input = document.querySelector("#base-url");
const statusOutput = document.querySelector("#status");

const { apiBaseUrl } = await browser.storage.local.get("apiBaseUrl");
input.value = apiBaseUrl || DEFAULT_BASE_URL;

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  try {
    const url = new URL(input.value);
    if (!["http:", "https:"].includes(url.protocol)) throw new Error(t("useHttpUrl"));
    const origin = url.origin;
    const originPattern = `${url.protocol}//${url.hostname}/*`;
    const allowed = await browser.permissions.request({ origins: [originPattern] });
    await browser.storage.local.set({ apiBaseUrl: origin });
    await browser.storage.local.remove("accessToken");
    input.value = origin;
    statusOutput.textContent = allowed
      ? t("savedReconnect")
      : t("savedPermissionMissing", originPattern);
  } catch (error) {
    statusOutput.textContent = error.message;
  }
});
