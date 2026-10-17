export class ApiError extends Error {
  constructor(message, status = 0) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

export function createApi({ apiBaseUrl = "", fetchImpl = globalThis.fetch, timeoutMs = 60000 } = {}) {
  const base = String(apiBaseUrl).trim().replace(/\/+$/, "");
  if (base && !base.startsWith("/")) {
    const url = new URL(base);
    if (!["http:", "https:"].includes(url.protocol) || url.username || url.password || url.search || url.hash) {
      throw new Error("The API address must be an HTTP(S) URL without credentials, query, or fragment.");
    }
  }
  if (base.startsWith("//") || /[?#]/.test(base)) {
    throw new Error("The API address must be an origin or an absolute path prefix.");
  }

  async function post(path, body) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeoutMs);
    try {
      const headers = { "Content-Type": "application/json", Accept: "application/json" };
      const response = await fetchImpl(`${base}/api/v1/${path}`, {
        method: "POST",
        headers,
        body: JSON.stringify(body),
        signal: controller.signal,
        cache: "no-store",
        credentials: "omit",
        redirect: "error",
      });
      if (!response.ok) {
        // Upstream bodies can contain sensitive diagnostics. Show bounded messages.
        if (response.status === 401) throw new ApiError("The search service could not access the video archive. Please try again.", 401);
        if (response.status === 403) throw new ApiError("The search service does not have access to this archive.", 403);
        if (response.status === 429) throw new ApiError("Too many requests. Please wait a moment and try again.", 429);
        throw new ApiError("The request failed. Please try again.", response.status);
      }
      try {
        return await response.json();
      } catch (error) {
        if (controller.signal.aborted) throw error;
        throw new ApiError("The service returned an unreadable response. Please try again.");
      }
    } catch (error) {
      if (error instanceof ApiError) throw error;
      if (controller.signal.aborted) throw new ApiError("The request timed out. Please try again.");
      throw new ApiError("Could not reach the service. Check your connection and try again.");
    } finally {
      clearTimeout(timer);
    }
  }

  return {
    playbackUrl(source) {
      if (typeof source !== "string" || !source.trim()) {
        throw new ApiError("This match does not include a video source.");
      }
      return `${base}/api/v1/videos/stream?${new URLSearchParams({ source })}`;
    },
    async search(query) {
      const cleaned = query.trim();
      if (!cleaned) throw new ApiError("Enter a search query.");
      const data = await post("search", { query: cleaned });
      if (!Array.isArray(data?.results) || data.results.some((row) => !row || typeof row !== "object" || Array.isArray(row))) {
        throw new ApiError("The service returned unexpected search results. Please try again.");
      }
      return data.results;
    },
  };
}

function formatTime(value, unit) {
  if (unit === "text") return typeof value === "string" && value.trim() ? value.trim() : null;
  if (value === null || value === undefined || value === "" || typeof value === "boolean") return null;
  if (typeof value !== "number" && typeof value !== "string") return null;
  if (typeof value === "string" && !value.trim()) return null;
  const seconds = Number(value) / (unit === "milliseconds" ? 1000 : 1);
  if (!Number.isFinite(seconds) || seconds < 0) return null;
  const milliseconds = Math.round(seconds * 1000);
  const whole = Math.floor(milliseconds / 1000);
  const hours = Math.floor(whole / 3600);
  const minutes = Math.floor((whole % 3600) / 60);
  const secs = String(whole % 60).padStart(2, "0");
  const fraction = milliseconds % 1000;
  const suffix = fraction ? `.${String(fraction).padStart(3, "0").replace(/0+$/, "")}` : "";
  return `${hours ? `${hours}:${String(minutes).padStart(2, "0")}` : minutes}:${secs}${suffix}`;
}

export function segmentTiming(result, mapping = {}) {
  const { startField, endField, unit = "seconds" } = mapping;
  if (!["seconds", "milliseconds", "text"].includes(unit)) return "";
  const start = startField && Object.hasOwn(result, startField) ? formatTime(result[startField], unit) : null;
  const end = endField && Object.hasOwn(result, endField) ? formatTime(result[endField], unit) : null;
  if (start && end) return `${start} – ${end}`;
  if (start) return `From ${start}`;
  if (end) return `Until ${end}`;
  return "";
}
