// Generic client-side search for a server-rendered list. Filters the items
// inside #item-list (each carrying a data-search string) by the #list-search
// box. Matches per-word and within words: "el smith" matches "michael w. smith"
// (every whitespace-separated term must appear somewhere). Debounced so it
// doesn't run on every keystroke. Pure DOM filtering, no network calls.
(function () {
  "use strict";

  var search = document.getElementById("list-search");
  var list = document.getElementById("item-list");
  if (!search || !list) return;

  var items = Array.prototype.slice.call(list.querySelectorAll("[data-search]"));

  function tokenize(q) {
    return q.trim().toLowerCase().split(/\s+/).filter(Boolean);
  }

  function apply() {
    var tokens = tokenize(search.value);
    items.forEach(function (el) {
      var hay = el.getAttribute("data-search") || "";
      var show = true;
      for (var i = 0; i < tokens.length; i++) {
        if (hay.indexOf(tokens[i]) === -1) {
          show = false;
          break;
        }
      }
      el.hidden = !show;
    });
  }

  var timer;
  search.addEventListener("input", function () {
    clearTimeout(timer);
    timer = setTimeout(apply, 200);
  });
})();
