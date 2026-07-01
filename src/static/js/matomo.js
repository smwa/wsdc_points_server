// Matomo analytics (self-hosted at mat.mechstack.dev, site id 7).
//
// Kept as an external file rather than an inline <script> so the page's
// Content-Security-Policy can stay strict (script-src 'self' plus the Matomo
// host, no 'unsafe-inline'). The loader below injects mat.mechstack.dev/matomo.js
// and tracking hits go to matomo.php, so the CSP also allow-lists that host for
// script-src, img-src, and connect-src (see src/main.py).
var _paq = (window._paq = window._paq || []);
/* tracker methods like "setCustomDimension" should be called before "trackPageView" */
_paq.push(["trackPageView"]);
_paq.push(["enableLinkTracking"]);
(function () {
  var u = "https://mat.mechstack.dev/";
  _paq.push(["setTrackerUrl", u + "matomo.php"]);
  _paq.push(["setSiteId", "7"]);
  var d = document,
    g = d.createElement("script"),
    s = d.getElementsByTagName("script")[0];
  g.async = true;
  g.src = u + "matomo.js";
  s.parentNode.insertBefore(g, s);
})();
