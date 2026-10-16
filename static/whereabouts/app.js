(function () {
  "use strict";

  const core = window.WhereaboutsCore;
  const form = document.getElementById("search-form");
  const input = document.getElementById("place-query");
  const submit = form.querySelector('button[type="submit"]');
  const clearButton = document.getElementById("clear-query");
  const status = document.getElementById("status");
  const results = document.getElementById("results");
  const resultsTitle = document.getElementById("results-title");
  const resultCount = document.getElementById("result-count");
  const candidateList = document.getElementById("candidate-list");
  const detail = document.getElementById("place-detail");
  const fallbackLinks = document.getElementById("fallback-links");
  const shareContext = document.getElementById("share-context");
  const contextText = document.getElementById("context-text");
  const rankingNote = document.getElementById("ranking-note");
  let context = "";
  let map = null;
  let mapObserver = null;
  let querySequence = 0;

  function setStatus(message, kind) {
    status.textContent = message || "";
    status.dataset.kind = kind || "";
  }

  function setBusy(busy) {
    submit.disabled = busy;
    submit.textContent = busy ? "查找中…" : "看看 ↗";
    input.disabled = busy;
    clearButton.disabled = busy;
  }

  function textElement(tag, className, text) {
    const element = document.createElement(tag);
    if (className) element.className = className;
    element.textContent = text || "";
    return element;
  }

  function resetMap() {
    if (mapObserver) {
      mapObserver.disconnect();
      mapObserver = null;
    }
    if (map) {
      map.remove();
      map = null;
    }
  }

  function zoomFor(candidate) {
    const dim = candidate.coordinates && candidate.coordinates.dim;
    if (!dim) return 7;
    if (dim >= 500000) return 4;
    if (dim >= 100000) return 6;
    if (dim >= 20000) return 8;
    if (dim >= 4000) return 10;
    return 12;
  }

  function addMap(candidate) {
    if (!candidate.coordinates) return;
    const frame = document.createElement("div");
    frame.className = "map-frame";
    const mapElement = document.createElement("div");
    mapElement.className = "map";
    mapElement.setAttribute("role", "img");
    mapElement.setAttribute("aria-label", `${candidate.title} 的地图位置`);
    frame.append(mapElement);
    detail.append(frame);

    if (!window.L) {
      showMapError(frame, "交互地图暂不可用。你仍可通过下方链接在外部地图中查看。");
      return;
    }

    const { lat, lon } = candidate.coordinates;
    map = window.L.map(mapElement, { scrollWheelZoom: false }).setView([lat, lon], zoomFor(candidate));
    window.L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
      maxZoom: 19,
      attribution: '&copy; <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener noreferrer">OpenStreetMap contributors</a>'
    }).addTo(map);
    window.L.circleMarker([lat, lon], {
      radius: 8,
      color: "#fffefa",
      weight: 3,
      fillColor: "#315640",
      fillOpacity: 1
    }).addTo(map).bindTooltip(candidate.title, { permanent: true, direction: "top", offset: [0, -8] });
    map.on("tileerror", () => showMapError(frame, "地图瓦片加载失败；你仍可通过下方链接查看地图。"));
    mapObserver = new ResizeObserver(() => {
      if (map) map.invalidateSize({ pan: false });
    });
    mapObserver.observe(mapElement);
  }

  function showMapError(frame, message) {
    let notice = frame.querySelector(".map-error");
    if (!notice) {
      notice = document.createElement("div");
      notice.className = "map-error";
      frame.append(notice);
    }
    notice.textContent = message;
  }

  function renderDetail(candidate, selectedButton) {
    resetMap();
    detail.replaceChildren();
    candidateList.querySelectorAll(".candidate").forEach((button) => {
      button.setAttribute("aria-pressed", String(button === selectedButton));
    });

    const title = textElement("h3", "detail-title", candidate.title);
    detail.append(title);
    if (candidate.aliases && candidate.aliases.length) {
      detail.append(textElement("p", "detail-alias", `别名或其他语言名称：${candidate.aliases.join(" · ")}`));
    }

    if (candidate.coordinates) {
      addMap(candidate);
      detail.append(textElement("p", "map-attribution", ""));
      const attribution = detail.querySelector(".map-attribution");
      const credit = document.createTextNode("地图数据：");
      const link = document.createElement("a");
      link.href = "https://www.openstreetmap.org/copyright";
      link.target = "_blank";
      link.rel = "noopener noreferrer";
      link.textContent = "© OpenStreetMap contributors";
      attribution.append(credit, link);
      const { lat, lon } = candidate.coordinates;
      detail.append(textElement("p", "coordinate", `坐标 ${lat.toFixed(5)}, ${lon.toFixed(5)} · 来源：${candidate.sourceLabel}`));
    } else {
      detail.append(textElement("p", "no-coordinates", "此条目没有可验证的地理坐标，因此不显示地图标记；你仍可查看来源或用地名打开外部地图。"));
    }

    detail.append(textElement("p", "detail-heading", "简明背景"));
    detail.append(textElement("p", "excerpt", candidate.extract || "来源条目没有提供可用的简介；这里不推测国家归属或周边地理关系。"));

    const source = document.createElement("a");
    source.className = "source-link";
    source.href = candidate.sourceUrl;
    source.target = "_blank";
    source.rel = "noopener noreferrer";
    source.textContent = `查看来源：${candidate.sourceLabel} ↗`;
    detail.append(source);

    const links = document.createElement("nav");
    links.className = "map-links";
    links.setAttribute("aria-label", "在外部地图中查看");
    appendMapLinks(links, candidate);
    detail.append(links);
  }

  function appendMapLinks(container, candidate) {
    for (const item of core.mapLinks(candidate, zoomFor(candidate))) {
      const anchor = document.createElement("a");
      anchor.className = "map-link";
      anchor.href = item.href;
      anchor.target = "_blank";
      anchor.rel = "noopener noreferrer";
      anchor.textContent = `${item.label} ↗`;
      container.append(anchor);
    }
  }

  function showFallbackLinks(query) {
    fallbackLinks.replaceChildren();
    fallbackLinks.hidden = false;
    appendMapLinks(fallbackLinks, { title: query });
  }

  function renderCandidates(candidates, query) {
    results.hidden = false;
    resultsTitle.textContent = query;
    resultCount.textContent = `${candidates.length} 个候选`;
    candidateList.replaceChildren();
    detail.replaceChildren();

    rankingNote.hidden = !context;
    rankingNote.textContent = rankingNote.hidden
      ? ""
      : "候选排序可能参考仅保留在本机的分享上下文；这只是词语匹配提示，不代表理解了文章语境。";

    for (const candidate of candidates) {
      const button = document.createElement("button");
      button.className = "candidate";
      button.type = "button";
      button.setAttribute("aria-pressed", "false");
      const meta = candidate.coordinates ? `${candidate.sourceLabel} · 有坐标` : `${candidate.sourceLabel} · 无坐标`;
      button.append(
        textElement("span", "candidate-title", candidate.title),
        textElement("span", "candidate-meta", candidate.aliases && candidate.aliases.length
          ? `${meta} · 别名：${candidate.aliases.join("、")}`
          : meta),
        textElement("span", "candidate-summary", candidate.extract || "来源没有提供简介")
      );
      button.addEventListener("click", () => renderDetail(candidate, button));
      candidateList.append(button);
    }
    detail.append(textElement("p", "select-prompt", "请选择一个候选地点，查看有来源支持的坐标与地理背景。"));
  }

  async function search(query) {
    const cleanQuery = query.trim();
    if (!cleanQuery) {
      setStatus("请输入一个地名。", "error");
      input.focus();
      return;
    }
    if (cleanQuery.length > core.MAX_QUERY_LENGTH) {
      setStatus(`查询词最多 ${core.MAX_QUERY_LENGTH} 个字符；请先整理分享内容中的地名。`, "error");
      input.focus();
      return;
    }

    const currentSequence = ++querySequence;
    results.hidden = true;
    fallbackLinks.hidden = true;
    rankingNote.hidden = true;
    resetMap();
    setBusy(true);
    setStatus("正在查找中英文地名与条目信息…");
    try {
      const response = await core.searchLocations(cleanQuery, context);
      if (currentSequence !== querySequence) return;
      if (!response.candidates.length) {
        results.hidden = true;
        setStatus(
          response.errors.length
            ? `没有找到结果，且部分数据源暂不可用：${response.errors.join("；")}。你可以重试或使用外部地图。`
            : "没有找到匹配条目。试试更短的地名，或保留输入并使用外部地图搜索。",
          "warning"
        );
        showFallbackLinks(cleanQuery);
        return;
      }
      renderCandidates(response.candidates, cleanQuery);
      if (response.errors.length) {
        setStatus(`显示可用结果，但部分来源暂不可用：${response.errors.join("；")}`, "warning");
      } else {
        setStatus(`找到 ${response.candidates.length} 个候选地点；请选择最符合你所指的地方。`);
      }
      const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
      results.scrollIntoView({ behavior: reducedMotion ? "auto" : "smooth", block: "start" });
    } catch (error) {
      if (currentSequence !== querySequence) return;
      results.hidden = true;
      setStatus(`查询失败：${error.message}。你的输入仍保留在框中，可以重试或使用外部地图。`, "error");
      showFallbackLinks(cleanQuery);
    } finally {
      if (currentSequence === querySequence) setBusy(false);
    }
  }

  function clearContext() {
    context = "";
    contextText.textContent = "";
    shareContext.hidden = true;
  }

  function applySharePayload() {
    const payload = core.readSharePayload(location.search);
    if (!payload.text && !payload.url && !payload.title) return;

    const sharedText = payload.text.trim();
    const pieces = [payload.title, payload.url].filter(Boolean);
    context = pieces.join("\n");
    shareContext.hidden = false;
    contextText.textContent = [sharedText, ...pieces].filter(Boolean).join("\n\n");
    history.replaceState(null, "", `${location.pathname}${location.hash}`);

    if (core.isShortShareText(sharedText)) {
      input.value = sharedText;
      setTimeout(() => search(sharedText), 0);
    } else {
      input.value = "";
      input.focus({ preventScroll: true });
      setStatus("已收到分享内容。请从中挑出一个地名填入上方，再开始查询。");
    }
    updateClearButton();
  }

  function updateClearButton() {
    clearButton.hidden = !input.value;
  }

  form.addEventListener("submit", (event) => {
    event.preventDefault();
    search(input.value);
  });
  input.addEventListener("input", updateClearButton);
  clearButton.addEventListener("click", () => {
    input.value = "";
    updateClearButton();
    results.hidden = true;
    fallbackLinks.hidden = true;
    setStatus("");
    input.focus();
  });
  document.getElementById("clear-context").addEventListener("click", clearContext);
  document.querySelector(".guide-close").addEventListener("click", () => {
    document.querySelector(".guide").open = false;
  });

  applySharePayload();
  updateClearButton();
})();
