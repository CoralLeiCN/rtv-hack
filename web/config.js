// Public browser configuration only. Never put credentials or tokens here.
window.VSS_CONFIG = {
  // Empty uses this website's origin. Include any proxy prefix before /api/v1.
  apiBaseUrl: "",

  // Verified against the workshop backend's segment results.
  resultTiming: {
    startField: "segment_start_sec",
    endField: "segment_end_sec",
    unit: "seconds", // "seconds", "milliseconds", or "text"
  },
};
