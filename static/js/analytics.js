
(function () {
  let metrikaLoaded = false;
  // ID счётчика приходит с сервера в data-ym-id на <html> (inline-скриптов нет — строгий CSP).
  const metrikaId = () => (document.documentElement.dataset.ymId || "").trim();

  function loadYandexMetrika() {
    if (metrikaLoaded) return;
    const counterId = metrikaId();
    if (!counterId) return; // TODO: счётчик не настроен — задайте YANDEX_METRIKA_ID в .env
    metrikaLoaded = true;

    /* eslint-disable */
    (function(m,e,t,r,i,k,a){m[i]=m[i]||function(){(m[i].a=m[i].a||[]).push(arguments)};
    m[i].l=1*new Date();
    k=e.createElement(t),a=e.getElementsByTagName(t)[0],k.async=1,k.src=r,a.parentNode.insertBefore(k,a)})
    (window, document, "script", "https://mc.yandex.ru/metrika/tag.js", "ym");
    /* eslint-enable */

    window.ym(Number(counterId), "init", { clickmap: true, trackLinks: true, accurateTrackBounce: true });
  }

  ["scroll", "click", "touchstart", "mousemove"].forEach((evt) => {
    window.addEventListener(evt, loadYandexMetrika, { once: true, passive: true });
  });

  window.trackEvent = function (name, params) {
    params = params || {};
    if (window.ym && metrikaId()) {
      window.ym(Number(metrikaId()), "reachGoal", name, params);
    }
    window.dataLayer = window.dataLayer || [];
    window.dataLayer.push({ event: name, ...params });
  };

  document.addEventListener("DOMContentLoaded", () => {
    document.querySelectorAll('a[href^="tel:"]').forEach((el) => {
      el.addEventListener("click", () => window.trackEvent("call_click"));
    });
    document.querySelectorAll('a[href*="wa.me"], a[href*="whatsapp"], a[href*="t.me"]').forEach((el) => {
      el.addEventListener("click", () => window.trackEvent("messenger_click", { channel: el.hostname }));
    });
  });
})();
