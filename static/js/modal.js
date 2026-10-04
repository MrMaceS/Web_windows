/* modal.js — нативные <dialog>: открыть/закрыть, backdrop, Escape, возврат фокуса.
   Focus trap обеспечивает сам showModal() (остальная страница становится inert).
   Обработчики делегированные — работают для любых диалогов на любой странице. */
(function () {
  "use strict";

  const LOCK_CLASS = "is-scroll-locked";
  const openers = new WeakMap(); // dialog → элемент, вернувший фокус после закрытия
  let pointerDownTarget = null;

  const openDialogs = () => document.querySelectorAll("dialog[open]");
  const unlockIfIdle = () => {
    if (!openDialogs().length) document.documentElement.classList.remove(LOCK_CLASS);
  };

  function openDialog(dialog, trigger, fromDialog) {
    if (!dialog || dialog.open || typeof dialog.showModal !== "function") return;
    // Если модалку открыли из другой (мобильное меню) — фокус вернём на исходную кнопку.
    openers.set(dialog, (fromDialog && openers.get(fromDialog)) || trigger);
    dialog.showModal();
    document.documentElement.classList.add(LOCK_CLASS);

    // На устройствах с мышью сразу ставим курсор в первое поле; на touch не вызываем клавиатуру.
    if (window.matchMedia("(pointer: fine)").matches) {
      const field = dialog.querySelector("form:not(.hidden) input:not([type=hidden]):not([type=checkbox]):not([tabindex='-1'])");
      if (field) field.focus();
    }
  }

  document.addEventListener("pointerdown", (e) => { pointerDownTarget = e.target; }, true);

  document.addEventListener("click", (e) => {
    const target = e.target;
    if (!(target instanceof Element)) return;

    const closeTrigger = target.closest("[data-close-dialog]");
    const openTrigger = target.closest("[data-open-dialog]");
    let closedDialog = null;

    if (closeTrigger) {
      closedDialog = closeTrigger.closest("dialog");
      if (closedDialog) closedDialog.close();
    }
    if (openTrigger) {
      const dialog = document.getElementById(openTrigger.getAttribute("data-open-dialog"));
      openDialog(dialog, openTrigger, closedDialog);
    }

    // Клик по подложке: и нажатие, и отпускание должны быть на самом <dialog>.
    // (Проверка по координатам ломалась: Enter в поле даёт click с clientX=0 и закрывал окно.)
    if (target instanceof HTMLDialogElement && target.classList.contains("dialog-center") &&
        target.open && pointerDownTarget === target) {
      target.close();
    }
    pointerDownTarget = null;
    unlockIfIdle();
  });

  // close срабатывает и для Escape, и для close(): снимаем блокировку, сбрасываем форму, возвращаем фокус.
  document.addEventListener("close", (e) => {
    const dialog = e.target;
    if (!(dialog instanceof HTMLDialogElement)) return;
    unlockIfIdle();

    if (window.App) dialog.querySelectorAll("form").forEach(window.App.resetLeadForm);

    if (!openDialogs().length) {
      const opener = openers.get(dialog);
      if (opener && opener.isConnected && typeof opener.focus === "function") opener.focus();
    }
  }, true);

  // Мобильное меню скрыто на lg+ (класс lg:hidden). Если его открыли и растянули окно
  // (поворот планшета, ресайз), закрываем — иначе невидимый modal-диалог оставил бы страницу inert.
  const desktopQuery = window.matchMedia("(min-width: 1024px)");
  const closeMenuOnDesktop = (e) => {
    if (!e.matches) return;
    const menu = document.getElementById("mobile-menu");
    if (menu && menu.open) menu.close();
  };
  if (desktopQuery.addEventListener) desktopQuery.addEventListener("change", closeMenuOnDesktop);
  else if (desktopQuery.addListener) desktopQuery.addListener(closeMenuOnDesktop);
})();
