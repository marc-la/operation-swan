// Swan dashboard: reload every minute, and keep the sections you opened open across reloads (this browser only).
(function () {
  var KEY = "swan-open", open = {};
  try { open = JSON.parse(localStorage.getItem(KEY) || "{}"); } catch (e) {}
  document.querySelectorAll("details[id]").forEach(function (d) {
    if (open[d.id]) d.open = true;
    d.addEventListener("toggle", function () {
      open[d.id] = d.open;
      try { localStorage.setItem(KEY, JSON.stringify(open)); } catch (e) {}
    });
  });
  setTimeout(function () { location.reload(); }, 60000);
})();
