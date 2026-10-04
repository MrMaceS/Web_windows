/* phone-mask.js — русская маска +7 (XXX) XXX-XX-XX.
   Только помогает вводу; нормализацию номера и итоговую проверку делает сервер. */
(function () {
  "use strict";

  const digitsOf = (value) => value.replace(/\D/g, "");

  // Приводит набор цифр к виду «7XXXXXXXXXX» (8 → 7, отсутствующая 7 добавляется).
  function normalize(digits) {
    if (!digits) return "";
    if (digits[0] === "8") digits = "7" + digits.slice(1);
    else if (digits[0] !== "7") digits = "7" + digits;
    return digits.slice(0, 11);
  }

  function format(digits) {
    if (!digits) return "";
    const d = digits.slice(1);
    let out = "+7";
    if (d.length) out += " (" + d.slice(0, 3);
    if (d.length >= 3) out += ")";
    if (d.length > 3) out += " " + d.slice(3, 6);
    if (d.length > 6) out += "-" + d.slice(6, 8);
    if (d.length > 8) out += "-" + d.slice(8, 10);
    return out;
  }

  function caretAfterDigits(formatted, count) {
    if (count <= 0) return 0;
    let seen = 0;
    for (let i = 0; i < formatted.length; i++) {
      if (/\d/.test(formatted[i])) seen++;
      if (seen === count) return i + 1;
    }
    return formatted.length;
  }

  function bind(input) {
    let previous = "";

    input.addEventListener("input", (e) => {
      const raw = input.value;
      const caret = input.selectionStart == null ? raw.length : input.selectionStart;
      const atEnd = caret >= raw.length;
      let digits = digitsOf(raw);
      let digitsBeforeCaret = digitsOf(raw.slice(0, caret)).length;

      // Backspace по символу маски ")", " " или "-" ничего не удалял бы — убираем цифру слева от каретки.
      const isBackspace = e.inputType === "deleteContentBackward";
      if (isBackspace && digits === digitsOf(previous) && digitsBeforeCaret > 0) {
        digits = digits.slice(0, digitsBeforeCaret - 1) + digits.slice(digitsBeforeCaret);
        digitsBeforeCaret -= 1;
      }

      const startsWithCountryCode = digits[0] === "7" || digits[0] === "8";
      digits = normalize(digits);
      if (digits && !startsWithCountryCode) digitsBeforeCaret += 1; // добавили «7» в начало

      const formatted = format(digits);
      input.value = formatted;
      previous = formatted;

      if (!atEnd || isBackspace) {
        const pos = caretAfterDigits(formatted, digitsBeforeCaret);
        input.setSelectionRange(pos, pos);
      }
    });

    // Пустая «заготовка» из одной «+7» не должна считаться введённым номером.
    input.addEventListener("blur", () => {
      if (digitsOf(input.value).length <= 1) {
        input.value = "";
        previous = "";
      }
    });
  }

  function init() {
    document.querySelectorAll(".js-phone-mask").forEach(bind);
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init);
  else init();
})();
