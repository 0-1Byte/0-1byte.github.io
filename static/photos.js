(() => {
  const viewer = document.querySelector(".photos-viewer");
  const viewerImage = viewer.querySelector(".photos-viewer__image");
  const closeButton = viewer.querySelector(".photos-viewer__close");
  const previousButton = viewer.querySelector(".photos-viewer__step--previous");
  const nextButton = viewer.querySelector(".photos-viewer__step--next");
  const photos = Array.from(document.querySelectorAll(".photos-card__button")).map((button) => ({
    button,
    src: button.dataset.full,
    width: Number(button.dataset.width),
    height: Number(button.dataset.height)
  }));
  let currentIndex = 0;
  let lastFocusedElement = null;
  let previousOverflow = "";
  let touchStart = null;

  function preload(index) {
    const photo = photos[(index + photos.length) % photos.length];
    if (!photo) return;
    const image = new Image();
    image.src = photo.src;
  }

  function showPhoto(index) {
    currentIndex = (index + photos.length) % photos.length;
    const photo = photos[currentIndex];
    viewerImage.src = photo.src;
    viewerImage.width = photo.width;
    viewerImage.height = photo.height;
    preload(currentIndex - 1);
    preload(currentIndex + 1);
  }

  function openViewer(index) {
    lastFocusedElement = photos[index].button;
    previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    viewer.hidden = false;
    showPhoto(index);
    closeButton.focus();
  }

  function closeViewer() {
    if (viewer.hidden) return;
    viewer.hidden = true;
    viewerImage.removeAttribute("src");
    document.body.style.overflow = previousOverflow;
    lastFocusedElement?.focus();
  }

  photos.forEach((photo, index) => {
    photo.button.addEventListener("click", () => openViewer(index));
  });
  closeButton.addEventListener("click", closeViewer);
  previousButton.addEventListener("click", () => showPhoto(currentIndex - 1));
  nextButton.addEventListener("click", () => showPhoto(currentIndex + 1));

  viewer.addEventListener("click", (event) => {
    if (event.target === viewer) closeViewer();
  });

  document.addEventListener("keydown", (event) => {
    if (viewer.hidden) return;
    if (event.key === "Escape") {
      event.preventDefault();
      closeViewer();
    } else if (event.key === "ArrowLeft") {
      event.preventDefault();
      showPhoto(currentIndex - 1);
    } else if (event.key === "ArrowRight") {
      event.preventDefault();
      showPhoto(currentIndex + 1);
    }
  });

  viewer.addEventListener("touchstart", (event) => {
    if (event.changedTouches.length !== 1) return;
    touchStart = {
      x: event.changedTouches[0].clientX,
      y: event.changedTouches[0].clientY
    };
  }, { passive: true });

  viewer.addEventListener("touchend", (event) => {
    if (!touchStart || event.changedTouches.length !== 1) return;
    const deltaX = event.changedTouches[0].clientX - touchStart.x;
    const deltaY = event.changedTouches[0].clientY - touchStart.y;
    touchStart = null;
    if (Math.abs(deltaX) < 48 || Math.abs(deltaX) < Math.abs(deltaY) * 1.2) return;
    showPhoto(currentIndex + (deltaX < 0 ? 1 : -1));
  }, { passive: true });
})();
