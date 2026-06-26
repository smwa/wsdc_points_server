// Client-side dancer list. The full dancer set (id + name, already sorted by id
// descending) is embedded in the page as JSON, but only a chunk is rendered at
// a time — more cards are appended as you scroll (so 26k rows don't all hit the
// DOM at once). Search is per-word and within words ("el smith" matches
// "michael w. smith") and debounced.
(function () {
  "use strict";

  var dataEl = document.getElementById("dancers-data");
  var list = document.getElementById("item-list");
  var search = document.getElementById("list-search");
  var sentinel = document.getElementById("list-sentinel");
  var status = document.getElementById("list-status");
  if (!dataEl || !list) return;

  // [[id, name], ...] -> entries with a precomputed lowercase haystack.
  var entries = JSON.parse(dataEl.textContent).map(function (d) {
    return { id: d[0], name: d[1], hay: (d[1] + " #" + d[0]).toLowerCase() };
  });

  var CHUNK = 100;
  var filtered = entries;
  var rendered = 0;

  function tokenize(q) {
    return q.trim().toLowerCase().split(/\s+/).filter(Boolean);
  }
  function matches(tokens, hay) {
    for (var i = 0; i < tokens.length; i++) {
      if (hay.indexOf(tokens[i]) === -1) return false;
    }
    return true;
  }

  function updateStatus() {
    if (status) {
      status.textContent =
        "Showing " + rendered.toLocaleString("en") +
        " of " + filtered.length.toLocaleString("en") + " dancers";
    }
  }

  function renderMore() {
    var frag = document.createDocumentFragment();
    var end = Math.min(rendered + CHUNK, filtered.length);
    for (var i = rendered; i < end; i++) {
      var e = filtered[i];
      var li = document.createElement("li");
      li.className = "card";
      var a = document.createElement("a");
      a.href = "/dancer/" + e.id;
      a.textContent = e.name;
      var meta = document.createElement("span");
      meta.className = "card-meta";
      meta.textContent = " #" + e.id;
      li.appendChild(a);
      li.appendChild(meta);
      frag.appendChild(li);
    }
    list.appendChild(frag);
    rendered = end;
    updateStatus();
    // Keep filling while the page isn't scrollable yet (so the observer can fire).
    if (
      rendered < filtered.length &&
      document.documentElement.scrollHeight <= window.innerHeight
    ) {
      renderMore();
    }
  }

  function reset() {
    list.innerHTML = "";
    rendered = 0;
    renderMore();
  }

  reset();

  if (sentinel && "IntersectionObserver" in window) {
    new IntersectionObserver(
      function (observed) {
        observed.forEach(function (entry) {
          if (entry.isIntersecting && rendered < filtered.length) renderMore();
        });
      },
      { rootMargin: "600px" }
    ).observe(sentinel);
  }

  if (search) {
    var timer;
    search.addEventListener("input", function () {
      clearTimeout(timer);
      timer = setTimeout(function () {
        var tokens = tokenize(search.value);
        filtered = tokens.length
          ? entries.filter(function (e) {
              return matches(tokens, e.hay);
            })
          : entries;
        reset();
      }, 200);
    });
  }
})();
