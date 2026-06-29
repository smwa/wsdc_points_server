// Progressive enhancement for the star/unstar forms.
//
// Without JS the forms POST and the server replies 303 back to the current page
// (Post/Redirect/Get). That redirect adds a second history entry for the page
// you're already on, so "back" lands on the duplicate before the list you came
// from. Submitting via fetch instead toggles the star in place with no
// navigation and no extra history entry, so one "back" returns to the list.

(function () {
  "use strict";

  function toggle(form) {
    var button = form.querySelector(".star-button");
    if (!button) return;
    var action = form.getAttribute("action");
    var starred = /\/delete$/.test(action);
    var base = starred ? action.replace(/\/delete$/, "") : action;

    button.disabled = true;
    fetch(action, {
      method: "POST",
      credentials: "same-origin",
      redirect: "manual",
      headers: { "X-Requested-With": "fetch" },
    })
      .then(function (res) {
        // redirect:"manual" yields an opaqueredirect (the 303) on success.
        if (res.type === "opaqueredirect" || res.ok) {
          if (starred) {
            form.setAttribute("action", base);
            button.classList.remove("is-starred");
            button.innerHTML = "&#9734;"; // ☆
            button.title = "Star";
            button.setAttribute("aria-label", "Star this dancer");
          } else {
            form.setAttribute("action", base + "/delete");
            button.classList.add("is-starred");
            button.innerHTML = "&#9733;"; // ★
            button.title = "Unstar";
            button.setAttribute("aria-label", "Unstar this dancer");
          }
        } else {
          form.submit(); // unexpected response: fall back to a real submit
        }
      })
      .catch(function () {
        form.submit(); // network/other failure: fall back to a real submit
      })
      .finally(function () {
        button.disabled = false;
      });
  }

  document.addEventListener("submit", function (event) {
    var form = event.target;
    if (form.classList && form.classList.contains("star-form")) {
      event.preventDefault();
      toggle(form);
    }
  });
})();
