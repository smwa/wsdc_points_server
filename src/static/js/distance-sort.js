// "Sort by distance" for the upcoming-events list. Reorders the #item-list
// cards by great-circle distance from the visitor and annotates each with the
// distance. Tries the precise Geolocation API first, then falls back to a
// coarse IP-based lookup (geojs.io) when that's unavailable/denied/times out —
// the same fallback the legacy site used, so it still works when the browser's
// location provider isn't configured (common on Firefox/Linux).
(function () {
  "use strict";

  var button = document.getElementById("sort-distance");
  var list = document.getElementById("item-list");
  if (!button || !list) return;

  var status = document.getElementById("sort-status");
  var cards = Array.prototype.slice.call(list.querySelectorAll(".card"));

  function deg2rad(d) {
    return (d * Math.PI) / 180;
  }
  function distanceKm(lat1, lon1, lat2, lon2) {
    var R = 6371;
    var dLat = deg2rad(lat2 - lat1);
    var dLon = deg2rad(lon2 - lon1);
    var a =
      Math.sin(dLat / 2) * Math.sin(dLat / 2) +
      Math.cos(deg2rad(lat1)) * Math.cos(deg2rad(lat2)) *
        Math.sin(dLon / 2) * Math.sin(dLon / 2);
    return R * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
  }
  function setStatus(msg) {
    if (status) status.textContent = msg;
  }

  function sortFrom(lat, lon, note) {
    cards.forEach(function (card) {
      var clat = parseFloat(card.getAttribute("data-lat"));
      var clon = parseFloat(card.getAttribute("data-lon"));
      var out = card.querySelector(".distance");
      if (isNaN(clat) || isNaN(clon)) {
        card.dataset.distance = "Infinity";
        if (out) out.textContent = "";
        return;
      }
      var km = distanceKm(lat, lon, clat, clon);
      card.dataset.distance = String(km);
      if (out) {
        out.textContent = " · " + Math.round(km * 0.621371).toLocaleString("en") + " mi away";
      }
    });

    cards
      .slice()
      .sort(function (a, b) {
        return parseFloat(a.dataset.distance) - parseFloat(b.dataset.distance);
      })
      .forEach(function (card) {
        list.appendChild(card);
      });

    setStatus("Sorted by distance" + (note || "") + ".");
    button.disabled = false;
  }

  function ipFallback() {
    setStatus("Estimating location from your network…");
    fetch("https://get.geojs.io/v1/ip/geo.json")
      .then(function (r) {
        if (!r.ok) throw new Error("geo lookup failed");
        return r.json();
      })
      .then(function (d) {
        var lat = parseFloat(d.latitude);
        var lon = parseFloat(d.longitude);
        if (isNaN(lat) || isNaN(lon)) throw new Error("no coordinates");
        sortFrom(lat, lon, " (approx. from your network)");
      })
      .catch(function () {
        button.disabled = false;
        setStatus("Couldn't determine your location.");
      });
  }

  button.addEventListener("click", function () {
    button.disabled = true;
    setStatus("Finding your location…");
    if (navigator.geolocation) {
      navigator.geolocation.getCurrentPosition(
        function (pos) {
          sortFrom(pos.coords.latitude, pos.coords.longitude, " from you");
        },
        function () {
          ipFallback();
        },
        { enableHighAccuracy: false, timeout: 8000, maximumAge: 600000 }
      );
    } else {
      ipFallback();
    }
  });
})();
