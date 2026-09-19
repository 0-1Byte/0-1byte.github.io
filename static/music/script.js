const state = {
  songs: [],
  filteredSongs: [],
  category: "All",
  query: "",
  currentIndex: -1,
  shuffle: localStorage.getItem("music-shuffle") === "true",
  repeat: localStorage.getItem("music-repeat") || "off",
  volume: Number(localStorage.getItem("music-volume") ?? 0.8),
};

const audio = document.querySelector("#audio");
const songList = document.querySelector("#song-list");
const emptyState = document.querySelector("#empty-state");
const categoryTabs = document.querySelector("#category-tabs");
const searchInput = document.querySelector("#search-input");
const songCount = document.querySelector("#song-count");
const visibleCount = document.querySelector("#visible-count");
const listTitle = document.querySelector("#list-title");

const playerCover = document.querySelector("#player-cover");
const playerTitle = document.querySelector("#player-title");
const playerArtist = document.querySelector("#player-artist");
const playerNote = document.querySelector("#player-note");
const playerLinks = document.querySelector("#player-links");

const progress = document.querySelector("#progress");
const currentTime = document.querySelector("#current-time");
const duration = document.querySelector("#duration");
const volume = document.querySelector("#volume");
const volumeValue = document.querySelector("#volume-value");

const playBtn = document.querySelector("#play-btn");
const prevBtn = document.querySelector("#prev-btn");
const nextBtn = document.querySelector("#next-btn");
const shuffleBtn = document.querySelector("#shuffle-btn");
const repeatBtn = document.querySelector("#repeat-btn");
const themeToggle = document.querySelector("#theme-toggle");

const fmtTime = (seconds) => {
  if (!Number.isFinite(seconds)) return "0:00";
  const mins = Math.floor(seconds / 60);
  const secs = Math.floor(seconds % 60).toString().padStart(2, "0");
  return `${mins}:${secs}`;
};

function setRangeFill(el, percent) {
  el.style.setProperty("--fill", `${percent}%`);
}

function savePlayerState() {
  localStorage.setItem("music-volume", String(state.volume));
  localStorage.setItem("music-shuffle", String(state.shuffle));
  localStorage.setItem("music-repeat", state.repeat);
  if (state.currentIndex >= 0 && state.songs[state.currentIndex]) {
    localStorage.setItem("music-last-song", state.songs[state.currentIndex].id ?? "");
    localStorage.setItem("music-last-time", String(audio.currentTime || 0));
  }
}

async function loadSongs() {
  try {
    const res = await fetch("./songs.json", { cache: "no-store" });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    state.songs = await res.json();
    state.songs = state.songs.filter(song => song && song.title);

    songCount.textContent = `${state.songs.length} song${state.songs.length === 1 ? "" : "s"}`;
    buildCategoryTabs();
    restoreLastSong();
    applyFilters();
  } catch (err) {
    console.error(err);
    songList.innerHTML = `
      <div class="empty-state">
        无法读取 <code>songs.json</code>。如果你直接双击 index.html 打开，
        请改用 GitHub Pages 或本地静态服务器访问。
      </div>`;
  }
}

function buildCategoryTabs() {
  const categories = ["All", ...new Set(
    state.songs.flatMap(song => Array.isArray(song.tags) ? song.tags : [song.category || "Other"])
      .filter(Boolean)
  )];

  categoryTabs.innerHTML = categories.map(category => `
    <button
      class="tab ${category === state.category ? "active" : ""}"
      type="button"
      role="tab"
      aria-selected="${category === state.category}"
      data-category="${escapeHtml(category)}"
    >${escapeHtml(category)}</button>
  `).join("");

  categoryTabs.querySelectorAll(".tab").forEach(btn => {
    btn.addEventListener("click", () => {
      state.category = btn.dataset.category;
      buildCategoryTabs();
      applyFilters();
    });
  });
}

function applyFilters() {
  const q = state.query.trim().toLowerCase();

  state.filteredSongs = state.songs.filter(song => {
    const tags = Array.isArray(song.tags) ? song.tags : [song.category].filter(Boolean);
    const categoryMatch = state.category === "All" || tags.includes(state.category);
    const text = [
      song.title, song.artist, song.album, song.note, song.year, ...tags
    ].filter(Boolean).join(" ").toLowerCase();
    return categoryMatch && (!q || text.includes(q));
  });

  visibleCount.textContent = String(state.filteredSongs.length);
  listTitle.textContent = state.category === "All" ? "All songs" : state.category;

  renderSongList();
}

function renderSongList() {
  if (!state.filteredSongs.length) {
    songList.innerHTML = "";
    emptyState.classList.remove("hidden");
    return;
  }

  emptyState.classList.add("hidden");

  songList.innerHTML = state.filteredSongs.map((song, filteredIndex) => {
    const globalIndex = state.songs.findIndex(item => item.id === song.id);
    const isPlaying = globalIndex === state.currentIndex;
    return `
      <article class="song-row ${isPlaying ? "playing" : ""}" data-index="${globalIndex}" tabindex="0">
        <img class="cover" src="${escapeAttr(song.cover || "./assets/cover-placeholder.svg")}" alt="${escapeAttr(song.title)} 封面" loading="lazy">
        <div class="song-main">
          <div class="song-title">${escapeHtml(song.title)}</div>
          <div class="song-subtitle">${escapeHtml(song.artist || "Unknown artist")} · ${escapeHtml(song.album || "Single")}</div>
        </div>
        <div class="song-side">${escapeHtml(String(song.year || ""))}</div>
        <button class="song-play" type="button" aria-label="${isPlaying && !audio.paused ? "暂停" : "播放"}">
          ${isPlaying && !audio.paused ? "❚❚" : "▶"}
        </button>
      </article>
    `;
  }).join("");

  songList.querySelectorAll(".song-row").forEach(row => {
    const index = Number(row.dataset.index);
    row.addEventListener("click", () => playSong(index));
    row.addEventListener("keydown", event => {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        playSong(index);
      }
    });
  });
}

function updatePlayer(song) {
  if (!song) return;

  playerTitle.textContent = song.title || "Untitled";
  playerArtist.textContent = [song.artist, song.album].filter(Boolean).join(" · ") || "Unknown";
  playerCover.src = song.cover || "./assets/cover-placeholder.svg";
  playerCover.alt = `${song.title || "Current song"} 封面`;

  playerNote.textContent = song.note || "";
  playerNote.classList.toggle("hidden", !song.note);

  const links = [];
  if (song.youtube) links.push(`<a href="${escapeAttr(song.youtube)}" target="_blank" rel="noopener noreferrer">YouTube</a>`);
  if (song.spotify) links.push(`<a href="${escapeAttr(song.spotify)}" target="_blank" rel="noopener noreferrer">Spotify</a>`);
  if (song.appleMusic) links.push(`<a href="${escapeAttr(song.appleMusic)}" target="_blank" rel="noopener noreferrer">Apple Music</a>`);
  playerLinks.innerHTML = links.join("");
}

function playSong(index, autoplay = true) {
  const song = state.songs[index];
  if (!song) return;

  state.currentIndex = index;
  updatePlayer(song);
  renderSongList();

  if (song.audio) {
    audio.src = song.audio;
    audio.load();
    if (autoplay) audio.play().catch(err => console.warn("Playback blocked:", err));
  } else {
    audio.removeAttribute("src");
    audio.load();
    if (autoplay) console.warn(`No audio file configured for "${song.title}".`);
  }

  savePlayerState();
}

function togglePlay() {
  if (state.currentIndex < 0) {
    const first = state.filteredSongs[0];
    if (!first) return;
    playSong(state.songs.findIndex(song => song.id === first.id));
    return;
  }

  if (!audio.src) {
    playSong(state.currentIndex);
    return;
  }

  if (audio.paused) {
    audio.play().catch(err => console.warn(err));
  } else {
    audio.pause();
  }
}

function nextSong() {
  if (!state.songs.length) return;

  let nextIndex;
  if (state.shuffle && state.songs.length > 1) {
    do {
      nextIndex = Math.floor(Math.random() * state.songs.length);
    } while (nextIndex === state.currentIndex);
  } else {
    nextIndex = (state.currentIndex + 1 + state.songs.length) % state.songs.length;
  }

  playSong(nextIndex);
}

function previousSong() {
  if (!state.songs.length) return;
  if (audio.currentTime > 3) {
    audio.currentTime = 0;
    return;
  }
  const prevIndex = (state.currentIndex - 1 + state.songs.length) % state.songs.length;
  playSong(prevIndex);
}

function handleEnded() {
  if (state.repeat === "one") {
    audio.currentTime = 0;
    audio.play().catch(console.warn);
    return;
  }
  nextSong();
}

function restoreLastSong() {
  const lastId = localStorage.getItem("music-last-song");
  if (!lastId) return;
  const index = state.songs.findIndex(song => song.id === lastId);
  if (index < 0) return;
  state.currentIndex = index;
  updatePlayer(state.songs[index]);

  audio.addEventListener("loadedmetadata", () => {
    const t = Number(localStorage.getItem("music-last-time") || 0);
    if (t > 0 && t < audio.duration) audio.currentTime = t;
  }, { once: true });
}

function escapeHtml(value) {
  return String(value).replace(/[&<>"']/g, char => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#039;"
  }[char]));
}

function escapeAttr(value) {
  return escapeHtml(value);
}

function loadTheme() {
  const saved = localStorage.getItem("music-theme");
  const prefersDark = window.matchMedia?.("(prefers-color-scheme: dark)").matches;
  const theme = saved || (prefersDark ? "dark" : "light");
  document.documentElement.dataset.theme = theme;
}

themeToggle.addEventListener("click", () => {
  const next = document.documentElement.dataset.theme === "dark" ? "light" : "dark";
  document.documentElement.dataset.theme = next;
  localStorage.setItem("music-theme", next);
});

searchInput.addEventListener("input", event => {
  state.query = event.target.value;
  applyFilters();
});

document.addEventListener("keydown", event => {
  const tag = document.activeElement?.tagName;
  if (["INPUT", "TEXTAREA", "SELECT"].includes(tag)) {
    if (event.key === "/" && document.activeElement === searchInput) return;
  }

  if (event.key === "/") {
    event.preventDefault();
    searchInput.focus();
    return;
  }

  if (event.code === "Space") {
    event.preventDefault();
    togglePlay();
  }

  if (event.key === "ArrowRight" && audio.duration) {
    audio.currentTime = Math.min(audio.duration, audio.currentTime + 5);
  }

  if (event.key === "ArrowLeft" && audio.duration) {
    audio.currentTime = Math.max(0, audio.currentTime - 5);
  }

  if (event.key.toLowerCase() === "n") nextSong();
  if (event.key.toLowerCase() === "p") previousSong();
});

playBtn.addEventListener("click", togglePlay);
nextBtn.addEventListener("click", nextSong);
prevBtn.addEventListener("click", previousSong);

shuffleBtn.addEventListener("click", () => {
  state.shuffle = !state.shuffle;
  shuffleBtn.classList.toggle("active", state.shuffle);
  savePlayerState();
});

repeatBtn.addEventListener("click", () => {
  state.repeat = state.repeat === "off"
    ? "all"
    : state.repeat === "all"
      ? "one"
      : "off";
  repeatBtn.classList.toggle("active", state.repeat !== "off");
  repeatBtn.textContent = state.repeat === "one" ? "1" : "↻";
  repeatBtn.title = `循环：${state.repeat}`;
  savePlayerState();
});

progress.addEventListener("input", () => {
  if (!audio.duration) return;
  audio.currentTime = (Number(progress.value) / 100) * audio.duration;
});

volume.value = state.volume;
volumeValue.textContent = String(Math.round(state.volume * 100));
setRangeFill(volume, state.volume * 100);
audio.volume = state.volume;

volume.addEventListener("input", () => {
  state.volume = Number(volume.value);
  audio.volume = state.volume;
  volumeValue.textContent = String(Math.round(state.volume * 100));
  setRangeFill(volume, state.volume * 100);
  savePlayerState();
});

audio.addEventListener("timeupdate", () => {
  const pct = audio.duration ? (audio.currentTime / audio.duration) * 100 : 0;
  progress.value = pct;
  setRangeFill(progress, pct);
  currentTime.textContent = fmtTime(audio.currentTime);
  duration.textContent = fmtTime(audio.duration);
  if (Math.floor(audio.currentTime) % 5 === 0) savePlayerState();
});

audio.addEventListener("play", () => {
  playBtn.textContent = "❚❚";
  playBtn.setAttribute("aria-label", "暂停");
  renderSongList();
});

audio.addEventListener("pause", () => {
  playBtn.textContent = "▶";
  playBtn.setAttribute("aria-label", "播放");
  renderSongList();
  savePlayerState();
});

audio.addEventListener("loadedmetadata", () => {
  duration.textContent = fmtTime(audio.duration);
});

audio.addEventListener("ended", handleEnded);

audio.addEventListener("error", () => {
  console.warn("音频加载失败，请检查 songs.json 中的 audio 路径。");
});

shuffleBtn.classList.toggle("active", state.shuffle);
repeatBtn.classList.toggle("active", state.repeat !== "off");
repeatBtn.textContent = state.repeat === "one" ? "1" : "↻";

document.querySelector("#footer-year").textContent = new Date().getFullYear();

loadTheme();
loadSongs();
