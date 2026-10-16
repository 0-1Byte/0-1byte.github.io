"use strict";

const assert = require("node:assert/strict");
const test = require("node:test");
const core = require("../static/whereabouts/core.js");

test("share payload decodes Chinese text and reserved URL characters", () => {
  const params = new URLSearchParams();
  params.set("text", "霍尔木兹海峡 & Patagonia");
  params.set("title", "一篇新闻：海峡");
  params.set("url", "https://example.com/story?a=1&b=2");
  assert.deepEqual(core.readSharePayload(`?${params.toString()}`), {
    text: "霍尔木兹海峡 & Patagonia",
    title: "一篇新闻：海峡",
    url: "https://example.com/story?a=1&b=2"
  });
});

test("short shared place names tolerate punctuation and URLs", () => {
  assert.equal(core.isShortShareText("苏瓦乌基走廊"), true);
  assert.equal(core.isShortShareText("Where is Patagonia?"), true);
  assert.equal(core.isShortShareText("Praha — Poland\nhttps://example.com/story"), true);
  assert.equal(core.isShortShareText("A long article without punctuation ".repeat(3)), false);
  assert.equal(core.isShortShareText("A brief article about Patagonia with several extra words"), false);
  assert.equal(core.isShortShareText("https://example.com/georgia"), false);
});

test("share query is extracted from text, URL-wrapped text, or title fallback", () => {
  assert.equal(core.extractShareQuery({ text: "霍尔木兹海峡" }), "霍尔木兹海峡");
  assert.equal(core.extractShareQuery({ text: "Praha\nhttps://example.com/story" }), "Praha");
  assert.equal(core.extractShareQuery({
    text: "https://example.com/story",
    title: "苏瓦乌基走廊",
    url: "https://example.com/story"
  }), "苏瓦乌基走廊");
  assert.equal(core.extractShareQuery({ text: "", title: "Strait of Hormuz" }), "Strait of Hormuz");
  assert.equal(core.extractShareQuery({
    text: "A whole article body which has many words ".repeat(5),
    title: "A short article headline"
  }), "");
});
test("unverified or non-earth coordinates are not returned", () => {
  assert.deepEqual(core.findCoordinates({ coordinates: [{ lat: 31.2, lon: 61.1, globe: "earth" }] }), {
    lat: 31.2,
    lon: 61.1,
    dim: null
  });
  assert.equal(core.findCoordinates({ coordinates: [{ lat: 0, lon: 0, globe: "mars" }] }), null);
  assert.equal(core.findCoordinates({ coordinates: [{ lat: 91, lon: 0, globe: "earth" }] }), null);
  assert.equal(core.findCoordinates({}), null);
});

test("ranking favors exact matches while keeping same-name candidates selectable", () => {
  const candidates = core.rankCandidates([
    { title: "Georgia (U.S. state)", coordinates: { lat: 32, lon: -83 } },
    { title: "Georgia", coordinates: { lat: 42, lon: 43 } },
    { title: "Georgia (country)", coordinates: { lat: 42, lon: 43 } }
  ], "Georgia", "");
  assert.equal(candidates[0].title, "Georgia");
  assert.equal(candidates.length, 3);
  assert.ok(candidates.some((candidate) => candidate.title === "Georgia (U.S. state)"));
});

test("a disambiguation article does not outrank selectable geographic matches", () => {
  const candidates = core.rankCandidates([
    { title: "Georgia", isDisambiguation: true, coordinates: null },
    { title: "Georgia (country)", coordinates: { lat: 42, lon: 43 } },
    { title: "Georgia (U.S. state)", coordinates: { lat: 32, lon: -83 } }
  ], "Georgia", "Georgia");
  assert.equal(candidates[0].title, "Georgia (country)");
  assert.equal(candidates.at(-1).title, "Georgia");
  assert.equal(candidates.at(-1).isDisambiguation, true);
});

test("local article context can adjust ranking without altering the query", () => {
  const ranked = core.rankCandidates([
    { title: "Georgia (country)", extract: "A country in the Caucasus region." },
    { title: "Georgia (U.S. state)", extract: "A state in the southeastern United States." }
  ], "Georgia", "The story mentions Atlanta, Georgia and the United States.");
  assert.equal(ranked[0].title, "Georgia (U.S. state)");
});

test("map links use encoded search queries or verified coordinates", () => {
  const place = { title: "霍尔木兹海峡 & 海湾", coordinates: { lat: 26.56, lon: 56.25 } };
  const links = core.mapLinks(place, 8);
  assert.equal(new URL(links[0].href).searchParams.get("query"), "26.56,56.25");
  assert.equal(new URL(links[1].href).searchParams.get("q"), place.title);
  assert.equal(new URL(links[1].href).searchParams.get("ll"), "26.56,56.25");
  assert.match(links[2].href, /#map=8\/26\.56\/56\.25$/);

  const noCoords = core.mapLinks({ title: "苏瓦乌基走廊" }, 7);
  assert.equal(new URL(noCoords[0].href).searchParams.get("query"), "苏瓦乌基走廊");
  assert.equal(new URL(noCoords[1].href).searchParams.get("q"), "苏瓦乌基走廊");
  assert.equal(new URL(noCoords[2].href).searchParams.get("query"), "苏瓦乌基走廊");
});

test("API queries send only the submitted place term and request public CORS", () => {
  const url = new URL(core.apiUrl("https://en.wikipedia.org/w/api.php", {
    list: "search",
    srsearch: "Patagonia"
  }));
  assert.equal(url.searchParams.get("origin"), "*");
  assert.equal(url.searchParams.get("srsearch"), "Patagonia");
  assert.equal(url.searchParams.has("context"), false);
});

test("lookup handles a missing-coordinate result and partial service failure", async () => {
  const fetchMock = async (url) => {
    const parsed = new URL(url);
    if (parsed.hostname === "en.wikipedia.org") {
      if (parsed.searchParams.get("list") === "search") {
        return { ok: true, json: async () => ({ query: { search: [{ title: "Patagonia" }] } }) };
      }
      return {
        ok: true,
        json: async () => ({
          query: {
            redirects: [{ from: "Patagonia region", to: "Patagonia" }],
            pages: [{
              title: "Patagonia",
              extract: "A region at the southern end of South America.",
              fullurl: "https://en.wikipedia.org/wiki/Patagonia"
            }]
          }
        })
      };
    }
    if (parsed.hostname === "zh.wikipedia.org") throw new Error("simulated offline");
    if (parsed.hostname === "www.wikidata.org") return { ok: true, json: async () => ({ search: [] }) };
    throw new Error("Unexpected host " + parsed.hostname);
  };
  const result = await core.searchLocations("Patagonia", "", { fetch: fetchMock });
  assert.equal(result.candidates[0].title, "Patagonia");
  assert.equal(result.candidates[0].coordinates, null);
  assert.equal(result.candidates[0].extract, "A region at the southern end of South America.");
  assert.deepEqual(result.candidates[0].aliases, ["Patagonia region"]);
  assert.equal(result.errors.length, 1);
});
test("article extracts stay brief and do not end mid-word", async () => {
  const longText = `${"A concise location summary with neighboring regions. ".repeat(14)}`;
  const fetchMock = async (url) => {
    const parsed = new URL(url);
    if (parsed.hostname === "www.wikidata.org") {
      return { ok: true, json: async () => ({ search: [] }) };
    }
    return {
      ok: true,
      json: async () => parsed.searchParams.has("list")
        ? { query: { search: [{ title: "Example place" }] } }
        : { query: { pages: [{ title: "Example place", extract: longText }] } }
    };
  };
  const result = await core.searchLocations("Example place", "", { fetch: fetchMock });
  assert.ok(result.candidates[0].extract.length <= 421);
  assert.match(result.candidates[0].extract, /…$/u);
  assert.doesNotMatch(result.candidates[0].extract, /summar…$/u);
});

test("English queries search the English encyclopedia first", async () => {
  const urls = [];
  const fetchMock = async (url) => {
    urls.push(url);
    return { ok: true, json: async () => ({ query: { search: [] } }) };
  };
  await core.searchLocations("Patagonia", "", { fetch: fetchMock });
  assert.match(urls[0], /^https:\/\/en\.wikipedia\.org\//);
  assert.match(urls[1], /^https:\/\/zh\.wikipedia\.org\//);
  assert.ok(urls.some((url) => url.includes("www.wikidata.org") && url.includes("wbsearchentities")));
});


test("Wikidata finds a place by its native-language alias", async () => {
  const requests = [];
  const fetchMock = async (url) => {
    const parsed = new URL(url);
    requests.push(parsed);
    if (parsed.hostname === "www.wikidata.org" && parsed.searchParams.get("action") === "wbsearchentities") {
      return {
        ok: true,
        json: async () => ({
          search: [{
            id: "Q1085",
            label: "布拉格",
            description: "捷克首都",
            match: { type: "alias", language: "cs", text: "Praha" },
            score: 100
          }]
        })
      };
    }
    if (parsed.hostname === "www.wikidata.org" && parsed.searchParams.get("action") === "wbgetentities") {
      return {
        ok: true,
        json: async () => ({
          entities: {
            Q1085: {
              id: "Q1085",
              labels: {
                zh: { language: "zh", value: "布拉格" },
                en: { language: "en", value: "Prague" },
                cs: { language: "cs", value: "Praha" }
              },
              descriptions: {
                zh: { language: "zh", value: "捷克首都" },
                en: { language: "en", value: "capital of the Czech Republic" }
              },
              aliases: { cs: [{ language: "cs", value: "Praha" }] },
              claims: {
                P625: [{
                  rank: "preferred",
                  mainsnak: {
                    snaktype: "value",
                    datavalue: {
                      value: {
                        latitude: 50.0755,
                        longitude: 14.4378,
                        precision: 0.01,
                        globe: "http://www.wikidata.org/entity/Q2"
                      }
                    }
                  }
                }]
              },
              sitelinks: {}
            }
          }
        })
      };
    }
    if (parsed.hostname === "en.wikipedia.org" || parsed.hostname === "zh.wikipedia.org") {
      return { ok: true, json: async () => ({ query: { search: [] } }) };
    }
    throw new Error("Unexpected host " + parsed.hostname);
  };

  const result = await core.searchLocations("Praha", "", { fetch: fetchMock });
  const place = result.candidates[0];
  assert.equal(place.title, "布拉格");
  assert.equal(place.matchedName, "Praha");
  assert.equal(place.matchedLanguage, "cs");
  assert.ok(place.aliases.includes("Praha"));
  assert.deepEqual(place.coordinates, { lat: 50.0755, lon: 14.4378, dim: 1113.2 });
  assert.equal(requests.some((url) => url.searchParams.get("action") === "wbsearchentities"), true);
});

test("lookup rejects empty and overlong input without making a request", async () => {
  let requests = 0;
  const fetchMock = async () => { requests += 1; throw new Error("unexpected request"); };
  await assert.rejects(core.searchLocations("  ", "", { fetch: fetchMock }), /请输入/);
  await assert.rejects(core.searchLocations("x".repeat(101), "", { fetch: fetchMock }), /最多 100 个字符/);
  assert.equal(requests, 0);
});

test("lookup surfaces a source timeout instead of returning an empty success", async () => {
  const fetchMock = async (_url, { signal }) => new Promise((_resolve, reject) => {
    signal.addEventListener("abort", () => {
      const error = new Error("aborted");
      error.name = "AbortError";
      reject(error);
    }, { once: true });
  });
  await assert.rejects(core.searchLocations("Georgia", "", { fetch: fetchMock, timeoutMs: 5 }), /超时/);
});
