(function (root) {
  "use strict";

  const MAX_QUERY_LENGTH = 100;
  const MAX_EXTRACT_LENGTH = 420;
  const MAX_RESULTS_PER_LANGUAGE = 6;
  const REQUEST_TIMEOUT_MS = 8000;
  const WIKIDATA_ENDPOINT = "https://www.wikidata.org/w/api.php";
  const WIKIPEDIA = {
    zh: { label: "中文维基百科", endpoint: "https://zh.wikipedia.org/w/api.php" },
    en: { label: "English Wikipedia", endpoint: "https://en.wikipedia.org/w/api.php" }
  };

  function normalize(value) {
    return String(value || "")
      .normalize("NFKC")
      .toLocaleLowerCase()
      .replace(/[\s\p{P}\p{S}]+/gu, "");
  }

  function cleanSharedText(value) {
    return String(value || "")
      .replace(/[\u200B-\u200D\uFEFF]/gu, "")
      .replace(/(?:https?:\/\/|www\.)[^\s]+/giu, " ")
      .replace(/\s+/gu, " ")
      .trim()
      .replace(/^[\s"'“”‘’]+|[\s"'“”‘’]+$/gu, "")
      .trim();
  }

  function isShortShareText(value) {
    const text = cleanSharedText(value);
    if (!text || text.length > MAX_QUERY_LENGTH) return false;
    const words = text.match(/[\p{L}\p{N}]+/gu) || [];
    const hasHan = /[\p{Script=Han}]/u.test(text);
    return hasHan ? text.length <= 40 : words.length <= 8;
  }

  function extractShareQuery(payload) {
    const sharedText = String(payload && payload.text || "").trim();
    const text = cleanSharedText(sharedText);
    const title = cleanSharedText(payload && payload.title || "");
    if (text && isShortShareText(text)) return text;

    // Some share sheets put selected text in title, or put only a URL in text.
    const textContainsOnlyUrl = Boolean(sharedText) && !text;
    if ((!sharedText || textContainsOnlyUrl) && title && isShortShareText(title)) {
      return title;
    }
    return "";
  }
  function readSharePayload(search) {
    const params = new URLSearchParams(search || "");
    return {
      text: params.get("text") || "",
      title: params.get("title") || "",
      url: params.get("url") || ""
    };
  }

  function findCoordinates(page) {
    const coords = Array.isArray(page && page.coordinates) ? page.coordinates : [];
    const isEarth = (item) => !item.globe || /(?:\/|#)Q2$/u.test(String(item.globe));
    const valid = coords.filter((item) => item && isEarth(item));
    const point = valid.find((item) => item.primary === true) || valid[0];
    if (!point) return null;

    const lat = Number(point.lat);
    const lon = Number(point.lon);
    if (!Number.isFinite(lat) || !Number.isFinite(lon) || Math.abs(lat) > 90 || Math.abs(lon) > 180) {
      return null;
    }
    return { lat, lon, dim: Number.isFinite(Number(point.dim)) ? Number(point.dim) : null };
  }
  function conciseExtract(value) {
    const text = String(value || "").replace(/\s+/gu, " ").trim();
    if (text.length <= MAX_EXTRACT_LENGTH) return text;

    const prefix = text.slice(0, MAX_EXTRACT_LENGTH);
    const sentenceEnd = Math.max(
      prefix.lastIndexOf(". "),
      prefix.lastIndexOf("! "),
      prefix.lastIndexOf("? "),
      prefix.lastIndexOf("。"),
      prefix.lastIndexOf("！"),
      prefix.lastIndexOf("？")
    );
    if (sentenceEnd >= 160) return `${prefix.slice(0, sentenceEnd + 1).trim()}…`;

    const wordBoundary = prefix.lastIndexOf(" ");
    const end = wordBoundary > 160 ? wordBoundary : prefix.length;
    return `${prefix.slice(0, end).trimEnd()}…`;
  }

  function contextScore(candidate, context) {
    const normalizedContext = normalize(context);
    const title = normalize(candidate.title);
    if (!normalizedContext || !title) return 0;
    if (normalizedContext.includes(title)) return 16;

    const words = String(context).toLocaleLowerCase().match(/[\p{L}\p{N}]{4,}/gu) || [];
    const searchable = `${candidate.title} ${candidate.extract}`.toLocaleLowerCase();
    const matches = new Set(words.filter((word) => searchable.includes(word)));
    return Math.min(matches.size * 3, 12);
  }

  function rankCandidates(candidates, query, context) {
    const normalizedQuery = normalize(query);
    return candidates
      .map((candidate) => {
        const names = [candidate.title, candidate.matchedName, ...(candidate.aliases || [])]
          .filter(Boolean)
          .map(normalize);
        const exactNameMatch = names.includes(normalizedQuery);
        let score = normalize(candidate.title) === normalizedQuery ? 100 : 0;
        if (exactNameMatch) score = Math.max(score, 120);
        if (names.some((name) => name && normalizedQuery.length >= 3 &&
          (name.includes(normalizedQuery) || normalizedQuery.includes(name)))) score += 25;
        if (candidate.matchedName && normalize(candidate.matchedName) === normalizedQuery) score += 35;
        if (candidate.coordinates) score += 4;
        score += contextScore(candidate, context);
        return { ...candidate, score };
      })
      .sort((a, b) =>
        Number(Boolean(a.isDisambiguation)) - Number(Boolean(b.isDisambiguation)) ||
        b.score - a.score ||
        a.title.localeCompare(b.title)
      );
  }
  function apiUrl(endpoint, params) {
    const url = new URL(endpoint);
    for (const [key, value] of Object.entries({
      action: "query",
      format: "json",
      formatversion: "2",
      origin: "*",
      ...params
    })) {
      url.searchParams.set(key, value);
    }
    return url.toString();
  }

  async function requestJson(url, fetchImpl, timeoutMs) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeoutMs || REQUEST_TIMEOUT_MS);
    try {
      const response = await fetchImpl(url, {
        signal: controller.signal,
        credentials: "omit",
        headers: { "Api-User-Agent": "Whereabouts/1.0 (https://0-1byte.github.io/whereabouts/)" }
      });
      if (!response.ok) throw new Error(`数据服务返回 HTTP ${response.status}`);
      const data = await response.json();
      if (data.error) throw new Error(data.error.info || "数据服务返回错误");
      return data;
    } catch (error) {
      if (error && error.name === "AbortError") throw new Error("数据服务响应超时，请检查网络后重试");
      throw error;
    } finally {
      clearTimeout(timer);
    }
  }

  async function searchLanguage(query, language, fetchImpl, timeoutMs) {
    const wiki = WIKIPEDIA[language];
    const searchData = await requestJson(apiUrl(wiki.endpoint, {
      list: "search",
      srsearch: query,
      srlimit: String(MAX_RESULTS_PER_LANGUAGE),
      srnamespace: "0"
    }), fetchImpl, timeoutMs);
    const pages = searchData.query && searchData.query.search || [];
    if (!pages.length) return [];

    const detailData = await requestJson(apiUrl(wiki.endpoint, {
      prop: "coordinates|extracts|pageprops|info",
      inprop: "url",
      exintro: "1",
      explaintext: "1",
      exsentences: "3",
      redirects: "1",
      titles: pages.map((page) => page.title).join("|")
    }), fetchImpl, timeoutMs);
    const redirects = detailData.query && detailData.query.redirects || [];
    return (detailData.query && detailData.query.pages || [])
      .filter((page) => !page.missing && !page.invalid)
      .map((page) => ({
        title: page.title,
        extract: conciseExtract(page.extract),
        coordinates: findCoordinates(page),
        sourceUrl: page.fullurl || `https://${language}.wikipedia.org/wiki/${encodeURIComponent(page.title.replace(/ /g, "_"))}`,
        sourceLabel: wiki.label,
        language,
        aliases: redirects.filter((redirect) => redirect.to === page.title).map((redirect) => redirect.from),
        wikidataId: page.pageprops && page.pageprops.wikibase_item || "",
        isDisambiguation: Boolean(page.pageprops && Object.prototype.hasOwnProperty.call(page.pageprops, "disambiguation"))
      }));
  }

  function mergeCandidates(candidates) {
    const merged = new Map();
    for (const candidate of candidates) {
      const key = candidate.wikidataId || (candidate.language + ":" + normalize(candidate.title));
      const existing = merged.get(key);
      if (!existing) {
        merged.set(key, { ...candidate, aliases: [...new Set(candidate.aliases || [])] });
        continue;
      }

      const aliases = [...(candidate.aliases || []), candidate.title, candidate.matchedName];
      for (const alias of aliases) {
        if (alias && normalize(alias) !== normalize(existing.title) &&
            !existing.aliases.some((name) => normalize(name) === normalize(alias))) {
          existing.aliases.push(alias);
        }
      }
      if (!existing.matchedName && candidate.matchedName) existing.matchedName = candidate.matchedName;
      if (!existing.coordinates && candidate.coordinates) existing.coordinates = candidate.coordinates;
      if (!existing.wikidataId && candidate.wikidataId) existing.wikidataId = candidate.wikidataId;
      if (candidate.isDisambiguation) existing.isDisambiguation = true;
      if (candidate.extract && (!existing.extract || candidate.extract.length > existing.extract.length)) {
        existing.extract = candidate.extract;
        if (candidate.sourceLabel && candidate.sourceLabel !== "Wikidata") {
          existing.sourceLabel = candidate.sourceLabel;
          existing.sourceUrl = candidate.sourceUrl || existing.sourceUrl;
          existing.language = candidate.language || existing.language;
        }
      }
      if (candidate.sourceUrl && !existing.sourceUrl) existing.sourceUrl = candidate.sourceUrl;
    }
    return [...merged.values()];
  }

  function findWikidataCoordinates(entity) {
    const claims = entity && entity.claims && entity.claims.P625;
    if (!Array.isArray(claims)) return null;

    const statements = claims
      .filter((statement) =>
        statement && statement.rank !== "deprecated" &&
        statement.mainsnak && statement.mainsnak.snaktype === "value" &&
        statement.mainsnak.datavalue && statement.mainsnak.datavalue.value
      )
      .sort((a, b) => Number(b.rank === "preferred") - Number(a.rank === "preferred"));

    for (const statement of statements) {
      const point = statement.mainsnak.datavalue.value;
      const globe = String(point.globe || "");
      if (globe && !/(?:\/|#)Q2$/u.test(globe)) continue;

      const lat = Number(point.latitude);
      const lon = Number(point.longitude);
      if (!Number.isFinite(lat) || !Number.isFinite(lon) ||
          Math.abs(lat) > 90 || Math.abs(lon) > 180) continue;

      const precision = Number(point.precision);
      return {
        lat,
        lon,
        dim: Number.isFinite(precision) && precision > 0 ? precision * 111320 : null
      };
    }
    return null;
  }

  async function searchWikidata(query, fetchImpl, timeoutMs) {
    const searchLanguage = /[\p{Script=Han}]/u.test(query) ? "zh" : "en";
    const searchData = await requestJson(apiUrl(WIKIDATA_ENDPOINT, {
      action: "wbsearchentities",
      search: query,
      language: searchLanguage,
      uselang: "zh",
      type: "item",
      limit: String(MAX_RESULTS_PER_LANGUAGE)
    }), fetchImpl, timeoutMs);

    const hits = (searchData.search || [])
      .filter((hit) => hit && /^Q\d+$/u.test(String(hit.id || "")));
    if (!hits.length) return { candidates: [], error: "" };

    const matchedLanguages = hits
      .map((hit) => hit.match && hit.match.language)
      .filter((language) => typeof language === "string" && /^[a-zA-Z0-9-]{2,12}$/u.test(language));
    const requestedLanguages = [...new Set(["zh", "en", ...matchedLanguages])];
    let entities = {};
    let detailError = "";

    try {
      const detailData = await requestJson(apiUrl(WIKIDATA_ENDPOINT, {
        action: "wbgetentities",
        ids: hits.map((hit) => hit.id).join("|"),
        props: "labels|descriptions|aliases|claims|sitelinks",
        languages: requestedLanguages.join("|"),
        languagefallback: "1"
      }), fetchImpl, timeoutMs);
      entities = detailData.entities || {};
    } catch (error) {
      detailError = "Wikidata 详细信息：" + error.message;
    }

    const candidates = hits.map((hit) => {
      const entity = entities[hit.id] || {};
      const labels = entity.labels || {};
      const descriptions = entity.descriptions || {};
      const matchedLanguage = hit.match && hit.match.language || "";
      const title =
        (labels.zh && labels.zh.value) ||
        (matchedLanguage && labels[matchedLanguage] && labels[matchedLanguage].value) ||
        (labels.en && labels.en.value) ||
        hit.label ||
        (hit.match && hit.match.text) ||
        hit.id;

      const aliases = new Set();
      const matchedName = hit.match && hit.match.text || query;
      if (matchedName && normalize(matchedName) !== normalize(title)) aliases.add(matchedName);
      for (const language of requestedLanguages) {
        const label = labels[language] && labels[language].value;
        if (label && normalize(label) !== normalize(title)) aliases.add(label);
        for (const alias of (entity.aliases && entity.aliases[language]) || []) {
          if (alias && alias.value && normalize(alias.value) !== normalize(title)) aliases.add(alias.value);
        }
      }

      const description =
        (descriptions.zh && descriptions.zh.value) ||
        (matchedLanguage && descriptions[matchedLanguage] && descriptions[matchedLanguage].value) ||
        (descriptions.en && descriptions.en.value) ||
        hit.description ||
        "";
      const instanceClaims = entity.claims && entity.claims.P31 || [];
      const isDisambiguation = instanceClaims.some((statement) =>
        statement && statement.mainsnak && statement.mainsnak.datavalue &&
        statement.mainsnak.datavalue.value &&
        statement.mainsnak.datavalue.value.id === "Q4167410"
      );

      return {
        title,
        matchedName,
        matchedLanguage,
        aliases: [...aliases].slice(0, 10),
        extract: conciseExtract(description),
        coordinates: findWikidataCoordinates(entity),
        sourceUrl: "https://www.wikidata.org/wiki/" + hit.id,
        sourceLabel: "Wikidata",
        language: matchedLanguage || searchLanguage,
        wikidataId: hit.id,
        isDisambiguation
      };
    });

    return { candidates, error: detailError };
  }

  
  async function searchLocations(query, context, options) {
    const cleanQuery = String(query || "").trim();
    if (!cleanQuery) throw new Error("请输入一个地名。");
    if (cleanQuery.length > MAX_QUERY_LENGTH) {
      throw new Error("查询词最多 " + MAX_QUERY_LENGTH + " 个字符；请先从分享内容中挑出地名。");
    }

    const fetchImpl = options && options.fetch || root.fetch.bind(root);
    const timeoutMs = options && options.timeoutMs;
    const candidates = [];
    const errors = [];
    let successfulSources = 0;
    const languages = /[\p{Script=Han}]/u.test(cleanQuery) ? ["zh", "en"] : ["en", "zh"];

    const tasks = languages.map(async (language) => {
      try {
        const results = await searchLanguage(cleanQuery, language, fetchImpl, timeoutMs);
        successfulSources += 1;
        candidates.push(...results);
      } catch (error) {
        errors.push(WIKIPEDIA[language].label + "：" + error.message);
      }
    });

    tasks.push((async () => {
      try {
        const result = await searchWikidata(cleanQuery, fetchImpl, timeoutMs);
        successfulSources += 1;
        candidates.push(...result.candidates);
        if (result.error) errors.push(result.error);
      } catch (error) {
        errors.push("Wikidata：" + error.message);
      }
    })());

    await Promise.all(tasks);
    const ranked = rankCandidates(mergeCandidates(candidates), cleanQuery, context);
    if (!ranked.length && successfulSources === 0) {
      throw new Error(errors.join("；") || "地名数据源暂时不可用，请稍后重试。");
    }
    return { candidates: ranked, errors };
  }
  function mapLinks(candidate, zoom) {
    const coords = candidate.coordinates;
    const query = coords ? `${coords.lat},${coords.lon}` : candidate.title;
    const google = new URL("https://www.google.com/maps/search/");
    google.searchParams.set("api", "1");
    google.searchParams.set("query", query);

    const apple = new URL("https://maps.apple.com/");
    apple.searchParams.set("q", candidate.title);
    if (coords) apple.searchParams.set("ll", `${coords.lat},${coords.lon}`);

    const osm = coords
      ? `https://www.openstreetmap.org/?mlat=${encodeURIComponent(coords.lat)}&mlon=${encodeURIComponent(coords.lon)}#map=${zoom || 8}/${coords.lat}/${coords.lon}`
      : `https://www.openstreetmap.org/search?query=${encodeURIComponent(candidate.title)}`;
    return [
      { label: "Google Maps", href: google.toString() },
      { label: "Apple 地图", href: apple.toString() },
      { label: "OpenStreetMap", href: osm }
    ];
  }

  const exported = {
    MAX_QUERY_LENGTH,
    apiUrl,
    findCoordinates,
    cleanSharedText,
    extractShareQuery,
    findWikidataCoordinates,
    isShortShareText,
    mapLinks,
    normalize,
    rankCandidates,
    readSharePayload,
    searchLocations
  };
  if (typeof module !== "undefined" && module.exports) module.exports = exported;
  root.WhereaboutsCore = exported;
})(typeof globalThis !== "undefined" ? globalThis : this);
