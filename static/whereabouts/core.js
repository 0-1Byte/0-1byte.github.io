(function (root) {
  "use strict";

  const MAX_QUERY_LENGTH = 100;
  const MAX_EXTRACT_LENGTH = 420;
  const MAX_RESULTS_PER_LANGUAGE = 6;
  const REQUEST_TIMEOUT_MS = 8000;
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

  function isShortShareText(value) {
    const text = String(value || "").trim();
    const words = text.match(/[\p{L}\p{N}]+/gu) || [];
    const isCjk = /[\p{Script=Han}]/u.test(text);
    return Boolean(
      text &&
      text.length <= 80 &&
      (isCjk ? text.length <= 20 : words.length <= 5) &&
      !/https?:\/\/|[\r\n。！？!?；;]/iu.test(text)
    );
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
    const point = coords.find((item) => item && item.primary !== "") || coords[0];
    if (!point || point.globe && point.globe !== "earth") return null;

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
        const title = normalize(candidate.title);
        let score = title === normalizedQuery ? 100 : 0;
        if (title && normalizedQuery && title.includes(normalizedQuery)) score += 25;
        if (candidate.coordinates) score += 4;
        score += contextScore(candidate, context);
        return { ...candidate, score };
      })
      .sort((a, b) => b.score - a.score || a.title.localeCompare(b.title));
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
        wikidataId: page.pageprops && page.pageprops.wikibase_item || ""
      }));
  }

  function mergeCandidates(candidates) {
    const merged = new Map();
    for (const candidate of candidates) {
      const key = candidate.wikidataId || `${candidate.language}:${normalize(candidate.title)}`;
      const existing = merged.get(key);
      if (!existing) {
        merged.set(key, { ...candidate, aliases: [...(candidate.aliases || [])] });
        continue;
      }

      for (const alias of candidate.aliases || []) {
        if (!existing.aliases.includes(alias)) existing.aliases.push(alias);
      }
      if (candidate.title !== existing.title && !existing.aliases.includes(candidate.title)) {
        existing.aliases.push(candidate.title);
      }
      if (!existing.extract && candidate.extract) existing.extract = candidate.extract;
      if (!existing.coordinates && candidate.coordinates) existing.coordinates = candidate.coordinates;
      if (!existing.wikidataId && candidate.wikidataId) existing.wikidataId = candidate.wikidataId;
    }
    return [...merged.values()];
  }

  async function searchLocations(query, context, options) {
    const cleanQuery = String(query || "").trim();
    if (!cleanQuery) throw new Error("请输入一个地名。");
    if (cleanQuery.length > MAX_QUERY_LENGTH) {
      throw new Error(`查询词最多 ${MAX_QUERY_LENGTH} 个字符；请先从分享内容中挑出地名。`);
    }

    const fetchImpl = options && options.fetch || root.fetch.bind(root);
    const timeoutMs = options && options.timeoutMs;
    const candidates = [];
    const errors = [];
    const languages = /[\p{Script=Han}]/u.test(cleanQuery) ? ["zh", "en"] : ["en", "zh"];
    for (const language of languages) {
      try {
        candidates.push(...await searchLanguage(cleanQuery, language, fetchImpl, timeoutMs));
      } catch (error) {
        errors.push(`${WIKIPEDIA[language].label}：${error.message}`);
      }
    }

    const ranked = rankCandidates(mergeCandidates(candidates), cleanQuery, context);
    if (!ranked.length && errors.length === 2) {
      throw new Error(errors.join("；"));
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
