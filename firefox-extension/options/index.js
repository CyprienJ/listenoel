const DEFAULT_BASE_URL = "https://noscadeaux.fr";
const form = document.querySelector("#settings-form");
const input = document.querySelector("#base-url");
const statusOutput = document.querySelector("#status");

const { apiBaseUrl } = await browser.storage.local.get("apiBaseUrl");
input.value = apiBaseUrl || DEFAULT_BASE_URL;

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  try {
    const url = new URL(input.value);
    if (!["http:", "https:"].includes(url.protocol)) throw new Error("Use an HTTP or HTTPS URL.");
    const origin = url.origin;
    const originPattern = `${url.protocol}//${url.hostname}/*`;
    const allowed = await browser.permissions.request({ origins: [originPattern] });
    await browser.storage.local.set({ apiBaseUrl: origin });
    await browser.storage.local.remove("accessToken");
    input.value = origin;
    statusOutput.textContent = allowed
      ? "Saved. Connect again from the sidebar."
      : `Saved, but Firefox has not granted ${originPattern}. Add it to host_permissions and reload the add-on.`;
  } catch (error) {
    statusOutput.textContent = error.message;
  }
});
