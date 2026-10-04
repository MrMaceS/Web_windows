/* main.js — общая основа публичного frontend: API-обёртка, формы заявок,
   sticky header / sticky CTA, scroll reveal. Все динамические данные выводятся
   через textContent — innerHTML в проекте не используется. */
(function () {
  "use strict";

  const motionQuery = window.matchMedia("(prefers-reduced-motion: reduce)");
  const isReducedMotion = () => motionQuery.matches;
  const track = (name, params) => window.trackEvent && window.trackEvent(name, params);

  /* ——— Ошибки API: понятные русские сообщения вместо «Failed to fetch» ——— */
  function apiError(kind, message, status) {
    const err = new Error(message);
    err.kind = kind; // network | validation | rate_limit | server | http
    err.status = status || 0;
    return err;
  }

  async function postJson(url, payload, options) {
    let response;
    try {
      response = await fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
        signal: options && options.signal,
      });
    } catch (e) {
      if (e && e.name === "AbortError") throw e;
      throw apiError("network", "Нет соединения с интернетом. Проверьте сеть и попробуйте ещё раз.");
    }

    let data = null;
    try {
      data = await response.json();
    } catch (e) {
      data = null;
    }
    const serverMessage = data && typeof data.message === "string" ? data.message : "";

    if (!response.ok) {
      const s = response.status;
      if (s === 429) throw apiError("rate_limit", serverMessage || "Слишком много запросов. Попробуйте через минуту.", s);
      if (s === 422) throw apiError("validation", serverMessage || "Проверьте правильность заполнения формы.", s);
      if (s >= 500) throw apiError("server", serverMessage || "Сервис временно недоступен. Попробуйте позже или позвоните нам.", s);
      throw apiError("http", serverMessage || "Не удалось выполнить запрос. Попробуйте ещё раз.", s);
    }
    if (data === null) throw apiError("server", "Сервер вернул неожиданный ответ. Попробуйте ещё раз.", response.status);
    return data;
  }

  /* ——— Ошибки полей и состояние кнопки ——— */
  function fieldErrorEl(input) {
    return input.id ? document.getElementById(input.id + "-error") : null;
  }

  function showFieldError(input, message) {
    const el = fieldErrorEl(input);
    if (el) {
      el.textContent = message;
      el.classList.remove("hidden");
    }
    input.setAttribute("aria-invalid", "true");
    if (input.type !== "checkbox") input.classList.add("field-error");
  }

  function clearFieldError(input) {
    const el = fieldErrorEl(input);
    if (el) {
      el.textContent = "";
      el.classList.add("hidden");
    }
    input.removeAttribute("aria-invalid");
    input.classList.remove("field-error");
  }

  function clearFormErrors(form) {
    form.querySelectorAll("input").forEach(clearFieldError);
    const general = form.querySelector(".form-general-error");
    if (general) general.remove();
  }

  function showGeneralError(form, message) {
    let box = form.querySelector(".form-general-error");
    if (!box) {
      box = document.createElement("p");
      box.className = "form-general-error text-sm text-red-700 mt-1";
      box.setAttribute("role", "alert");
      form.appendChild(box);
    }
    box.textContent = message;
  }

  function setBusy(button, busy) {
    const label = button.querySelector("span") || button;
    if (busy) {
      if (!button.dataset.label) button.dataset.label = label.textContent;
      label.textContent = "Отправляем…";
      button.disabled = true;
      button.setAttribute("aria-busy", "true");
    } else {
      label.textContent = button.dataset.label || label.textContent;
      button.disabled = false;
      button.removeAttribute("aria-busy");
    }
  }

  /* Клиентская проверка только для удобства: нормализацию телефона и
     итоговую валидацию по-прежнему делает сервер. */
  function validateContactFields(form) {
    const phone = form.querySelector('input[name="phone"]');
    const consent = form.querySelector('input[name="consent"]');
    let first = null;

    if (phone && (phone.value.match(/\d/g) || []).length < 10) {
      showFieldError(phone, "Введите номер телефона полностью");
      first = first || phone;
    }
    if (consent && !consent.checked) {
      showFieldError(consent, "Подтвердите согласие на обработку данных");
      first = first || consent;
    }
    if (first) first.focus();
    return !first;
  }

  function showSuccess(form, message) {
    form.classList.add("hidden");
    const block = document.getElementById(form.id + "-success");
    if (!block) return;
    const text = block.querySelector(".success-text");
    if (text && message) text.textContent = message;
    block.classList.remove("hidden");
    block.focus({ preventScroll: true });
    form.dataset.done = "1";
  }

  function fillUtmFields(root) {
    const params = new URLSearchParams(window.location.search);
    (root || document).querySelectorAll("form").forEach((form) => {
      ["utm_source", "utm_medium", "utm_campaign"].forEach((field) => {
        const input = form.querySelector('input[name="' + field + '"]');
        if (input) input.value = (params.get(field) || "").slice(0, 100);
      });
    });
  }

  /* После успешной заявки форма в модалке при повторном открытии снова пустая. */
  function resetLeadForm(form) {
    if (form.dataset.done !== "1") return;
    form.reset();
    fillUtmFields(form.parentElement);
    clearFormErrors(form);
    form.classList.remove("hidden");
    const block = document.getElementById(form.id + "-success");
    if (block) block.classList.add("hidden");
    delete form.dataset.done;
  }

  /* ——— Обычные заявки: главная форма, «замерщик», «обратный звонок» ——— */
  function bindLeadForm(form) {
    form.addEventListener("input", (e) => {
      if (e.target instanceof HTMLInputElement) clearFieldError(e.target);
    });
    form.addEventListener("change", (e) => {
      if (e.target instanceof HTMLInputElement) clearFieldError(e.target);
    });

    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      if (form.dataset.busy === "1") return; // защита от повторной отправки

      clearFormErrors(form);
      if (!validateContactFields(form)) return;

      const submitBtn = form.querySelector('button[type="submit"]');
      form.dataset.busy = "1";
      setBusy(submitBtn, true);

      const payload = Object.fromEntries(new FormData(form).entries());
      payload.consent = form.querySelector('input[name="consent"]').checked;
      payload.source = form.dataset.source || "hero_form";
      track("form_submit", { source: payload.source });

      try {
        const result = await postJson("/api/lead", payload);
        showSuccess(form, result.message);
        track("lead_success", { source: payload.source, lead_id: result.lead_id });
      } catch (err) {
        // Введённые поля не очищаем — пользователь может исправить и повторить.
        showGeneralError(form, err.message);
      } finally {
        delete form.dataset.busy;
        setBusy(submitBtn, false);
      }
    });
  }

  /* ——— Sticky header: тень после прокрутки ——— */
  function initHeader() {
    const header = document.querySelector("[data-site-header]");
    if (!header) return;
    let ticking = false;
    const update = () => {
      header.classList.toggle("header-shadow", window.scrollY > 8);
      ticking = false;
    };
    window.addEventListener("scroll", () => {
      if (!ticking) {
        ticking = true;
        window.requestAnimationFrame(update);
      }
    }, { passive: true });
    update();
  }

  /* ——— Sticky CTA (mobile): прячем, пока на экране калькулятор или форма ——— */
  function initStickyCta() {
    const bar = document.querySelector("[data-sticky-cta]");
    const zones = document.querySelectorAll("[data-hide-sticky]");
    if (!bar || !zones.length || !("IntersectionObserver" in window)) return;
    const visible = new Set();
    const observer = new IntersectionObserver((entries) => {
      entries.forEach((entry) => {
        if (entry.isIntersecting) visible.add(entry.target);
        else visible.delete(entry.target);
      });
      bar.dataset.hidden = visible.size > 0 ? "true" : "false";
    }, { threshold: 0.15 });
    zones.forEach((zone) => observer.observe(zone));
  }

  /* ——— Scroll reveal (только opacity/transform — без layout shift) ——— */
  function initReveal() {
    const items = document.querySelectorAll(".reveal");
    if (!items.length) return;
    if (isReducedMotion() || !("IntersectionObserver" in window)) {
      items.forEach((el) => el.classList.add("is-visible"));
      return;
    }
    const observer = new IntersectionObserver((entries) => {
      entries.forEach((entry) => {
        if (entry.isIntersecting) {
          entry.target.classList.add("is-visible");
          observer.unobserve(entry.target);
        }
      });
    }, { threshold: 0.12, rootMargin: "0px 0px -5% 0px" });
    items.forEach((el) => observer.observe(el));
  }

  function initFormViewTracking() {
    if (!("IntersectionObserver" in window)) return;
    const seen = new WeakSet();
    const observer = new IntersectionObserver((entries) => {
      entries.forEach((entry) => {
        if (entry.isIntersecting && !seen.has(entry.target)) {
          seen.add(entry.target);
          track("form_view", { source: entry.target.dataset.source });
        }
      });
    }, { threshold: 0.5 });
    document.querySelectorAll("[data-lead-form]").forEach((f) => observer.observe(f));
  }

  window.App = {
    isReducedMotion, postJson, setBusy, showFieldError, clearFieldError,
    clearFormErrors, showGeneralError, validateContactFields, showSuccess,
    resetLeadForm, fillUtmFields,
  };

  function init() {
    fillUtmFields();
    document.querySelectorAll("[data-lead-form]").forEach(bindLeadForm);
    initHeader();
    initStickyCta();
    initReveal();
    initFormViewTracking();
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init);
  else init();
})();
