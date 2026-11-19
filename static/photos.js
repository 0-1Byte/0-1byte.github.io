(() => {
  "use strict";

  const strip = document.querySelector("[data-photos-strip]");
  const frames = Array.from(document.querySelectorAll(".photos-frame"));
  const viewer = document.querySelector("[data-viewer]");
  const viewerImages = Array.from(document.querySelectorAll("[data-viewer-image]"));
  const closeButton = document.querySelector("[data-viewer-close]");
  const soundToggle = document.querySelector("[data-sound-toggle]");

  if (!strip || !frames.length || !viewer || viewerImages.length !== 2 || !closeButton || !soundToggle) {
    return;
  }

  const photos = frames.map((frame) => ({
    thumbnail: frame.dataset.thumbnail,
    thumbnailWidth: Number(frame.dataset.thumbnailWidth),
    thumbnailHeight: Number(frame.dataset.thumbnailHeight),
    mobile: {
      src: frame.dataset.fullMobile,
      width: Number(frame.dataset.mobileWidth),
      height: Number(frame.dataset.mobileHeight),
    },
    desktop: {
      src: frame.dataset.fullDesktop,
      width: Number(frame.dataset.desktopWidth),
      height: Number(frame.dataset.desktopHeight),
    },
  }));

  const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)");
  let stripIndex = Math.max(0, frames.findIndex((frame) => frame.classList.contains("is-current")));
  let viewerIndex = -1;
  let viewerOpen = false;
  let viewerSwitching = false;
  let transitionTargetIndex = -1;
  let queuedViewerIndex = null;
  let activeViewerLayer = 0;
  let viewerRequestId = 0;
  let fullImageRequest = null;
  let previewImageRequest = null;
  let targetPreviewFailed = false;
  let targetFullFailed = false;
  let transitionTimer = 0;
  let scrollIdleTimer = 0;
  let resizeTimer = 0;
  let savedStripState = null;
  let returnFocus = null;
  let soundMuted = false;
  let audioContext = null;
  let previousBodyOverflow = "";
  let previousRootOverflow = "";

  function selectedResource(index) {
    return window.matchMedia("(max-width: 1024px)").matches
      ? photos[index].mobile
      : photos[index].desktop;
  }

  function setStripIndex(index, playSound) {
    if (index === stripIndex) {
      return false;
    }

    stripIndex = index;
    frames.forEach((frame, frameIndex) => {
      frame.classList.toggle("is-current", frameIndex === index);
    });

    if (playSound) {
      playTick();
    }
    return true;
  }

  function scrollLeftFor(frame) {
    const stripRect = strip.getBoundingClientRect();
    const frameRect = frame.getBoundingClientRect();
    return strip.scrollLeft + frameRect.left - stripRect.left -
      (strip.clientWidth - frame.clientWidth) / 2;
  }

  function goToStripIndex(index, behavior = "smooth", playSound = true) {
    const boundedIndex = Math.max(0, Math.min(frames.length - 1, index));
    setStripIndex(boundedIndex, playSound);
    strip.scrollTo({
      left: scrollLeftFor(frames[boundedIndex]),
      behavior: reducedMotion.matches ? "auto" : behavior,
    });
  }

  function nearestStripIndex() {
    const stripCenter = strip.getBoundingClientRect().left + strip.clientWidth / 2;
    let nearestIndex = 0;
    let nearestDistance = Infinity;

    frames.forEach((frame, index) => {
      const rect = frame.getBoundingClientRect();
      const distance = Math.abs(rect.left + rect.width / 2 - stripCenter);
      if (distance < nearestDistance) {
        nearestDistance = distance;
        nearestIndex = index;
      }
    });

    return nearestIndex;
  }

  function loadDecodedImage(src, priority) {
    const image = new Image();
    image.decoding = "async";
    if ("fetchPriority" in image) {
      image.fetchPriority = priority;
    }

    let cancelled = false;
    let settled = false;
    let resolveRequest;
    let rejectRequest;
    const promise = new Promise((resolve, reject) => {
      resolveRequest = resolve;
      rejectRequest = reject;
    });

    const fail = (error) => {
      if (cancelled || settled) {
        return;
      }
      settled = true;
      rejectRequest(error);
    };

    const ready = async () => {
      if (cancelled || settled) {
        return;
      }
      try {
        if (typeof image.decode === "function") {
          await image.decode();
        }
      } catch (error) {
        if (!image.naturalWidth) {
          fail(error);
          return;
        }
      }
      if (!cancelled && !settled) {
        settled = true;
        resolveRequest(image);
      }
    };

    image.onload = ready;
    image.onerror = () => fail(new Error(`Unable to load photo resource: ${src}`));
    image.src = src;
    if (image.complete && image.naturalWidth) {
      void ready();
    }

    return {
      promise,
      cancel() {
        if (cancelled) {
          return;
        }
        cancelled = true;
        image.onload = null;
        image.onerror = null;
        image.src = "";
        if (!settled) {
          settled = true;
          resolveRequest(null);
        }
      },
    };
  }

  function cancelImageRequests() {
    if (fullImageRequest) {
      fullImageRequest.cancel();
      fullImageRequest = null;
    }
    if (previewImageRequest) {
      previewImageRequest.cancel();
      previewImageRequest = null;
    }
  }

  function setViewerImageSource(image, source) {
    image.width = source.width;
    image.height = source.height;
    image.src = source.src;
  }

  function startFullResolutionRequest(index, requestId) {
    const source = selectedResource(index);
    const request = loadDecodedImage(source.src, "high");
    fullImageRequest = request;

    request.promise.then((loadedImage) => {
      if (!loadedImage || requestId !== viewerRequestId || !viewerOpen || viewerIndex !== index) {
        return;
      }

      const layer = viewerImages[activeViewerLayer];
      layer.width = source.width;
      layer.height = source.height;
      layer.src = loadedImage.src;
    }).catch((error) => {
      if (requestId === viewerRequestId && viewerOpen) {
        console.warn("Could not load the high-resolution photo; keeping its thumbnail.", error);
      }
    });
  }

  function focusViewerCloseButton() {
    requestAnimationFrame(() => closeButton.focus({ preventScroll: true }));
  }

  function openViewer(index) {
    if (viewerOpen || index < 0 || index >= photos.length) {
      return;
    }

    savedStripState = {
      index: stripIndex,
      scrollLeft: strip.scrollLeft,
      viewportWidth: strip.clientWidth,
    };
    returnFocus = frames[index];
    viewerOpen = true;
    viewerIndex = index;
    activeViewerLayer = 0;
    viewerSwitching = false;
    transitionTargetIndex = -1;
    queuedViewerIndex = null;
    viewerRequestId += 1;
    cancelImageRequests();
    targetPreviewFailed = false;
    targetFullFailed = false;

    const thumb = frames[index].querySelector("img");
    const preview = {
      src: thumb.currentSrc || photos[index].thumbnail,
      width: photos[index].thumbnailWidth,
      height: photos[index].thumbnailHeight,
    };
    viewerImages.forEach((image, imageIndex) => {
      image.classList.toggle("is-active", imageIndex === activeViewerLayer);
      image.removeAttribute("src");
    });
    setViewerImageSource(viewerImages[activeViewerLayer], preview);

    previousBodyOverflow = document.body.style.overflow;
    previousRootOverflow = document.documentElement.style.overflow;
    document.body.style.overflow = "hidden";
    document.documentElement.style.overflow = "hidden";
    viewer.hidden = false;
    const requestId = viewerRequestId;
    startFullResolutionRequest(index, requestId);
    focusViewerCloseButton();
  }

  function finishViewerTransition(requestId) {
    if (requestId !== viewerRequestId || !viewerOpen) {
      return;
    }
    viewerImages[1 - activeViewerLayer].removeAttribute("src");
    viewerSwitching = false;
    transitionTargetIndex = -1;

    if (queuedViewerIndex !== null) {
      const nextIndex = queuedViewerIndex;
      queuedViewerIndex = null;
      navigateViewer(nextIndex);
    }
  }

  function abandonViewerTransition(requestId) {
    if (requestId !== viewerRequestId || !viewerOpen) {
      return;
    }

    viewerSwitching = false;
    transitionTargetIndex = -1;
    if (queuedViewerIndex !== null) {
      const nextIndex = queuedViewerIndex;
      queuedViewerIndex = null;
      navigateViewer(nextIndex);
    }
  }

  function beginViewerTransition(index, src, dimensions, requestId) {
    if (requestId !== viewerRequestId || !viewerOpen || viewerIndex === index) {
      return false;
    }

    if (previewImageRequest) {
      previewImageRequest.cancel();
      previewImageRequest = null;
    }

    const outgoingLayer = activeViewerLayer;
    const incomingLayer = 1 - activeViewerLayer;
    const source = { src, width: dimensions.width, height: dimensions.height };
    setViewerImageSource(viewerImages[incomingLayer], source);
    viewerIndex = index;
    transitionTargetIndex = -1;
    activeViewerLayer = incomingLayer;
    viewerSwitching = true;
    playTick();

    requestAnimationFrame(() => {
      if (requestId !== viewerRequestId || !viewerOpen) {
        return;
      }
      viewerImages[incomingLayer].classList.add("is-active");
      viewerImages[outgoingLayer].classList.remove("is-active");
      window.clearTimeout(transitionTimer);
      transitionTimer = window.setTimeout(
        () => finishViewerTransition(requestId),
        reducedMotion.matches ? 30 : 460,
      );
    });
    return true;
  }

  function navigateViewer(index) {
    if (!viewerOpen || index < 0 || index >= photos.length) {
      return;
    }
    if (viewerSwitching) {
      queuedViewerIndex = index;
      return;
    }
    if (index === viewerIndex) {
      return;
    }

    viewerSwitching = true;
    transitionTargetIndex = index;
    viewerRequestId += 1;
    const requestId = viewerRequestId;
    cancelImageRequests();
    targetPreviewFailed = false;
    targetFullFailed = false;

    const thumb = frames[index].querySelector("img");
    if (thumb.complete && thumb.naturalWidth) {
      beginViewerTransition(index, thumb.currentSrc || photos[index].thumbnail, {
        width: photos[index].thumbnailWidth,
        height: photos[index].thumbnailHeight,
      }, requestId);
    } else {
      previewImageRequest = loadDecodedImage(photos[index].thumbnail, "low");
      previewImageRequest.promise.then((loadedImage) => {
        if (!loadedImage) {
          return;
        }
        beginViewerTransition(index, loadedImage.src, {
          width: photos[index].thumbnailWidth,
          height: photos[index].thumbnailHeight,
        }, requestId);
      }).catch((error) => {
        if (requestId === viewerRequestId) {
          console.warn("Could not load the photo preview.", error);
          targetPreviewFailed = true;
          if (targetFullFailed) {
            abandonViewerTransition(requestId);
          }
        }
      });
    }

    const fullRequest = loadDecodedImage(selectedResource(index).src, "high");
    fullImageRequest = fullRequest;
    fullRequest.promise.then((loadedImage) => {
      if (!loadedImage || requestId !== viewerRequestId || !viewerOpen) {
        return;
      }
      const dimensions = selectedResource(index);
      if (viewerIndex === index) {
        const layer = viewerImages[activeViewerLayer];
        layer.width = dimensions.width;
        layer.height = dimensions.height;
        layer.src = loadedImage.src;
      } else if (transitionTargetIndex === index) {
        beginViewerTransition(index, loadedImage.src, dimensions, requestId);
      }
    }).catch((error) => {
      if (requestId === viewerRequestId && viewerOpen) {
        console.warn("Could not load the high-resolution photo; keeping its thumbnail.", error);
        targetFullFailed = true;
        if (targetPreviewFailed) {
          abandonViewerTransition(requestId);
        }
      }
    });
  }

  function stepViewer(direction) {
    const baseIndex = queuedViewerIndex ?? transitionTargetIndex;
    const currentIndex = baseIndex >= 0 ? baseIndex : viewerIndex;
    const nextIndex = (currentIndex + direction + photos.length) % photos.length;
    navigateViewer(nextIndex);
  }

  function closeViewer() {
    if (!viewerOpen) {
      return;
    }

    viewerOpen = false;
    viewer.hidden = true;
    viewerRequestId += 1;
    window.clearTimeout(transitionTimer);
    cancelImageRequests();
    viewerImages.forEach((image) => {
      image.classList.remove("is-active");
      image.removeAttribute("src");
    });
    viewerSwitching = false;
    transitionTargetIndex = -1;
    queuedViewerIndex = null;
    viewerIndex = -1;

    document.body.style.overflow = previousBodyOverflow;
    document.documentElement.style.overflow = previousRootOverflow;

    if (savedStripState) {
      const currentScrollBehavior = strip.style.scrollBehavior;
      const viewportChanged = savedStripState.viewportWidth !== strip.clientWidth;
      strip.style.scrollBehavior = "auto";
      if (!viewportChanged) {
        strip.scrollLeft = savedStripState.scrollLeft;
      }
      setStripIndex(savedStripState.index, false);
      if (viewportChanged) {
        goToStripIndex(savedStripState.index, "auto", false);
      }
      strip.style.scrollBehavior = currentScrollBehavior;
      savedStripState = null;
    }

    if (returnFocus && returnFocus.isConnected) {
      returnFocus.focus({ preventScroll: true });
    }
    returnFocus = null;
  }

  function playTick() {
    if (soundMuted) {
      return;
    }

    const AudioContextConstructor = window.AudioContext || window.webkitAudioContext;
    if (!AudioContextConstructor) {
      return;
    }

    if (!audioContext || audioContext.state === "closed") {
      try {
        audioContext = new AudioContextConstructor();
      } catch (error) {
        console.warn("Film advance sound is unavailable in this browser.", error);
        return;
      }
    }

    if (audioContext.state === "suspended") {
      audioContext.resume().catch((error) => {
        console.warn("Could not resume film advance sound.", error);
      });
    }

    const context = audioContext;
    const startTime = context.currentTime;
    const tickGain = context.createGain();
    const filter = context.createBiquadFilter();
    const oscillator = context.createOscillator();
    const noiseSource = context.createBufferSource();
    const noiseBuffer = context.createBuffer(1, Math.ceil(context.sampleRate * 0.035), context.sampleRate);
    const noiseData = noiseBuffer.getChannelData(0);

    for (let sample = 0; sample < noiseData.length; sample += 1) {
      noiseData[sample] = Math.random() * 2 - 1;
    }

    filter.type = "highpass";
    filter.frequency.setValueAtTime(900, startTime);
    tickGain.gain.setValueAtTime(0.0001, startTime);
    tickGain.gain.exponentialRampToValueAtTime(0.045, startTime + 0.002);
    tickGain.gain.exponentialRampToValueAtTime(0.0001, startTime + 0.04);
    oscillator.type = "triangle";
    oscillator.frequency.setValueAtTime(1250, startTime);
    oscillator.frequency.exponentialRampToValueAtTime(420, startTime + 0.035);
    noiseSource.buffer = noiseBuffer;
    oscillator.connect(filter);
    noiseSource.connect(filter);
    filter.connect(tickGain);
    tickGain.connect(context.destination);
    oscillator.start(startTime);
    noiseSource.start(startTime);
    oscillator.stop(startTime + 0.04);
    noiseSource.stop(startTime + 0.035);
  }

  function setMuted(muted) {
    soundMuted = muted;
    soundToggle.setAttribute("aria-pressed", String(muted));
    soundToggle.setAttribute(
      "aria-label",
      muted ? "Unmute film advance sound" : "Mute film advance sound",
    );
  }

  function createWheelHandler(moveBy) {
    let lastDiscreteTime = 0;
    let lastDiscreteDirection = 0;
    let lastContinuousTime = 0;
    let continuousDirection = 0;
    let accumulatedDelta = 0;
    let continuousLocked = false;
    let idleTimer = 0;

    return (event) => {
      let deltaX = event.deltaX;
      let deltaY = event.deltaY;
      if (event.deltaMode === WheelEvent.DOM_DELTA_LINE) {
        const lineHeight = Number.parseFloat(getComputedStyle(strip).lineHeight) || 16;
        deltaX *= lineHeight;
        deltaY *= lineHeight;
      } else if (event.deltaMode === WheelEvent.DOM_DELTA_PAGE) {
        deltaX *= strip.clientWidth;
        deltaY *= strip.clientHeight;
      }

      const delta = Math.abs(deltaX) > Math.abs(deltaY) * 1.2 ? deltaX : deltaY;
      if (Math.abs(delta) < 1) {
        return;
      }
      event.preventDefault();

      const direction = Math.sign(delta);
      const now = performance.now();
      if (Math.abs(delta) >= 48) {
        if (
          direction === lastDiscreteDirection &&
          now - lastDiscreteTime < 360
        ) {
          return;
        }
        lastDiscreteDirection = direction;
        lastDiscreteTime = now;
        accumulatedDelta = 0;
        continuousLocked = true;
        window.clearTimeout(idleTimer);
        idleTimer = window.setTimeout(() => {
          continuousLocked = false;
          continuousDirection = 0;
        }, 220);
        moveBy(direction);
        return;
      }

      if (now - lastContinuousTime > 220 || (continuousDirection && direction !== continuousDirection)) {
        accumulatedDelta = 0;
        continuousLocked = false;
      }
      lastContinuousTime = now;
      continuousDirection = direction;
      accumulatedDelta += Math.abs(delta);
      window.clearTimeout(idleTimer);
      idleTimer = window.setTimeout(() => {
        accumulatedDelta = 0;
        continuousLocked = false;
        continuousDirection = 0;
      }, 220);

      if (!continuousLocked && accumulatedDelta >= 44) {
        accumulatedDelta = 0;
        continuousLocked = true;
        moveBy(direction);
      }
    };
  }

  const stripWheelHandler = createWheelHandler((direction) => {
    goToStripIndex(stripIndex + direction);
  });
  const viewerWheelHandler = createWheelHandler((direction) => {
    stepViewer(direction);
  });

  strip.addEventListener("wheel", stripWheelHandler, { passive: false });
  viewer.addEventListener("wheel", viewerWheelHandler, { passive: false });

  strip.addEventListener("scroll", () => {
    if (viewerOpen) {
      return;
    }
    window.clearTimeout(scrollIdleTimer);
    scrollIdleTimer = window.setTimeout(() => {
      setStripIndex(nearestStripIndex(), true);
    }, 140);
  }, { passive: true });

  window.addEventListener("resize", () => {
    if (viewerOpen) {
      return;
    }
    window.clearTimeout(resizeTimer);
    resizeTimer = window.setTimeout(() => {
      const currentScrollBehavior = strip.style.scrollBehavior;
      strip.style.scrollBehavior = "auto";
      goToStripIndex(stripIndex, "auto", false);
      strip.style.scrollBehavior = currentScrollBehavior;
    }, 100);
  });

  frames.forEach((frame, index) => {
    frame.addEventListener("click", () => openViewer(index));
  });

  soundToggle.addEventListener("click", () => setMuted(!soundMuted));
  closeButton.addEventListener("click", closeViewer);
  viewer.addEventListener("click", (event) => {
    if (event.target === viewer) {
      closeViewer();
    }
  });

  let touchStart = null;
  viewer.addEventListener("pointerdown", (event) => {
    if (event.pointerType === "touch") {
      touchStart = { x: event.clientX, y: event.clientY };
    }
  });
  viewer.addEventListener("pointerup", (event) => {
    if (!touchStart || event.pointerType !== "touch") {
      touchStart = null;
      return;
    }
    const deltaX = event.clientX - touchStart.x;
    const deltaY = event.clientY - touchStart.y;
    touchStart = null;
    if (Math.abs(deltaX) >= 48 && Math.abs(deltaX) > Math.abs(deltaY) * 1.25) {
      stepViewer(deltaX < 0 ? 1 : -1);
    }
  });
  viewer.addEventListener("pointercancel", () => {
    touchStart = null;
  });

  document.addEventListener("keydown", (event) => {
    if (event.altKey || event.ctrlKey || event.metaKey) {
      return;
    }

    if (event.key.toLowerCase() === "m") {
      event.preventDefault();
      setMuted(!soundMuted);
      return;
    }

    if (viewerOpen) {
      if (event.key === "Escape") {
        event.preventDefault();
        closeViewer();
      } else if (event.key === "ArrowLeft") {
        event.preventDefault();
        stepViewer(-1);
      } else if (event.key === "ArrowRight") {
        event.preventDefault();
        stepViewer(1);
      }
      return;
    }

    if (event.key === "ArrowLeft" || event.key === "ArrowRight") {
      event.preventDefault();
      goToStripIndex(stripIndex + (event.key === "ArrowRight" ? 1 : -1));
    }
  });

  window.addEventListener("pagehide", () => {
    window.clearTimeout(scrollIdleTimer);
    window.clearTimeout(resizeTimer);
    window.clearTimeout(transitionTimer);
    cancelImageRequests();
    if (audioContext && audioContext.state !== "closed") {
      audioContext.close().catch((error) => {
        console.warn("Could not close the film advance audio context.", error);
      });
    }
  }, { once: true });

  requestAnimationFrame(() => {
    strip.scrollTo({
      left: scrollLeftFor(frames[stripIndex]),
      behavior: "auto",
    });
  });
})();
