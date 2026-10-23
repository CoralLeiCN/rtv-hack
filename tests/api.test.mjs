import test from "node:test";
import assert from "node:assert/strict";

import { ApiError, createApi, segmentTiming } from "../web/api.js";

function jsonResponse(data, status = 200) {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

test("search sends only the query to the adapter without browser credentials", async () => {
  const requests = [];
  const matches = [
    { source: "second-file", reasoning_content: "First ranked result" },
    { source: "first-file", reasoning_content: "Second ranked result" },
  ];
  const api = createApi({
    fetchImpl: async (url, options) => {
      requests.push({ url, ...options });
      return jsonResponse({ results: matches });
    },
  });

  assert.deepEqual(await api.search("  forklift near a person \n"), matches);
  assert.deepEqual(requests.map(({ url }) => url), ["/api/v1/search"]);
  assert.deepEqual(JSON.parse(requests[0].body), { query: "forklift near a person" });
  assert.deepEqual(requests[0].headers, { "Content-Type": "application/json", Accept: "application/json" });
  for (const request of requests) {
    assert.equal(request.method, "POST");
    assert.equal(request.credentials, "omit");
    assert.equal(request.cache, "no-store");
    assert.equal(request.redirect, "error");
    assert.ok(request.signal instanceof AbortSignal);
  }
});

test("blank queries never make a request", async () => {
  let calls = 0;
  const api = createApi({ fetchImpl: async () => { calls += 1; return jsonResponse({ results: [] }); } });
  for (const query of ["", " \n\t "]) {
    await assert.rejects(api.search(query), { name: "ApiError", message: "Enter a search query." });
  }
  assert.equal(calls, 0);
});

test("empty result arrays are valid and unexpected result shapes are rejected", async () => {
  const empty = createApi({ fetchImpl: async () => jsonResponse({ results: [] }) });
  assert.deepEqual(await empty.search("forklift"), []);

  for (const payload of [null, {}, { results: null }, { results: {} }, { results: [null] }, { results: ["text"] }, { results: [[]] }]) {
    const api = createApi({ fetchImpl: async () => jsonResponse(payload) });
    await assert.rejects(api.search("forklift"), {
      name: "ApiError", message: "The service returned unexpected search results. Please try again.",
    });
  }
});

test("invalid JSON produces a safe recoverable error", async () => {
  const api = createApi({ fetchImpl: async () => new Response("private upstream diagnostic", { status: 200 }) });
  await assert.rejects(api.search("forklift"), {
    name: "ApiError", message: "The service returned an unreadable response. Please try again.",
  });
});

test("HTTP failures preserve actionable status without exposing upstream bodies", async () => {
  const cases = [
    [401, "The search service could not access the video archive. Please try again."],
    [403, "The search service does not have access to this archive."],
    [429, "Too many requests. Please wait a moment and try again."],
    [500, "The request failed. Please try again."],
  ];
  for (const [status, message] of cases) {
    let readBody = false;
    const api = createApi({
      fetchImpl: async () => ({
        ok: false, status,
        json: async () => { readBody = true; return { detail: "private upstream diagnostic" }; },
        text: async () => { readBody = true; return "private upstream diagnostic"; },
      }),
    });
    await assert.rejects(api.search("forklift"), (error) => {
      assert.ok(error instanceof ApiError);
      assert.equal(error.status, status);
      assert.equal(error.message, message);
      return true;
    });
    assert.equal(readBody, false);
  }
});

test("network failures and externally aborted requests do not expose transport diagnostics", async () => {
  for (const cause of [new TypeError("private transport diagnostic"), new DOMException("private abort diagnostic", "AbortError")]) {
    const api = createApi({ fetchImpl: async () => { throw cause; } });
    await assert.rejects(api.search("forklift"), {
      name: "ApiError", message: "Could not reach the service. Check your connection and try again.",
    });
  }
});

test("search limit shows a fixed maintenance message without echoing diagnostics", async () => {
  const api = createApi({ fetchImpl: async () => jsonResponse({
    code: "search_limit_reached", detail: "private upstream diagnostic",
  }, 503) });
  await assert.rejects(api.search("deer"), {
    name: "ApiError", status: 503,
    message: "Search could not finish validating matches. Archive maintenance is required before retrying.",
  });
});

test("unrecognized and malformed service-unavailable bodies remain private", async () => {
  for (const body of [null, [], { code: "unknown", detail: "private diagnostic" }, "not-json"]) {
    const api = createApi({ fetchImpl: async () => typeof body === "string"
      ? new Response(body, { status: 503 }) : jsonResponse(body, 503) });
    await assert.rejects(api.search("deer"), {
      name: "ApiError", status: 503, message: "The request failed. Please try again.",
    });
  }
});

test("timeouts abort both pending fetches and pending response reads", async () => {
  for (const stalledStage of ["fetch", "json", "error-json"]) {
    let requestSignal;
    const api = createApi({
      timeoutMs: 5,
      fetchImpl: async (_url, { signal }) => {
        requestSignal = signal;
        const pending = () => new Promise((_resolve, reject) => {
          signal.addEventListener("abort", () => reject(new DOMException("Aborted", "AbortError")), { once: true });
        });
        return stalledStage === "fetch" ? pending() : { ok: stalledStage !== "error-json", status: stalledStage === "error-json" ? 503 : 200, json: pending };
      },
    });
    await assert.rejects(api.search("forklift"), {
      name: "ApiError", message: "The request timed out. Please try again.",
    });
    assert.equal(requestSignal.aborted, true);
  }
});

test("configuration supports an origin or an absolute proxy path prefix", async () => {
  for (const [base, expected] of [
    ["", "/api/v1/search"],
    ["/", "/api/v1/search"],
    [" /workshop/team/ ", "/workshop/team/api/v1/search"],
    ["https://fixture.example/", "https://fixture.example/api/v1/search"],
    ["https://fixture.example/proxy/", "https://fixture.example/proxy/api/v1/search"],
  ]) {
    let requestedUrl;
    const api = createApi({ apiBaseUrl: base, fetchImpl: async (url) => { requestedUrl = url; return jsonResponse({ results: [] }); } });
    await api.search("forklift");
    assert.equal(requestedUrl, expected);
  }
  for (const base of ["//fixture.example", "javascript:alert(1)", "https://user:pass@fixture.example", "/proxy?token=fixture", "https://fixture.example/#fragment"]) {
    assert.throws(() => createApi({ apiBaseUrl: base }));
  }
});

test("playback uses the adapter path and encodes the complete source as one parameter", () => {
  const source = "s3://fixture-segments/aisle 4/clip+one.mp4?x=1&token=source-text#frame";
  for (const [base, expectedOrigin, expectedPath] of [
    ["", "https://frontend.example", "/api/v1/videos/stream"],
    ["/", "https://frontend.example", "/api/v1/videos/stream"],
    [" /workshop/team/ ", "https://frontend.example", "/workshop/team/api/v1/videos/stream"],
    ["https://adapter.example/proxy/", "https://adapter.example", "/proxy/api/v1/videos/stream"],
  ]) {
    const api = createApi({ apiBaseUrl: base });
    const url = new URL(api.playbackUrl(source), "https://frontend.example");
    assert.equal(url.origin, expectedOrigin);
    assert.equal(url.pathname, expectedPath);
    assert.equal(url.searchParams.get("source"), source);
    assert.deepEqual([...url.searchParams.keys()], ["source"]);
    assert.equal(url.username, "");
    assert.equal(url.password, "");
    assert.equal(url.hash, "");
  }
});

test("playback never uses a result source as the destination URL or requests it eagerly", () => {
  let requests = 0;
  const api = createApi({ fetchImpl: async () => { requests += 1; return jsonResponse({ results: [] }); } });
  for (const source of ["https://external.example/video.mp4", "javascript:alert(1)", "//external.example/clip.mp4"]) {
    const url = new URL(api.playbackUrl(source), "https://frontend.example");
    assert.equal(url.origin, "https://frontend.example");
    assert.equal(url.pathname, "/api/v1/videos/stream");
    assert.equal(url.searchParams.get("source"), source);
    assert.deepEqual([...url.searchParams.keys()], ["source"]);
  }
  assert.equal(requests, 0);
  for (const source of [undefined, null, "", " \n ", 7, {}, []]) {
    assert.throws(() => api.playbackUrl(source), { name: "ApiError", message: "This match does not include a video source." });
  }
});

// These field names are arbitrary fixtures, not claims about the VSS contract.
const fixtureMapping = { startField: "fixtureBegin", endField: "fixtureFinish" };

test("timestamp display is opt-in and preserves zero and fractional seconds", () => {
  const result = { fixtureBegin: 0, fixtureFinish: 65.25 };
  assert.equal(segmentTiming(result), "");
  assert.equal(segmentTiming(result, fixtureMapping), "0:00 – 1:05.25");
  assert.equal(segmentTiming({ fixtureBegin: "3601.005" }, fixtureMapping), "From 1:00:01.005");
  assert.equal(segmentTiming({ fixtureFinish: 0 }, fixtureMapping), "Until 0:00");
  assert.equal(segmentTiming({ fixtureBegin: 59.9996 }, fixtureMapping), "From 1:00");
});

test("timestamps support configured millisecond and text values", () => {
  assert.equal(segmentTiming({ fixtureBegin: 0, fixtureFinish: 61250 }, { ...fixtureMapping, unit: "milliseconds" }), "0:00 – 1:01.25");
  assert.equal(segmentTiming({ fixtureBegin: " 2026-10-17T10:00:00Z ", fixtureFinish: "10:01:30" }, { ...fixtureMapping, unit: "text" }), "2026-10-17T10:00:00Z – 10:01:30");
});

test("missing and invalid timestamps are omitted without inventing values", () => {
  assert.equal(segmentTiming({}, fixtureMapping), "");
  for (const value of [undefined, null, "", " \n ", false, -1, Infinity, NaN, {}, [], "not a time"]) {
    assert.equal(segmentTiming({ fixtureBegin: value, fixtureFinish: 2 }, fixtureMapping), "Until 0:02");
  }
  assert.equal(segmentTiming(Object.create({ fixtureBegin: 3 }), fixtureMapping), "");
  assert.equal(segmentTiming({ fixtureBegin: 3 }, { ...fixtureMapping, unit: "unknown" }), "");
  assert.equal(segmentTiming({ fixtureBegin: 3 }, { ...fixtureMapping, unit: "text" }), "");
});
