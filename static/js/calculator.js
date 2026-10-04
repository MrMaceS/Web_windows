(function () {
  "use strict";

  const widget = document.getElementById("calc-widget");
  const App = window.App;
  if (!widget || !App || widget.dataset.calcInit === "1") return;
  widget.dataset.calcInit = "1";

  const DEFAULTS = { window_type: "Окно", profile_type: "Стандарт (70 мм)", width_mm: 1300, height_mm: 1400, quantity: 1 };
  const LIMITS = { size: [200, 4000], quantity: [1, 50] };
  const RATE_LIMIT_PAUSE_MS = 10000;

  const state = Object.assign({}, DEFAULTS);
  let step = 1;
  let requestSeq = 0;
  let controller = null;
  let countFrame = 0;
  let estimate = null;

  const $ = (selector) => widget.querySelector(selector);
  const $$ = (selector) => Array.from(widget.querySelectorAll(selector));
  const steps = $$("[data-calc-step]");
  const tabs = $$("[data-calc-tab]");
  const backBtn = $("[data-calc-back]");
  const announce = $("#calc-announce");
  const stateBoxes = { loading: $('[data-calc-state="loading"]'), error: $('[data-calc-state="error"]'), result: $('[data-calc-state="result"]') };
  const leadSection = $("#calc-lead-section");
  const retryBtn = $("[data-calc-retry]");
  const inputs = { width_mm: $("#calc-width"), height_mm: $("#calc-height"), quantity: $("#calc-quantity") };
  const summary = {};
  document.querySelectorAll("[data-sum]").forEach((el) => { summary[el.dataset.sum] = el; });

  const track = (name, params) => window.trackEvent && window.trackEvent(name, params);
  const priceFormat = new Intl.NumberFormat("ru-RU");
  const formatPrice = (value) => priceFormat.format(Math.round(value)) + " ₽";

  function say(message) {
    announce.textContent = "";
    window.setTimeout(() => { announce.textContent = message; }, 50);
  }

  function updateSummary() {
    if (summary.type) summary.type.textContent = state.window_type;
    if (summary.profile) summary.profile.textContent = state.profile_type;
    if (summary.size) summary.size.textContent = state.width_mm + " × " + state.height_mm + " мм";
    if (summary.qty) summary.qty.textContent = state.quantity + " шт.";
  }

  /* ——— Шаги ——— */
  function showStep(n, options) {
    step = n;
    steps.forEach((el) => el.classList.toggle("hidden", Number(el.dataset.calcStep) !== n));
    tabs.forEach((tab) => {
      const tabStep = Number(tab.dataset.calcTab);
      if (tabStep === n) tab.setAttribute("aria-current", "step");
      else tab.removeAttribute("aria-current");
      tab.dataset.done = tabStep < n ? "true" : "false";
    });
    backBtn.classList.toggle("hidden", n === 1);
    backBtn.classList.toggle("inline-flex", n !== 1);
    track("calculator_step", { step: n });

    if (options && options.focus) {
      const heading = widget.querySelector('[data-calc-step="' + n + '"] h3');
      if (heading) heading.focus({ preventScroll: true });
      if (widget.getBoundingClientRect().top < 0) {
        widget.scrollIntoView({ block: "start", behavior: App.isReducedMotion() ? "auto" : "smooth" });
      }
    }
  }

  /* ——— Выбор опций (radiogroup с roving tabindex и стрелками) ——— */
  function selectOption(field, button) {
    $$('[data-field="' + field + '"] .calc-option').forEach((opt) => {
      const active = opt === button;
      opt.setAttribute("aria-checked", active ? "true" : "false");
      opt.tabIndex = active ? 0 : -1;
    });
    state[field] = button.dataset.value;
    updateSummary();
  }

  $$("[data-field]").forEach((group) => {
    const field = group.dataset.field;
    const options = Array.from(group.querySelectorAll(".calc-option"));
    options.forEach((btn) => btn.addEventListener("click", () => selectOption(field, btn)));

    group.addEventListener("keydown", (e) => {
      const keys = { ArrowRight: 1, ArrowDown: 1, ArrowLeft: -1, ArrowUp: -1 };
      const current = options.indexOf(document.activeElement);
      if (current === -1) return;
      let next = null;
      if (e.key in keys) next = (current + keys[e.key] + options.length) % options.length;
      else if (e.key === "Home") next = 0;
      else if (e.key === "End") next = options.length - 1;
      if (next === null) return;
      e.preventDefault();
      options[next].focus();
      selectOption(field, options[next]);
    });
  });

  $$("[data-calc-next]").forEach((btn) => btn.addEventListener("click", () => showStep(step + 1, { focus: true })));

  /* ——— Размеры: валидация формата, границы проверяет сервер ——— */
  function validateDimensions() {
    const rules = [
      ["width_mm", "Ширина", LIMITS.size, "мм"],
      ["height_mm", "Высота", LIMITS.size, "мм"],
      ["quantity", "Количество", LIMITS.quantity, "шт"],
    ];
    const values = {};
    let firstInvalid = null;

    rules.forEach(([key, label, range, unit]) => {
      const input = inputs[key];
      App.clearFieldError(input);
      const value = input.value.trim() === "" ? NaN : Number(input.value);
      if (!Number.isInteger(value)) {
        App.showFieldError(input, label + ": укажите целое число");
      } else if (value < range[0] || value > range[1]) {
        App.showFieldError(input, label + ": от " + range[0] + " до " + range[1] + " " + unit);
      } else {
        values[key] = value;
        return;
      }
      firstInvalid = firstInvalid || input;
    });

    if (firstInvalid) {
      firstInvalid.focus();
      return null;
    }
    return values;
  }

  Object.values(inputs).forEach((input) => input.addEventListener("input", () => App.clearFieldError(input)));

  /* ——— Серверный расчёт ——— */
  function setPhase(phase) {
    Object.keys(stateBoxes).forEach((key) => stateBoxes[key].classList.toggle("hidden", key !== phase));
    leadSection.classList.toggle("hidden", phase !== "result");
  }

  function cancelPending() {
    requestSeq += 1; // ответ устаревшего запроса будет проигнорирован
    if (controller) controller.abort();
    controller = null;
    window.cancelAnimationFrame(countFrame);
  }

  function renderPrice(total) {
    const target = $("#calc-price");
    window.cancelAnimationFrame(countFrame);
    // Count-up — только ПОСЛЕ ответа сервера и только если анимации не отключены.
    if (App.isReducedMotion()) {
      target.textContent = formatPrice(total);
      return;
    }
    const started = performance.now();
    const duration = 600;
    const tick = (now) => {
      const progress = Math.min((now - started) / duration, 1);
      const eased = 1 - Math.pow(1 - progress, 3);
      target.textContent = formatPrice(total * eased);
      if (progress < 1) countFrame = window.requestAnimationFrame(tick);
      else target.textContent = formatPrice(total);
    };
    countFrame = window.requestAnimationFrame(tick);
  }

  function renderResult(data) {
    renderPrice(data.total_price);
    if (summary.price) summary.price.textContent = formatPrice(data.total_price);

    const area = Number(data.area_m2);
    $("#calc-area").textContent = Number.isFinite(area)
      ? new Intl.NumberFormat("ru-RU", { maximumFractionDigits: 2 }).format(area) + " м²" : "—";

    const discountRow = $("#calc-discount-row");
    const percent = Number(data.discount_percent);
    const amount = Number(data.discount_amount);
    if (percent > 0 && amount > 0) {
      $("#calc-discount").textContent = percent + "% (−" + formatPrice(amount) + ")";
      discountRow.classList.remove("hidden");
    } else {
      discountRow.classList.add("hidden");
    }
  }

  async function requestEstimate() {
    cancelPending();
    const seq = requestSeq;
    controller = new AbortController();
    estimate = null;
    if (summary.price) summary.price.textContent = "—";
    setPhase("loading");
    say("Считаем стоимость…");

    try {
      const data = await App.postJson("/api/v1/calculator/estimate", {
        window_type: state.window_type,
        profile_type: state.profile_type,
        width_mm: state.width_mm,
        height_mm: state.height_mm,
        quantity: state.quantity,
      }, { signal: controller.signal });
      if (seq !== requestSeq) return;

      if (typeof data.total_price !== "number" || !Number.isFinite(data.total_price)) {
        const bad = new Error("Не удалось получить стоимость. Попробуйте ещё раз.");
        bad.kind = "server";
        throw bad;
      }
      estimate = data;
      renderResult(data);
      setPhase("result");
      say("Предварительная стоимость: " + formatPrice(data.total_price));
      track("calculator_complete", { price: data.total_price });
    } catch (err) {
      if (seq !== requestSeq || (err && err.name === "AbortError")) return;
      $("#calc-error-text").textContent = err.message || "Не удалось рассчитать стоимость.";
      setPhase("error");
      retryBtn.disabled = false;
      if (err.kind === "rate_limit") {
        retryBtn.disabled = true; // не провоцируем ещё один 429
        window.setTimeout(() => { retryBtn.disabled = false; }, RATE_LIMIT_PAUSE_MS);
      }
    } finally {
      if (seq === requestSeq) controller = null;
    }
  }

  $("[data-calc-submit]").addEventListener("click", () => {
    const values = validateDimensions();
    if (!values) return;
    Object.assign(state, values);
    updateSummary();
    showStep(4, { focus: true });
    requestEstimate();
  });

  retryBtn.addEventListener("click", requestEstimate);
  $("[data-calc-edit]").addEventListener("click", () => { cancelPending(); showStep(3, { focus: true }); });

  backBtn.addEventListener("click", () => {
    if (step <= 1) return;
    if (step === 4) cancelPending();
    showStep(step - 1, { focus: true });
  });

  $("[data-calc-restart]").addEventListener("click", () => {
    cancelPending();
    estimate = null;
    Object.assign(state, DEFAULTS);
    $$('[data-field="window_type"] .calc-option').forEach((b) => { if (b.dataset.value === DEFAULTS.window_type) selectOption("window_type", b); });
    $$('[data-field="profile_type"] .calc-option').forEach((b) => { if (b.dataset.value === DEFAULTS.profile_type) selectOption("profile_type", b); });
    inputs.width_mm.value = DEFAULTS.width_mm;
    inputs.height_mm.value = DEFAULTS.height_mm;
    inputs.quantity.value = DEFAULTS.quantity;
    Object.values(inputs).forEach(App.clearFieldError);
    if (summary.price) summary.price.textContent = "—";
    const form = document.getElementById("calc-form");
    if (form) App.resetLeadForm(form);
    showStep(1, { focus: true });
  });

  /* ——— Заявка из калькулятора ——— */
  const calcForm = document.getElementById("calc-form");
  if (calcForm) {
    calcForm.addEventListener("input", (e) => { if (e.target instanceof HTMLInputElement) App.clearFieldError(e.target); });
    calcForm.addEventListener("change", (e) => { if (e.target instanceof HTMLInputElement) App.clearFieldError(e.target); });

    calcForm.addEventListener("submit", async (e) => {
      e.preventDefault();
      if (calcForm.dataset.busy === "1" || !estimate) return; // без расчёта заявки нет; двойной submit блокируем

      App.clearFormErrors(calcForm);
      if (!App.validateContactFields(calcForm)) return;

      const submitBtn = calcForm.querySelector('button[type="submit"]');
      calcForm.dataset.busy = "1";
      App.setBusy(submitBtn, true);

      // Цену НЕ отправляем: сервер пересчитывает её сам по параметрам.
      const payload = Object.fromEntries(new FormData(calcForm).entries());
      payload.consent = calcForm.querySelector('input[name="consent"]').checked;
      payload.window_type = state.window_type;
      payload.profile_type = state.profile_type;
      payload.width_mm = state.width_mm;
      payload.height_mm = state.height_mm;
      payload.quantity = state.quantity;

      try {
        const result = await App.postJson("/api/calculator-lead", payload);
        App.showSuccess(calcForm, result.message);
        track("lead_success", { source: "calculator", lead_id: result.lead_id });
      } catch (err) {
        App.showGeneralError(calcForm, err.message);
      } finally {
        delete calcForm.dataset.busy;
        App.setBusy(submitBtn, false);
      }
    });
  }

  /* ——— Предзаполнение из каталога: принимаем только значения, которые есть среди опций ——— */
  function applyQueryParams() {
    const params = new URLSearchParams(window.location.search);
    let applied = false;
    ["window_type", "profile_type"].forEach((field) => {
      const raw = params.get(field);
      if (!raw || raw.length > 100) return;
      const match = $$('[data-field="' + field + '"] .calc-option').find((btn) => btn.dataset.value === raw);
      if (match) {
        selectOption(field, match);
        applied = true;
      }
    });
    if (applied) showStep(3);
  }

  updateSummary();
  showStep(1);
  applyQueryParams();
})();
