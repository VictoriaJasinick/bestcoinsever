(function () {
  const KEY = "bce_cookie_ok";
  const banner = document.getElementById("cookie-banner");
  const btn = document.getElementById("cookie-accept");
  if (!banner || !btn) return;

  const accepted = localStorage.getItem(KEY) === "1";
  if (!accepted) banner.style.display = "block";

  btn.addEventListener("click", function () {
    localStorage.setItem(KEY, "1");
    banner.style.display = "none";
  });
})();
