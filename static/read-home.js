(() => {
  "use strict";

  const track = document.querySelector("[data-read-book-track]");
  if (!track) return;

  const controls = [...document.querySelectorAll("[data-read-step]")];
  const previous = controls.find(button => button.dataset.readStep === "-1");
  const next = controls.find(button => button.dataset.readStep === "1");
  const items = [...track.querySelectorAll(".read-book")];
  if (!items.length) return;

  const maxScroll = () => Math.max(0, track.scrollWidth - track.clientWidth);

  const updateControls = () => {
    const max = maxScroll();
    const currentLeft = track.scrollLeft;
    const startScroll = Number.parseFloat(getComputedStyle(track).paddingLeft) || 0;
    if (previous) previous.disabled = max <= 1 || currentLeft <= startScroll + 1;
    if (next) next.disabled = max <= 1 || currentLeft >= max - 3;
  };

  const move = direction => {
    const max = maxScroll();
    const stride = Math.max(1, track.clientWidth * 0.72);
    const target = Math.max(0, Math.min(max, track.scrollLeft + direction * stride));
    track.scrollTo({
      left: target,
      behavior: matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth"
    });
  };

  previous?.addEventListener("click", () => move(-1));
  next?.addEventListener("click", () => move(1));
  track.addEventListener("scroll", () => {
    updateControls();
  }, { passive: true });
  track.addEventListener("keydown", event => {
    if (event.key !== "ArrowLeft" && event.key !== "ArrowRight") return;
    event.preventDefault();
    move(event.key === "ArrowRight" ? 1 : -1);
  });

  track.querySelectorAll(".read-book-artwork img").forEach(image => {
    image.addEventListener("error", () => {
      const original = image.dataset.originalSrc;
      if (original && image.src !== new URL(original, location.href).href) {
        image.removeAttribute("srcset");
        image.removeAttribute("sizes");
        image.removeAttribute("data-original-src");
        image.src = original;
        return;
      }
      const fallbackCover = image.dataset.fallbackCover;
      if (fallbackCover && image.src !== new URL(fallbackCover, location.href).href) {
        image.removeAttribute("data-fallback-cover");
        image.src = fallbackCover;
        return;
      }
      image.hidden = true;
      const fallback = image.parentElement.querySelector(".read-book-fallback");
      if (fallback) fallback.hidden = false;
    });
  });

  window.addEventListener("resize", () => {
    updateControls();
  }, { passive: true });

  updateControls();
})();
