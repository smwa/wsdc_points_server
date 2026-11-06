// Distance filter for the upcoming-events list: a logarithmic slider (50 to
// 15,000 mi, snapped to 50) that hides cards farther away than its value, and
// annotates each card with its distance. 15,000 mi is the "off" position, since
// nothing on Earth is farther than that.
//
// Location is only requested if the browser already has permission (the filter
// then starts at 500 mi) or once the visitor moves the slider. A failed
// Geolocation lookup falls back to a coarse IP-based one (geojs.io), so it still
// works when the browser's location provider isn't configured (common on
// Firefox/Linux).
//
// The last location is kept in this browser for a week. Firefox and Safari can
// report a one-time "Allow" as "prompt" on the next visit, so without this those
// visitors would look like they never gave access. Revoking access clears it.
//
// Search (list-search.js) toggles the `hidden` attribute on the same cards; this
// uses the separate .too-far class so the two filters don't overwrite each other.
(function () {
  "use strict";

  var wrap = document.getElementById("distance-filter");
  var range = document.getElementById("distance-range");
  var list = document.getElementById("item-list");
  if (!wrap || !range || !list) return;

  var MIN_MILES = 50;
  var MAX_MILES = 15000;
  var SNAP_MILES = 50;
  var DEFAULT_MILES = 500;
  var EARTH_RADIUS_MILES = 3958.8;
  var HINT = "Move the slider to filter by distance from your location.";
  var STORAGE_KEY = "wsdc-last-location";
  var REMEMBER_MS = 7 * 24 * 60 * 60 * 1000;

  var valueOut = document.getElementById("distance-value");
  var status = document.getElementById("distance-status");
  var cards = Array.prototype.slice.call(list.querySelectorAll(".card"));
  var maxPosition = parseInt(range.max, 10);

  var hasLocation = false;
  var approximate = false;
  var locating = false;
  var moved = false;
  var refused = false;

  function milesAt(position) {
    var miles = MIN_MILES * Math.pow(MAX_MILES / MIN_MILES, position / maxPosition);
    return Math.round(miles / SNAP_MILES) * SNAP_MILES;
  }
  function positionFor(miles) {
    return Math.round((maxPosition * Math.log(miles / MIN_MILES)) / Math.log(MAX_MILES / MIN_MILES));
  }
  function formatMiles(miles) {
    return miles.toLocaleString("en") + " mi";
  }
  function deg2rad(d) {
    return (d * Math.PI) / 180;
  }
  function distanceMiles(lat1, lon1, lat2, lon2) {
    var dLat = deg2rad(lat2 - lat1);
    var dLon = deg2rad(lon2 - lon1);
    var a =
      Math.sin(dLat / 2) * Math.sin(dLat / 2) +
      Math.cos(deg2rad(lat1)) * Math.cos(deg2rad(lat2)) *
        Math.sin(dLon / 2) * Math.sin(dLon / 2);
    return EARTH_RADIUS_MILES * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
  }

  function remember(lat, lon, isApproximate) {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify({
        lat: lat, lon: lon, approximate: isApproximate, savedAt: Date.now()
      }));
    } catch (e) {}
  }
  function recall() {
    try {
      var saved = JSON.parse(localStorage.getItem(STORAGE_KEY));
      if (saved && Date.now() - saved.savedAt < REMEMBER_MS) return saved;
    } catch (e) {}
    return null;
  }
  function forget() {
    try {
      localStorage.removeItem(STORAGE_KEY);
    } catch (e) {}
  }

  function showValue() {
    var text = formatMiles(milesAt(range.value));
    valueOut.textContent = text;
    range.setAttribute("aria-valuetext", "Within " + text);
  }

  function applyFilter() {
    var limit = milesAt(range.value);
    var filtering = limit < MAX_MILES;
    var count = 0;
    cards.forEach(function (card) {
      // A card with no coordinates has no data-miles, so it only shows unfiltered.
      var show = !filtering || parseInt(card.dataset.miles, 10) <= limit;
      card.classList.toggle("too-far", !show);
      if (show) count++;
    });

    if (!filtering) {
      status.textContent = approximate
        ? "Distances are approximate, based on your network."
        : "Distances are from your location.";
      return;
    }
    var from = approximate ? " of your approximate location." : " of you.";
    status.textContent =
      (count === 0 ? "No events" : count === 1 ? "1 event" : count.toLocaleString("en") + " events") +
      " within " + formatMiles(limit) + from;
  }

  function useLocation(lat, lon, isApproximate) {
    locating = false;
    hasLocation = true;
    approximate = isApproximate;
    cards.forEach(function (card) {
      var clat = parseFloat(card.getAttribute("data-lat"));
      var clon = parseFloat(card.getAttribute("data-lon"));
      if (isNaN(clat) || isNaN(clon)) return;
      var miles = Math.round(distanceMiles(lat, lon, clat, clon));
      card.dataset.miles = String(miles);
      var out = card.querySelector(".distance");
      if (out) out.textContent = " · " + formatMiles(miles) + " away";
    });
    if (!moved) range.value = positionFor(DEFAULT_MILES);
    showValue();
    applyFilter();
  }

  function giveUp() {
    locating = false;
    if (moved) {
      // Nothing to measure from: don't leave the slider claiming a filter is on.
      moved = false;
      range.value = maxPosition;
      showValue();
      status.textContent = "Couldn't determine your location.";
    } else {
      status.textContent = HINT;
    }
  }

  function ipFallback() {
    status.textContent = "Estimating location from your network…";
    fetch("https://get.geojs.io/v1/ip/geo.json")
      .then(function (r) {
        if (!r.ok) throw new Error("geo lookup failed");
        return r.json();
      })
      .then(function (d) {
        var lat = parseFloat(d.latitude);
        var lon = parseFloat(d.longitude);
        if (isNaN(lat) || isNaN(lon)) throw new Error("no coordinates");
        useLocation(lat, lon, true);
        // Don't carry an estimate into later visits for someone who said no.
        if (!refused) remember(lat, lon, true);
      })
      .catch(giveUp);
  }

  function geolocationFailed(err) {
    refused = !!err && err.code === 1; // GeolocationPositionError.PERMISSION_DENIED
    if (hasLocation) {
      // A refresh of a remembered location failed: keep what's already showing.
      locating = false;
    } else {
      ipFallback();
    }
  }

  function locate() {
    if (locating) return;
    locating = true;
    if (!hasLocation) status.textContent = "Finding your location…";
    if (!navigator.geolocation) {
      geolocationFailed();
      return;
    }
    navigator.geolocation.getCurrentPosition(
      function (pos) {
        useLocation(pos.coords.latitude, pos.coords.longitude, false);
        remember(pos.coords.latitude, pos.coords.longitude, false);
      },
      geolocationFailed,
      { enableHighAccuracy: false, timeout: 8000, maximumAge: 600000 }
    );
  }

  range.addEventListener("input", function () {
    moved = true;
    showValue();
    if (hasLocation) applyFilter();
    else locate();
  });

  // The log scale packs many positions into each 50 mi at the low end, so the
  // native one-position arrow step often wouldn't change the value at all.
  range.addEventListener("keydown", function (e) {
    var direction = { ArrowLeft: -1, ArrowDown: -1, ArrowRight: 1, ArrowUp: 1 }[e.key];
    if (!direction) return;
    e.preventDefault();
    var position = parseInt(range.value, 10);
    var current = milesAt(position);
    for (position += direction; position >= 0 && position <= maxPosition; position += direction) {
      if (milesAt(position) !== current) {
        range.value = position;
        range.dispatchEvent(new Event("input", { bubbles: true }));
        return;
      }
    }
  });

  range.value = maxPosition;
  showValue();
  status.textContent = HINT;
  wrap.hidden = false;

  function start(permissionState) {
    if (permissionState === "denied") {
      forget();
      return;
    }
    var saved = recall();
    if (saved) useLocation(saved.lat, saved.lon, saved.approximate);
    if (permissionState === "granted") locate();
  }

  if (navigator.permissions && navigator.permissions.query) {
    navigator.permissions.query({ name: "geolocation" }).then(
      function (permission) {
        start(permission.state);
      },
      function () {
        start("prompt");
      }
    );
  } else {
    start("prompt");
  }
})();
