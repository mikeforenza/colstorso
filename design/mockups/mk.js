/* Mockup helper: ?annotate=1 shows numbered pins + notes panel; ?frame=390 sets frame width;
   ?theme=dark switches theme; ?shot=1 hides the toggle (for PNG renders). Not product code. */
(function () {
  var q = new URLSearchParams(location.search), h = document.documentElement;
  if (q.get("theme")) h.setAttribute("data-theme", q.get("theme"));
  if (q.get("shot")) h.classList.add("shot");
  if (q.get("frame")) h.style.setProperty("--mk-frame-w", q.get("frame") + "px");
  function pins() {
    document.querySelectorAll(".mk-pin").forEach(function (p) { p.remove(); });
    if (!h.classList.contains("annotate")) return;
    var frame = document.querySelector(".mk-frame"), fr = frame.getBoundingClientRect();
    document.querySelectorAll("[data-note]").forEach(function (el) {
      var r = el.getBoundingClientRect(); if (!r.width || !r.height) return; var p = document.createElement("div");
      p.className = "mk-pin"; p.textContent = el.getAttribute("data-note");
      p.style.left = Math.max(4, Math.min(r.right - fr.left - 18, fr.width - 30)) + "px";
      p.style.top = Math.max(4, r.top - fr.top - 10) + "px";
      frame.appendChild(p);
    });
  }
  function set(on) { h.classList.toggle("annotate", on); requestAnimationFrame(pins); }
  window.addEventListener("load", function () {
    var b = document.createElement("button"); b.className = "mk-toggle"; b.type = "button";
    b.textContent = "Toggle annotations"; b.onclick = function () { set(!h.classList.contains("annotate")); };
    document.body.appendChild(b);
    set(q.get("annotate") === "1");
  });
  window.addEventListener("resize", pins);
})();
