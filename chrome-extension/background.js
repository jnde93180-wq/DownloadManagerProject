// Click the extension to send current tab URL to the app
chrome.action.onClicked.addListener((tab) => {
  if (!tab || !tab.url) return;
  fetch("http://127.0.0.1:8765/add", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({url: tab.url})
  }).catch(err => console.error("Failed to send URL to Download Manager:", err));
});
chrome.runtime.onInstalled.addListener(() => {
  chrome.contextMenus.create({
    id: "send-to-dm",
    title: "Send link to Download Manager",
    contexts: ["link"]
  });
});
chrome.contextMenus.onClicked.addListener((info) => {
  if (info.menuItemId === "send-to-dm" && info.linkUrl) {
    fetch("http://127.0.0.1:8765/add", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({url: info.linkUrl})
    }).catch(console.error);
  }
});
