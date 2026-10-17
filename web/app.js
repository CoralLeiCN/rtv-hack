import { createApi, segmentTiming } from "./api.js";

const element = (id) => document.getElementById(id);
const ui = Object.fromEntries([
  "search-panel", "search-form", "query", "search-button", "search-status",
  "search-error", "results", "results-heading",
].map((id) => [id, element(id)]));
const config = window.VSS_CONFIG ?? {};
let api;
let searching = false;

function message(id, text = "") {
  ui[id].textContent = text;
  ui[id].hidden = !text;
}

function clearResults() {
  ui.results.querySelectorAll("video").forEach((video) => {
    video.pause();
    video.removeAttribute("src");
    video.load();
  });
  ui.results.replaceChildren();
  ui["results-heading"].hidden = true;
}

function appendVideo(card, source, matchNumber) {
  if (typeof source !== "string" || !source.trim()) {
    const unavailable = document.createElement("p");
    unavailable.className = "video-unavailable";
    unavailable.textContent = "Video unavailable for this match.";
    card.append(unavailable);
    return;
  }

  const video = document.createElement("video");
  video.className = "result-video";
  video.controls = true;
  video.playsInline = true;
  video.preload = "none";
  video.setAttribute("aria-label", `Match ${matchNumber} video`);
  video.src = api.playbackUrl(source);

  const error = document.createElement("div");
  error.className = "video-error";
  error.hidden = true;
  const errorText = document.createElement("p");
  errorText.setAttribute("role", "alert");
  const retry = document.createElement("button");
  retry.type = "button";
  retry.className = "video-retry";
  retry.textContent = "Retry video";
  retry.setAttribute("aria-label", `Retry video for Match ${matchNumber}`);
  error.append(errorText, retry);

  function showPlaybackError() {
    if (!video.isConnected || !video.hasAttribute("src")) return;
    error.hidden = false;
    errorText.textContent = "Video could not be loaded. Please try again.";
  }

  video.addEventListener("error", showPlaybackError);
  video.addEventListener("play", () => {
    ui.results.querySelectorAll("video").forEach((other) => {
      if (other !== video) other.pause();
    });
  });
  retry.addEventListener("click", () => {
    error.hidden = true;
    errorText.textContent = "";
    video.load();
    video.focus();
    video.play().catch((failure) => {
      if (failure.name !== "AbortError") showPlaybackError();
    });
  });
  card.append(video, error);
}

function renderResults(results) {
  const fragment = document.createDocumentFragment();
  results.forEach((result, index) => {
    const card = document.createElement("li");
    card.className = "result-card";
    const heading = document.createElement("h3");
    heading.className = "result-title";
    heading.textContent = `Match ${index + 1}`;
    card.append(heading);
    appendVideo(card, result.source, index + 1);
    if (typeof result.reasoning_content === "string" && result.reasoning_content.trim()) {
      const description = document.createElement("p");
      description.className = "result-description";
      description.textContent = result.reasoning_content;
      card.append(description);
    }
    const timing = segmentTiming(result, config.resultTiming);
    if (timing) {
      const time = document.createElement("p");
      time.className = "result-time";
      time.textContent = timing;
      card.append(time);
    }
    fragment.append(card);
  });
  ui.results.replaceChildren(fragment);
  ui["results-heading"].hidden = results.length === 0;
}

ui["search-form"].addEventListener("submit", async (event) => {
  event.preventDefault();
  if (searching || !api) return;
  const query = ui.query.value.trim();
  clearResults();
  message("search-error");
  message("search-status");
  if (!query) {
    message("search-error", "Enter a description to search for.");
    ui.query.focus();
    return;
  }
  searching = true;
  ui.query.disabled = true;
  ui["search-button"].disabled = true;
  ui["search-button"].textContent = "Searching…";
  ui.results.setAttribute("aria-busy", "true");
  ui["search-panel"].dataset.loading = "true";
  message("search-status", "Searching the video archive…");
  try {
    const results = await api.search(query);
    renderResults(results);
    message("search-status", results.length
      ? `${results.length} ${results.length === 1 ? "match" : "matches"} for “${query}”.`
      : `No matches for “${query}”. Try another description.`);
  } catch (error) {
    message("search-status");
    message("search-error", error.message);
  } finally {
    searching = false;
    ui.query.disabled = false;
    ui["search-button"].disabled = false;
    ui["search-button"].textContent = "Search";
    ui.results.setAttribute("aria-busy", "false");
    ui["search-panel"].dataset.loading = "false";
    ui.query.focus();
  }
});

try {
  api = createApi(config);
  ui.query.focus();
} catch {
  message("search-status");
  message("search-error", "Search is not configured correctly. Please contact the person running this site.");
  ui["search-button"].disabled = true;
}
