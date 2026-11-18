(() => {
  const viewer = document.querySelector(".photos-viewer");
  const previewImage = viewer.querySelector(".photos-viewer__image--preview");
  const detailImage = viewer.querySelector(".photos-viewer__image--detail");
  const closeButton = viewer.querySelector(".photos-viewer__close");
  const previousButton = viewer.querySelector(".photos-viewer__step--previous");
  const nextButton = viewer.querySelector(".photos-viewer__step--next");
  const photos = Array.from(document.querySelectorAll(".photos-card__button")).map((button) => ({
    button,
    thumbnail: button.dataset.thumbnail,
    thumbnailWidth: Number(button.dataset.thumbnailWidth),
    thumbnailHeight: Number(button.dataset.thumbnailHeight),
    mobile: {
      src: button.dataset.fullMobile,
      width: Number(button.dataset.mobileWidth),
      height: Number(button.dataset.mobileHeight)
    },
    desktop: {
      src: button.dataset.fullDesktop,
      width: Number(button.dataset.desktopWidth),
      height: Number(button.dataset.desktopHeight)
    }
  }));
  let currentIndex = 0;
  let requestId = 0;
  let lastFocusedElement = null;
  let previousOverflow = "";
  let touchStart = null;

  function showPhoto(index) {
    const selectedIndex = (index + photos.length) % photos.length;
    currentIndex = selectedIndex;
    const activeRequest = ++requestId;
    const photo = photos[currentIndex];
    const preview = photo.button.querySelector("img");
    const fullSize = window.matchMedia("(max-width: 1024px)").matches ? photo.mobile : photo.desktop;

    detailImage.classList.remove("is-ready");
    detailImage.removeAttribute("src");
    detailImage.width = fullSize.width;
    detailImage.height = fullSize.height;
    previewImage.src = preview.currentSrc || photo.thumbnail;
    previewImage.width = photo.thumbnailWidth;
    previewImage.height = photo.thumbnailHeight;

    detailImage.fetchPriority = "high";
    detailImage.decoding = "async";
    detailImage.src = fullSize.src;
    detailImage.decode().then(() => {
      if (activeRequest !== requestId || viewer.hidden || currentIndex !== selectedIndex) return;
      detailImage.classList.add("is-ready");
    }).catch(() => {
      if (activeRequest !== requestId || viewer.hidden || currentIndex !== selectedIndex) return;
      detailImage.removeAttribute("src");
    });
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
    requestId += 1;
    viewer.hidden = true;
    detailImage.classList.remove("is-ready");
    detailImage.removeAttribute("src");
    previewImage.removeAttribute("src");
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
