const measurementId = "G-WTPHWDLQ7K";
const choiceKey = "prawko-analytics-consent-v1";
const choiceLifetime = 180 * 86400 * 1000;
const cookiePath = "/prawko/";
const disableKey = `ga-disable-${measurementId}`;
const denied = {
  analytics_storage: "denied",
  ad_storage: "denied",
  ad_user_data: "denied",
  ad_personalization: "denied",
};
const banner = document.querySelector("#analytics-consent");
const settings = document.querySelector("#analytics-settings");
let started = false;

function storedChoice() {
  try {
    const choice = JSON.parse(localStorage.getItem(choiceKey));
    if (choice?.expires > Date.now() && typeof choice.allowed === "boolean") return choice.allowed;
  } catch { /* Analytics stays off when a choice cannot be read. */ }
  return null;
}

function setAnalytics(allowed) {
  window[disableKey] = !allowed;
  if (!allowed) {
    if (started) window.gtag("consent", "update", denied);
    for (const cookie of document.cookie.split(";")) {
      const name = cookie.trim().split("=", 1)[0];
      if (/^prawko_ga(?:_[a-zA-Z0-9]+)?$/.test(name)) {
        document.cookie = `${name}=; Max-Age=0; Path=${cookiePath}; SameSite=Lax`;
      }
    }
    return;
  }
  const granted = { ...denied, analytics_storage: "granted" };
  if (started) {
    window.gtag("consent", "update", granted);
    return;
  }
  started = true;
  window.dataLayer = window.dataLayer || [];
  window.gtag = function () { window.dataLayer.push(arguments); };
  window.gtag("consent", "default", denied);
  window.gtag("consent", "update", granted);
  window.gtag("js", new Date());
  window.gtag("config", measurementId, {
    allow_google_signals: false,
    allow_ad_personalization_signals: false,
    cookie_prefix: "prawko",
    cookie_domain: "none",
    cookie_path: cookiePath,
    cookie_expires: 90 * 86400,
    cookie_update: false,
  });
  const script = document.createElement("script");
  script.async = true;
  script.src = `https://www.googletagmanager.com/gtag/js?id=${measurementId}`;
  document.head.append(script);
}

function applyChoice(choice) {
  setAnalytics(choice === true);
  banner.hidden = choice !== null;
  settings.setAttribute("aria-expanded", String(!banner.hidden));
}

function choose(allowed) {
  try {
    localStorage.setItem(choiceKey, JSON.stringify({ allowed, expires: Date.now() + choiceLifetime }));
  } catch { /* The choice still applies to the current page. */ }
  applyChoice(allowed);
  settings.focus({ preventScroll: true });
}

settings.hidden = false;
settings.addEventListener("click", () => {
  banner.hidden = !banner.hidden;
  settings.setAttribute("aria-expanded", String(!banner.hidden));
  if (!banner.hidden) banner.querySelector("h2").focus();
});
banner.querySelector("#analytics-accept").addEventListener("click", () => choose(true));
banner.querySelector("#analytics-reject").addEventListener("click", () => choose(false));
window.addEventListener("storage", event => {
  if (event.key === choiceKey || event.key === null) applyChoice(storedChoice());
});
applyChoice(storedChoice());
