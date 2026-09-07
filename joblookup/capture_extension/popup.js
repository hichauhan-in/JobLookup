const address = document.querySelector("#origin");
const button = document.querySelector("#capture");
const status = document.querySelector("#status");
try {
  const defaults = await fetch(chrome.runtime.getURL("settings.json")).then((response) => response.json());
  const saved = await chrome.storage.local.get("joblookupOrigin");
  address.value = saved.joblookupOrigin || defaults.origin;
} catch {
  status.textContent = "Workspace address can be set below.";
}
button.addEventListener("click", async () => {
  button.disabled = true;
  try {
    const origin = new URL(address.value);
    if (!["http:", "https:"].includes(origin.protocol) || !["127.0.0.1", "localhost", "[::1]"].includes(origin.hostname) || origin.username || origin.password) {
      throw new Error("Use the address of your local JobLookup workspace.");
    }
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    if (!tab?.id || !/^https?:\/\//.test(tab.url || "")) throw new Error("Open a job posting in a web tab first.");
    const [{ result }] = await chrome.scripting.executeScript({
      target: { tabId: tab.id },
      func: () => {
        const scripts = [...document.querySelectorAll('script[type="application/ld+json"]')].slice(0, 8).map((element) => `<script type="application/ld+json">${element.textContent.slice(0, 25000)}</script>`).join("").slice(0, 120000);
        const selected = window.getSelection()?.toString();
        return { format: "joblookup-capture-v1", url: location.href, title: document.title, html: scripts, text: (selected || document.querySelector("main")?.innerText || document.body.innerText).slice(0, 40000) };
      },
    });
    await chrome.storage.local.set({ joblookupOrigin: origin.origin });
    await chrome.tabs.create({ url: `${origin.origin}/#/capture?packet=${encodeURIComponent(JSON.stringify(result))}` });
    window.close();
  } catch (error) {
    status.textContent = error instanceof Error ? error.message : "Capture failed.";
    button.disabled = false;
  }
});