(() => {
  "use strict";

  const tools = document.querySelector("[data-home-tools]");
  const toggle = document.querySelector("[data-home-clean-toggle]");
  const cleanLabel = document.querySelector("[data-home-clean-label]");
  const saveButton = document.querySelector("[data-home-save]");
  const status = document.querySelector("[data-home-tools-status]");
  const home = document.querySelector(".home--living");
  const background = home && home.querySelector("[data-home-background-image]");
  const quote = home && home.querySelector("[data-quote-text]");
  const source = home && home.querySelector("[data-quote-source]");
  const main = document.querySelector("body > main.main");
  const footer = document.querySelector("body > footer.footer");

  if (!tools || !toggle || !cleanLabel || !saveButton || !status || !home || !background || !quote || !main) {
    console.error("[home-tools] 首页工具所需的主页元素缺失，未启用工具。");
    return;
  }
  if (footer) footer.classList.add("home-clean-footer");

  const cleanModeQuery = window.matchMedia("(hover: hover) and (pointer: fine)");
  let toastTimer = 0;
  let idleTimer = 0;
  let cleanMode = false;
  let keyboardNavigation = false;

  function showStatus(message, duration = 2400) {
    window.clearTimeout(toastTimer);
    status.textContent = message;
    status.hidden = false;
    requestAnimationFrame(() => status.classList.add("is-visible"));
    toastTimer = window.setTimeout(() => {
      status.classList.remove("is-visible");
      window.setTimeout(() => {
        if (!status.classList.contains("is-visible")) status.hidden = true;
      }, 220);
    }, duration);
  }

  function hasKeyboardFocus() {
    return keyboardNavigation && Array.from(tools.querySelectorAll("button"))
      .some((button) => button.matches(":focus-visible"));
  }

  function revealTools() {
    tools.classList.remove("is-idle");
    window.clearTimeout(idleTimer);
    if (!cleanMode || !cleanModeQuery.matches || hasKeyboardFocus()) return;
    idleTimer = window.setTimeout(() => tools.classList.add("is-idle"), 3600);
  }

  function setCleanMode(enabled) {
    cleanMode = enabled;
    document.documentElement.classList.toggle("home-clean-mode", enabled);
    document.body.classList.toggle("home-clean-mode", enabled);
    toggle.setAttribute("aria-pressed", String(enabled));
    toggle.setAttribute("aria-label", enabled ? "退出清屏模式" : "进入清屏模式");
    cleanLabel.textContent = enabled ? "退出清屏" : "清屏";

    if (enabled) {
      revealTools();
      showStatus("清屏模式 · Esc 退出", 2200);
    } else {
      tools.classList.remove("is-idle");
      window.clearTimeout(idleTimer);
    }
  }

  function canvasBlob(canvas) {
    return new Promise((resolve, reject) => {
      try {
        canvas.toBlob((blob) => {
          if (blob) resolve(blob);
          else reject(new Error("浏览器无法生成 PNG 图片。"));
        }, "image/png");
      } catch (error) {
        reject(error);
      }
    });
  }

  function positionPercent(value, axis) {
    const normalized = value.toLowerCase();
    if (normalized.includes(axis === "x" ? "left" : "top")) return 0;
    if (normalized.includes(axis === "x" ? "right" : "bottom")) return 100;
    const percentage = normalized.match(/-?\d+(?:\.\d+)?%/);
    return percentage ? Number.parseFloat(percentage[0]) : 50;
  }

  function backgroundRect(image, width, height) {
    const scale = Math.max(width / image.naturalWidth, height / image.naturalHeight);
    const drawWidth = image.naturalWidth * scale;
    const drawHeight = image.naturalHeight * scale;
    const position = window.getComputedStyle(image).objectPosition.split(/\s+/);
    const xPercent = positionPercent(position[0] || "50%", "x");
    const yPercent = positionPercent(position[1] || position[0] || "50%", "y");
    return {
      x: (width - drawWidth) * xPercent / 100,
      y: (height - drawHeight) * yPercent / 100,
      width: drawWidth,
      height: drawHeight,
    };
  }

  function getTextLines(element, context, beforeText = "") {
    const groups = new Map();
    const walker = document.createTreeWalker(element, NodeFilter.SHOW_TEXT);
    let node;

    while ((node = walker.nextNode())) {
      let offset = 0;
      for (const character of Array.from(node.data)) {
        const start = offset;
        offset += character.length;
        if (character === "\n") continue;

        const range = document.createRange();
        range.setStart(node, start);
        range.setEnd(node, offset);
        const rect = range.getBoundingClientRect();
        if (!rect.height) continue;

        const lineKey = Math.round(rect.top * 2) / 2;
        const group = groups.get(lineKey) || { text: "", left: rect.left, top: rect.top, height: rect.height };
        group.text += character;
        group.left = Math.min(group.left, rect.left);
        group.height = Math.max(group.height, rect.height);
        groups.set(lineKey, group);
      }
    }

    const style = window.getComputedStyle(element);
    const fontSize = Number.parseFloat(style.fontSize) || 16;
    const lineHeight = Number.parseFloat(style.lineHeight) || fontSize * 1.2;
    const metrics = context.measureText("Mg");
    const ascent = metrics.actualBoundingBoxAscent || fontSize * 0.8;
    const descent = metrics.actualBoundingBoxDescent || fontSize * 0.2;
    const baselineOffset = (lineHeight - ascent - descent) / 2 + ascent;

    return Array.from(groups.values()).map((line, index) => {
      const prefix = index === 0 ? beforeText : "";
      const prefixWidth = prefix ? context.measureText(prefix).width : 0;
      return {
        text: prefix + line.text,
        x: line.left - prefixWidth,
        y: line.top + baselineOffset,
      };
    });
  }

  function drawTextElement(context, element, prefix = "") {
    if (!element || element.hidden || window.getComputedStyle(element).visibility === "hidden") return;
    const style = window.getComputedStyle(element);
    context.font = style.font;
    context.fillStyle = style.color;
    context.textAlign = style.textAlign === "start" ? "left" : style.textAlign;
    context.textBaseline = "alphabetic";
    if ("letterSpacing" in context) context.letterSpacing = style.letterSpacing;

    const lines = getTextLines(element, context, prefix);
    if (element.textContent.trim() && !lines.length) {
      throw new Error("无法读取文字的实际排版位置。");
    }
    for (const line of lines) {
      if (!Number.isFinite(context.measureText(line.text).width)) {
        throw new Error("当前字体无法测量，无法安全生成图片。");
      }
      context.fillText(line.text, line.x, line.y);
    }
  }

  function getTimestamp() {
    const now = new Date();
    const date = [
      now.getFullYear(),
      String(now.getMonth() + 1).padStart(2, "0"),
      String(now.getDate()).padStart(2, "0"),
    ].join("");
    const time = [
      String(now.getHours()).padStart(2, "0"),
      String(now.getMinutes()).padStart(2, "0"),
      String(now.getSeconds()).padStart(2, "0"),
    ].join("");
    return `${date}-${time}`;
  }

  async function saveCurrentFrame() {
    saveButton.disabled = true;
    try {
      if (quote.closest(".is-loading") || !quote.textContent.trim()) {
        throw new Error("当前句子仍在准备中，请稍后再试。");
      }
      if (!background.complete || !background.naturalWidth || !background.naturalHeight) {
        throw new Error("当前背景图片尚未成功加载，暂时无法保存画面。");
      }

      const imageUrl = new URL(background.currentSrc || background.src, window.location.href);
      if (imageUrl.origin !== window.location.origin) {
        throw new Error("当前背景图片来自其他站点，浏览器的跨域保护阻止了导出。");
      }

      await Promise.race([
        document.fonts.ready,
        new Promise((resolve) => window.setTimeout(resolve, 1500)),
      ]);

      const width = document.documentElement.clientWidth || window.innerWidth;
      const height = document.documentElement.clientHeight || window.innerHeight;
      if (!width || !height) throw new Error("无法读取当前视口尺寸。");
      const scale = Math.min(
        2,
        4096 / width,
        4096 / height,
        Math.sqrt(16000000 / (width * height)),
      );
      const canvas = document.createElement("canvas");
      canvas.width = Math.round(width * scale);
      canvas.height = Math.round(height * scale);
      const context = canvas.getContext("2d");
      if (!context) throw new Error("浏览器无法创建图片画布。");

      context.scale(scale, scale);
      context.fillStyle = "#101214";
      context.fillRect(0, 0, width, height);

      const imageStyle = window.getComputedStyle(background);
      const rect = backgroundRect(background, width, height);
      const transform = imageStyle.transform === "none"
        ? null
        : new DOMMatrix(imageStyle.transform);
      context.save();
      const imageOpacity = Number.parseFloat(imageStyle.opacity);
      context.globalAlpha = Number.isFinite(imageOpacity) ? imageOpacity : 1;
      if (transform) {
        context.transform(
          transform.a,
          transform.b,
          transform.c,
          transform.d,
          transform.e,
          transform.f,
        );
      }
      context.drawImage(background, rect.x, rect.y, rect.width, rect.height);
      context.restore();

      context.fillStyle = "rgba(8, 10, 12, .62)";
      context.fillRect(0, 0, width, height);
      const vignette = context.createRadialGradient(
        width / 2, height / 2, Math.min(width, height) * 0.18,
        width / 2, height / 2, Math.max(width, height) * 0.76,
      );
      vignette.addColorStop(0, "rgba(0, 0, 0, 0)");
      vignette.addColorStop(1, "rgba(0, 0, 0, .24)");
      context.fillStyle = vignette;
      context.fillRect(0, 0, width, height);

      drawTextElement(context, quote, "");
      if (source && !source.hidden) {
        const pseudoContent = window.getComputedStyle(source, "::before").content;
        let prefix = "";
        if (pseudoContent && pseudoContent !== "none" && !source.hasAttribute("data-has-dash")) {
          try {
            prefix = JSON.parse(pseudoContent);
          } catch {
            prefix = "— ";
          }
        }
        drawTextElement(context, source, prefix);
      }
      const note = home.querySelector(".home-note");
      if (note) drawTextElement(context, note);

      const blob = await canvasBlob(canvas);
      const objectUrl = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = objectUrl;
      link.download = `Chen-${getTimestamp()}.png`;
      link.click();
      window.setTimeout(() => URL.revokeObjectURL(objectUrl), 60000);
      showStatus("画面已保存");
    } catch (error) {
      console.error("[home-tools] 无法保存当前主页画面。", error);
      const message = error && error.name === "SecurityError"
        ? "浏览器阻止了跨域图片导出；请确认背景图片与网站同源。"
        : error && error.message
          ? error.message
          : "保存失败，请稍后重试。";
      showStatus(`保存失败：${message}`, 4200);
    } finally {
      saveButton.disabled = false;
    }
  }

  toggle.addEventListener("click", () => setCleanMode(!cleanMode));
  saveButton.addEventListener("click", saveCurrentFrame);

  document.addEventListener("keydown", (event) => {
    keyboardNavigation = true;
    if (event.key === "Escape" && cleanMode) {
      event.preventDefault();
      setCleanMode(false);
      toggle.focus();
    } else if (cleanMode) {
      revealTools();
    }
  });

  document.addEventListener("pointermove", () => {
    if (cleanMode && cleanModeQuery.matches) revealTools();
  }, { passive: true });

  document.addEventListener("pointerdown", () => {
    keyboardNavigation = false;
    if (cleanMode && cleanModeQuery.matches) revealTools();
  }, { passive: true });

  tools.addEventListener("focusout", () => {
    window.setTimeout(() => {
      if (cleanMode && !tools.contains(document.activeElement)) revealTools();
    }, 0);
  });
})();
