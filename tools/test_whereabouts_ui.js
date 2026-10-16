"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");
const core = require("../static/whereabouts/core.js");

class FakeElement {
  constructor(tagName = "div") {
    this.tagName = tagName.toUpperCase();
    this.children = [];
    this.listeners = {};
    this.attributes = {};
    this.dataset = {};
    this.hidden = false;
    this.disabled = false;
    this.open = false;
    this.value = "";
    this._textContent = "";
  }

  set textContent(value) {
    this._textContent = String(value);
    this.children = [];
  }

  get textContent() {
    return this._textContent + this.children.map((child) => child.textContent || "").join("");
  }

  set innerText(value) {
    this.textContent = value;
  }

  get innerText() {
    return this.textContent;
  }

  append(...items) {
    for (const item of items) {
      if (item && typeof item === "object") this.children.push(item);
    }
  }

  replaceChildren(...items) {
    this.children = [];
    this._textContent = "";
    this.append(...items);
  }

  setAttribute(name, value) {
    this.attributes[name] = String(value);
  }

  getAttribute(name) {
    return this.attributes[name] ?? null;
  }

  addEventListener(name, callback) {
    (this.listeners[name] ||= []).push(callback);
  }

  querySelectorAll(selector) {
    const className = selector.startsWith(".") ? selector.slice(1) : null;
    const found = [];
    const visit = (node) => {
      for (const child of node.children) {
        if (className && child.className?.split(/\s+/u).includes(className)) found.push(child);
        visit(child);
      }
    };
    visit(this);
    return found;
  }

  querySelector(selector) {
    return this.querySelectorAll(selector)[0] || null;
  }

  focus() {}

  scrollIntoView() {
    this.wasScrolledIntoView = true;
  }
}

function candidate(title, lat, lon, extract = `${title} geographic background.`) {
  return {
    title,
    aliases: [],
    coordinates: lat === null ? null : { lat, lon, dim: 5000 },
    extract,
    sourceLabel: "Wikipedia",
    sourceUrl: `https://en.wikipedia.org/wiki/${encodeURIComponent(title)}`
  };
}

function createLeafletStub() {
  const instances = [];
  const leaflet = {
    map(element) {
      if (element._leaflet_id) throw new Error("Map container already initialized.");
      element._leaflet_id = instances.length + 1;
      const instance = {
        element,
        center: null,
        zoom: null,
        marker: null,
        handlers: {},
        removed: false,
        invalidations: 0,
        setView(center, zoom) {
          this.center = center;
          this.zoom = zoom;
          return this;
        },
        on(name, callback) {
          (this.handlers[name] ||= []).push(callback);
          return this;
        },
        invalidateSize() {
          this.invalidations += 1;
        },
        remove() {
          this.removed = true;
          this.element._leaflet_id = null;
        },
        emit(name) {
          for (const callback of this.handlers[name] || []) callback();
        }
      };
      instances.push(instance);
      return instance;
    },
    tileLayer(url) {
      const layer = {
        handlers: {},
        on(name, callback) {
          (this.handlers[name] ||= []).push(callback);
          return this;
        },
        addTo(map) {
          map.tileLayerUrl = url;
          map.tileLayer = this;
          return this;
        },
        emit(name) {
          for (const callback of this.handlers[name] || []) callback();
        }
      };
      return layer;
    },
    circleMarker(center) {
      return {
        addTo(map) {
          map.marker = { center };
          return { bindTooltip: (title) => { map.marker.title = title; } };
        }
      };
    }
  };
  return { leaflet, instances };
}

function createApp({ leaflet = createLeafletStub().leaflet, searchResults, locationSearch = "" }) {
  const ids = [
    "search-form", "place-query", "clear-query", "status", "results", "results-title",
    "result-count", "candidate-summary-count", "candidate-picker", "candidate-list",
    "place-detail", "fallback-links", "share-context", "context-text", "ranking-note",
    "clear-context"
  ];
  const elements = Object.fromEntries(ids.map((id) => [id, new FakeElement(id === "search-form" ? "form" : "div")]));
  const submit = new FakeElement("button");
  elements["search-form"].querySelector = () => submit;
  const allCandidates = new FakeElement();
  elements["candidate-picker"].append(allCandidates);
  const guideClose = new FakeElement("button");
  const guide = new FakeElement("details");
  const document = {
    getElementById(id) {
      return elements[id];
    },
    querySelector(selector) {
      return selector === ".guide-close" ? guideClose : selector === ".guide" ? guide : null;
    },
    createElement(tagName) {
      return new FakeElement(tagName);
    },
    createTextNode(text) {
      const node = new FakeElement("#text");
      node.textContent = text;
      return node;
    }
  };
  const pendingObservers = [];
  const context = {
    document,
    window: {
      WhereaboutsCore: {
        ...core,
        MAX_QUERY_LENGTH: 100,
        async searchLocations(query) {
          return { candidates: searchResults[query] || [], errors: [] };
        }
      },
      L: leaflet,
      matchMedia: () => ({ matches: true })
    },
    location: { search: locationSearch, pathname: "/whereabouts/" },
    history: { replaceState() {} },
    URLSearchParams,
    ResizeObserver: class {
      constructor(callback) {
        this.callback = callback;
        pendingObservers.push(this);
      }
      observe(element) {
        this.element = element;
      }
      disconnect() {
        this.disconnected = true;
      }
    },
    requestAnimationFrame(callback) {
      callback();
    },
    setTimeout,
    console: { error() {} }
  };
  const appPath = path.join(__dirname, "..", "static", "whereabouts", "app.js");
  vm.runInNewContext(fs.readFileSync(appPath, "utf8"), context, { filename: appPath });

  async function search(query) {
    elements["place-query"].value = query;
    const event = { preventDefault() {} };
    elements["search-form"].listeners.submit[0](event);
    await new Promise((resolve) => setImmediate(resolve));
  }

  return { elements, submit, guide, pendingObservers, search };
}

test("Chinese and English searches immediately show a real map and selected place", async () => {
  const { leaflet, instances } = createLeafletStub();
  const app = createApp({
    leaflet,
    searchResults: {
      "霍尔木兹海峡": [candidate("霍尔木兹海峡", 26.56, 56.25)],
      Patagonia: [candidate("Patagonia", -41.81, -68.91)]
    }
  });

  await app.search("霍尔木兹海峡");
  assert.equal(app.elements["place-detail"].querySelector(".detail-title").textContent, "霍尔木兹海峡");
  assert.deepEqual(Array.from(instances[0].center), [26.56, 56.25]);
  assert.deepEqual(Array.from(instances[0].marker.center), [26.56, 56.25]);
  assert.equal(instances[0].invalidations, 1);
  assert.match(app.elements["place-detail"].textContent, /简明背景/u);
  assert.match(app.elements["place-detail"].textContent, /OpenStreetMap contributors/u);
  assert.equal(app.elements["candidate-picker"].open, false);

  await app.search("Patagonia");
  assert.equal(app.elements["place-detail"].querySelector(".detail-title").textContent, "Patagonia");
  assert.deepEqual(Array.from(instances[1].center), [-41.81, -68.91]);
  assert.equal(instances[0].removed, true);
});

test("Georgia defaults to a marked candidate and switching updates coordinates and map links", async () => {
  const { leaflet, instances } = createLeafletStub();
  const georgia = candidate("Georgia", 42.3154, 43.3569);
  const usState = candidate("Georgia (U.S. state)", 32.1656, -82.9001);
  const app = createApp({ leaflet, searchResults: { Georgia: [georgia, usState] } });

  await app.search("Georgia");
  assert.equal(app.elements["place-detail"].querySelector(".selected-label").textContent, "暂选结果 · 最相关匹配");
  assert.deepEqual(Array.from(instances[0].marker.center), [42.3154, 43.3569]);
  const initialLinks = app.elements["place-detail"].querySelectorAll(".map-link");
  assert.equal(new URL(initialLinks[0].href).searchParams.get("query"), "42.3154,43.3569");

  const alternatives = app.elements["candidate-list"].querySelectorAll(".candidate");
  alternatives[1].listeners.click[0]();
  assert.equal(instances[0].removed, true);
  assert.deepEqual(Array.from(instances[1].center), [32.1656, -82.9001]);
  assert.equal(app.elements["place-detail"].querySelector(".detail-title").textContent, usState.title);
  assert.equal(app.elements["place-detail"].querySelector(".selected-label").textContent, "已切换候选地点");
  assert.equal(alternatives[1].getAttribute("aria-pressed"), "true");
  const updatedLinks = app.elements["place-detail"].querySelectorAll(".map-link");
  assert.equal(new URL(updatedLinks[0].href).searchParams.get("query"), "32.1656,-82.9001");
});

test("a candidate without coordinates never inherits the previous marker or coordinates", async () => {
  const { leaflet, instances } = createLeafletStub();
  const app = createApp({
    leaflet,
    searchResults: {
      Georgia: [candidate("Georgia", 42.3154, 43.3569), candidate("Georgia (region)", null, null)]
    }
  });
  await app.search("Georgia");
  app.elements["candidate-list"].querySelectorAll(".candidate")[1].listeners.click[0]();

  assert.equal(instances[0].removed, true);
  assert.equal(instances.length, 1);
  assert.equal(app.elements["place-detail"].querySelector(".map"), null);
  assert.match(app.elements["place-detail"].textContent, /暂无可靠坐标/u);
  const links = app.elements["place-detail"].querySelectorAll(".map-link");
  assert.equal(links.length, 3);
  assert.equal(new URL(links[0].href).searchParams.get("query"), "Georgia (region)");
  assert.equal(app.elements["place-detail"].querySelector(".coordinate"), null);
});

test("repeated searches destroy old Leaflet instances without container reuse", async () => {
  const { leaflet, instances } = createLeafletStub();
  const app = createApp({
    leaflet,
    searchResults: { Patagonia: [candidate("Patagonia", -41.81, -68.91)] }
  });
  for (let index = 0; index < 4; index += 1) await app.search("Patagonia");
  assert.equal(instances.length, 4);
  assert.equal(instances.filter((instance) => instance.removed).length, 3);
  assert.equal(app.elements["place-detail"].querySelectorAll(".map").length, 1);
});

test("missing Leaflet and tile failures show an explanation while preserving external links", async () => {
  const appWithoutLeaflet = createApp({
    leaflet: null,
    searchResults: { Patagonia: [candidate("Patagonia", -41.81, -68.91)] }
  });
  await appWithoutLeaflet.search("Patagonia");
  assert.match(appWithoutLeaflet.elements["place-detail"].querySelector(".map-error").textContent, /交互地图暂不可用/u);
  assert.equal(appWithoutLeaflet.elements["place-detail"].querySelectorAll(".map-link").length, 3);

  const { leaflet, instances } = createLeafletStub();
  const appWithTiles = createApp({
    leaflet,
    searchResults: { Patagonia: [candidate("Patagonia", -41.81, -68.91)] }
  });
  await appWithTiles.search("Patagonia");
  instances[0].tileLayer.emit("tileerror");
  assert.match(appWithTiles.elements["place-detail"].querySelector(".map-error").textContent, /瓦片加载失败/u);
  assert.equal(appWithTiles.elements["place-detail"].querySelectorAll(".map-link").length, 3);
});


test("sharing a selected place automatically searches from text or title without retyping", async () => {
  const { leaflet, instances } = createLeafletStub();
  const fromText = createApp({
    leaflet,
    locationSearch: "?text=Krak%C3%B3w%0Ahttps%3A%2F%2Fexample.com%2Fstory&title=Local+news&url=https%3A%2F%2Fexample.com%2Fstory",
    searchResults: { "Kraków": [candidate("克拉科夫", 50.0614, 19.9366)] }
  });
  await new Promise((resolve) => setTimeout(resolve, 10));
  assert.equal(fromText.elements["place-query"].value, "Kraków");
  assert.equal(fromText.elements.results.hidden, false);
  assert.equal(fromText.elements["place-detail"].querySelector(".detail-title").textContent, "克拉科夫");
  assert.equal(fromText.elements["share-context"].hidden, true);
  assert.equal(instances.length, 1);

  const titleLeaflet = createLeafletStub();
  const fromTitle = createApp({
    leaflet: titleLeaflet.leaflet,
    locationSearch: "?text=https%3A%2F%2Fexample.com%2Fstory&title=%E9%9C%8D%E5%B0%94%E6%9C%A8%E5%85%B9%E6%B5%B7%E5%B3%A1&url=https%3A%2F%2Fexample.com%2Fstory",
    searchResults: { "霍尔木兹海峡": [candidate("霍尔木兹海峡", 26.56, 56.25)] }
  });
  await new Promise((resolve) => setTimeout(resolve, 10));
  assert.equal(fromTitle.elements["place-query"].value, "霍尔木兹海峡");
  assert.equal(fromTitle.elements.results.hidden, false);
  assert.equal(fromTitle.elements["place-detail"].querySelector(".detail-title").textContent, "霍尔木兹海峡");
  assert.equal(titleLeaflet.instances.length, 1);
});



test("Shanghai search immediately renders the correct city map", async () => {
  const { leaflet, instances } = createLeafletStub();
  const app = createApp({
    leaflet,
    searchResults: {
      "上海": [candidate("上海市", 31.2304, 121.4737, "行政区划：中国")]
    }
  });
  await app.search("上海");
  assert.equal(app.elements["place-detail"].querySelector(".detail-title").textContent, "上海市");
  assert.deepEqual(Array.from(instances[0].center), [31.2304, 121.4737]);
  assert.match(app.elements["place-detail"].textContent, /上海市/u);
});
