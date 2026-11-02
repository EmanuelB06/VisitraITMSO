import { getJSON, postJSON } from "./api.js";
import { toast } from "./ui.js";

const COPY = {
  STUDENT: {
    label: "Student ID",
    placeholder: "Type a student ID or name…",
    hint: "Start typing to search registered students.",
  },
  FACULTY: {
    label: "Employee ID",
    placeholder: "Type an employee ID or name…",
    hint: "Start typing to search registered faculty.",
  },
  EXTERNAL: {
    label: "Reference",
    placeholder: "Type a reference or name…",
    hint: "Search for a registered external visitor.",
  },
};

const bootstrapElement = document.getElementById("kiosk-bootstrap");
if (bootstrapElement) {
  const bootstrap = JSON.parse(bootstrapElement.textContent);
  const urls = bootstrap.urls;

  const tabs = Array.from(document.querySelectorAll("#visitor-tabs [data-type]"));
  const search = document.getElementById("visitor-search");
  const clearButton = document.getElementById("clear-visitor");
  const lookupLabel = document.getElementById("lookup-label");
  const lookupHint = document.getElementById("lookup-hint");
  const suggestions = document.getElementById("suggestions");
  const matched = document.getElementById("matched-visitor");
  const matchedInitial = document.getElementById("matched-initial");
  const matchedName = document.getElementById("matched-name");
  const matchedDetail = document.getElementById("matched-detail");
  const matchedIdentifier = document.getElementById("matched-identifier");
  const matchedType = document.getElementById("matched-type");
  const session = document.getElementById("active-session");
  const sessionPurpose = document.getElementById("session-purpose");
  const sessionTime = document.getElementById("session-time");
  const purposeSelect = document.getElementById("purpose-select");
  const customField = document.getElementById("custom-purpose-field");
  const customInput = document.getElementById("custom-purpose");
  const timeInButton = document.getElementById("time-in-btn");
  const timeOutButton = document.getElementById("time-out-btn");
  const kioskHint = document.getElementById("kiosk-hint");
  const overlay = document.getElementById("success-overlay");
  const overlayTitle = document.getElementById("success-title");
  const overlayDetail = document.getElementById("success-detail");
  const activeList = document.getElementById("active-list");
  const refreshButton = document.getElementById("refresh-active");
  const matchedProfile = document.getElementById("matched-profile");
  const scanButton = document.getElementById("scan-qr-btn");
  const scannerOverlay = document.getElementById("scanner-overlay");
  const scannerVideo = document.getElementById("scanner-video");
  const scannerCanvas = document.getElementById("scanner-canvas");
  const scannerStatus = document.getElementById("scanner-status");
  const scannerHint = document.getElementById("scanner-hint");
  const scannerClose = document.getElementById("scanner-close");
  const scannerCancel = document.getElementById("scanner-cancel");
  const scannerRetry = document.getElementById("scanner-retry");

  const state = {
    type: "STUDENT",
    visitor: null,
    activeVisit: null,
    suggestions: [],
    highlighted: -1,
    busy: false,
    requestSeq: 0,
  };

  let lookupTimer = null;
  let overlayTimer = null;

  const scanner = {
    stream: null,
    frame: null,
    active: false,
    busy: false,
    deviceId: null,
    label: "",
  };

  // Desktop Chrome has no "environment" camera, and its default pick is often
  // an IR (Windows Hello) or virtual camera that streams nothing but black.
  const CAMERA_REJECT = /(infrared|\bir\b|windows hello|virtual|obs|snap camera|manycam|droidcam|epoccam|xsplit|ndi)/i;
  const CAMERA_PREFER = /(back|rear|environment|usb|webcam|camera)/i;

  async function cameraCandidates() {
    const fallback = [{ deviceId: null, label: "Default camera" }];
    if (!navigator.mediaDevices?.enumerateDevices) return fallback;

    try {
      const devices = (await navigator.mediaDevices.enumerateDevices()).filter(
        (device) => device.kind === "videoinput" && device.deviceId,
      );
      // Labels stay empty until camera permission has been granted once.
      const labelled = devices.filter((device) => device.label);
      if (!labelled.length) return fallback;

      const usable = labelled.filter((device) => !CAMERA_REJECT.test(device.label));
      const pool = usable.length ? usable : labelled;
      pool.sort(
        (a, b) =>
          Number(CAMERA_PREFER.test(b.label)) - Number(CAMERA_PREFER.test(a.label)),
      );

      const candidates = pool.map((device) => ({
        deviceId: device.deviceId,
        label: device.label,
      }));
      const saved = candidates.find((candidate) => candidate.deviceId === scanner.deviceId);
      if (saved) {
        candidates.splice(candidates.indexOf(saved), 1);
        candidates.unshift(saved);
      }
      return candidates;
    } catch {
      return fallback;
    }
  }

  function waitForFrames(timeout = 2000) {
    return new Promise((resolve) => {
      if (scannerVideo.videoWidth > 0) {
        resolve(true);
        return;
      }

      function finish() {
        scannerVideo.removeEventListener("loadeddata", check);
        scannerVideo.removeEventListener("playing", check);
        clearTimeout(timer);
        resolve(scannerVideo.videoWidth > 0);
      }

      function check() {
        if (scannerVideo.videoWidth > 0) finish();
      }

      const timer = setTimeout(finish, timeout);
      scannerVideo.addEventListener("loadeddata", check);
      scannerVideo.addEventListener("playing", check);
    });
  }

  async function openCamera(deviceId) {
    const stream = await navigator.mediaDevices.getUserMedia({
      video: deviceId
        ? { deviceId: { exact: deviceId } }
        : { facingMode: { ideal: "environment" } },
      audio: false,
    });
    scannerVideo.srcObject = stream;

    try {
      await scannerVideo.play();
    } catch {
      /* A rejected play() still shows up as a missing frame below. */
    }

    if (await waitForFrames()) return stream;

    stream.getTracks().forEach((track) => track.stop());
    scannerVideo.srcObject = null;
    return null;
  }

  async function startScanner() {
    if (!scannerSupported()) {
      toast("Camera scanning is not supported in this browser. Use visitor lookup instead.", "warning");
      return;
    }

    scannerOverlay.hidden = false;
    scannerRetry.hidden = true;
    scannerStatus.textContent = "Starting camera…";
    scannerHint.textContent = "Allow camera access when prompted.";

    try {
      let stream = null;

      for (const candidate of await cameraCandidates()) {
        try {
          stream = await openCamera(candidate.deviceId);
        } catch (error) {
          if (error?.name === "NotAllowedError" || error?.name === "NotFoundError") {
            throw error;
          }
          stream = null; // Unusable device: fall through to the next camera.
        }
        if (stream) {
          scanner.deviceId = candidate.deviceId;
          scanner.label = candidate.label;
          break;
        }
      }

      if (!stream) {
        throw Object.assign(new Error("No camera produced a video signal."), {
          name: "NoVideo",
        });
      }

      scanner.stream = stream;
      scanner.active = true;
      scanner.busy = false;
      scannerStatus.textContent = "Point the camera at the visitor's QR code.";
      scannerHint.textContent = scanner.label
        ? `Using ${scanner.label}. Hold the QR code inside the frame.`
        : "Hold the QR code inside the frame.";
      scanFrame();
    } catch (error) {
      stopScannerStream();
      scannerHint.textContent =
        error?.name === "NotAllowedError"
          ? "Camera permission was denied. Allow access or use visitor lookup instead."
          : error?.name === "NoVideo" ||
              error?.name === "NotReadableError" ||
              error?.name === "OverconstrainedError"
            ? "This camera is not sending a picture. Close other camera apps, then scan again."
            : "No usable camera was found. Use visitor lookup instead.";
      scannerStatus.textContent = "Camera unavailable.";
      scannerRetry.hidden = false;
    }
  }

  function retryScanner() {
    scannerRetry.hidden = true;
    if (scanner.stream) {
      scannerStatus.textContent = "Point the camera at the visitor's QR code.";
      scannerHint.textContent = scanner.label
        ? `Using ${scanner.label}. Hold the QR code inside the frame.`
        : "Hold the QR code inside the frame.";
      scanner.busy = false;
      scanner.active = true;
      scanFrame();
      return;
    }
    startScanner();
  }

  /* ------------------------------------------------------------
     Visitor type tabs
     ------------------------------------------------------------ */
  function setType(type, { focusSearch = false } = {}) {
    state.type = COPY[type] ? type : "STUDENT";
    tabs.forEach((tab) => {
      const active = tab.dataset.type === state.type;
      tab.classList.toggle("is-active", active);
      tab.setAttribute("aria-selected", String(active));
    });

    const copy = COPY[state.type];
    lookupLabel.textContent = copy.label;
    search.placeholder = copy.placeholder;
    lookupHint.textContent = copy.hint;

    resetAll();
    if (focusSearch) search.focus();
  }

  tabs.forEach((tab) => {
    tab.addEventListener("click", () => setType(tab.dataset.type, { focusSearch: true }));
  });

  /* ------------------------------------------------------------
     Lookup
     ------------------------------------------------------------ */
  function clearVisitorState() {
    state.visitor = null;
    state.activeVisit = null;
    matched.hidden = true;
    matchedProfile.hidden = true;
    session.hidden = true;
    purposeSelect.disabled = false;
    updateUi();
  }

  function clearSuggestions() {
    state.suggestions = [];
    state.highlighted = -1;
    suggestions.hidden = true;
    suggestions.replaceChildren();
    search.setAttribute("aria-expanded", "false");
  }

  function resetAll({ focus = false } = {}) {
    state.visitor = null;
    state.activeVisit = null;
    search.value = "";
    clearButton.hidden = true;
    matched.hidden = true;
    matchedProfile.hidden = true;
    session.hidden = true;
    purposeSelect.disabled = false;
    purposeSelect.value = "";
    customInput.value = "";
    customField.hidden = true;
    clearSuggestions();
    if (focus) search.focus();
    updateUi();
  }

  function renderSuggestions() {
    suggestions.replaceChildren();

    if (state.suggestions.length === 0) {
      const empty = document.createElement("p");
      empty.className = "empty-state small";
      empty.textContent = "No matching visitors found.";
      suggestions.appendChild(empty);
      suggestions.hidden = false;
      search.setAttribute("aria-expanded", "true");
      return;
    }

    state.suggestions.forEach((visitor, index) => {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "suggestion";
      button.setAttribute("role", "option");
      button.dataset.index = String(index);

      const avatar = document.createElement("span");
      avatar.className = "suggestion-avatar";
      avatar.textContent = (visitor.name || "?").slice(0, 1).toUpperCase();

      const body = document.createElement("span");
      body.className = "suggestion-body";
      const name = document.createElement("strong");
      name.textContent = visitor.name;
      const detail = document.createElement("small");
      detail.textContent = `${visitor.identifier || "No ID"} · ${visitor.detail}`;
      body.append(name, detail);

      const badge = document.createElement("span");
      badge.className = `badge ${visitor.active_visit ? "badge-green" : "badge-blue"} suggestion-badge`;
      badge.textContent = visitor.active_visit ? "Inside" : visitor.type_label;

      button.append(avatar, body, badge);
      button.addEventListener("click", () => selectSuggestion(index));
      suggestions.appendChild(button);
    });

    state.highlighted = -1;
    suggestions.hidden = false;
    search.setAttribute("aria-expanded", "true");
  }

  function highlight(index) {
    const items = Array.from(suggestions.querySelectorAll(".suggestion"));
    if (items.length === 0) return;
    state.highlighted = (index + items.length) % items.length;
    items.forEach((item, itemIndex) => {
      item.classList.toggle("is-highlighted", itemIndex === state.highlighted);
    });
    items[state.highlighted]?.scrollIntoView({ block: "nearest" });
  }

  async function performLookup(term) {
    const sequence = ++state.requestSeq;
    try {
      const query = new URLSearchParams({ q: term, type: state.type });
      const data = await getJSON(`${urls.lookup}?${query.toString()}`);
      if (sequence !== state.requestSeq) return;
      state.suggestions = data.results || [];
      renderSuggestions();
    } catch (error) {
      if (sequence === state.requestSeq) toast(error.message, "error");
    }
  }

  search.addEventListener("input", () => {
    clearTimeout(lookupTimer);
    clearVisitorState();
    clearButton.hidden = search.value.length === 0;

    const term = search.value.trim();
    if (!term) {
      clearSuggestions();
      return;
    }
    lookupTimer = window.setTimeout(() => performLookup(term), 260);
  });

  search.addEventListener("keydown", (event) => {
    if (suggestions.hidden) return;
    if (event.key === "ArrowDown") {
      event.preventDefault();
      highlight(state.highlighted + 1);
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      highlight(state.highlighted - 1);
    } else if (event.key === "Enter" && state.highlighted >= 0) {
      event.preventDefault();
      selectSuggestion(state.highlighted);
    } else if (event.key === "Escape") {
      clearSuggestions();
    }
  });

  clearButton.addEventListener("click", () => resetAll({ focus: true }));

  document.addEventListener("click", (event) => {
    if (suggestions.hidden) return;
    if (suggestions.contains(event.target) || event.target === search) return;
    clearSuggestions();
  });

  /* ------------------------------------------------------------
     Selected visitor + active session
     ------------------------------------------------------------ */
  function applyVisitor(visitor) {
    state.visitor = visitor;
    search.value = visitor.identifier || visitor.name;
    clearButton.hidden = false;

    matchedInitial.textContent = (visitor.name || "?").slice(0, 1).toUpperCase();
    matchedName.textContent = visitor.name;
    matchedDetail.textContent = visitor.detail;
    matchedIdentifier.textContent = `${visitor.identifier_label}: ${visitor.identifier || "—"}`;
    matchedType.textContent = visitor.type_label;
    matched.hidden = false;

    matchedProfile.href = visitor.profile_url || "#";
    matchedProfile.hidden = !visitor.profile_url;

    setActiveVisit(visitor.active_visit || null);
    updateUi();
  }

  function selectSuggestion(index) {
    const visitor = state.suggestions[index];
    if (!visitor) return;

    clearSuggestions();
    applyVisitor(visitor);
    purposeSelect.focus();
  }

  function setActiveVisit(visit) {
    state.activeVisit = visit || null;
    if (visit) {
      sessionPurpose.textContent = visit.purpose;
      sessionTime.textContent = `Time in: ${visit.time_in}`;
      session.hidden = false;
      purposeSelect.disabled = true;
      customField.hidden = true;
      customInput.value = "";
    } else {
      session.hidden = true;
      purposeSelect.disabled = false;
    }
  }

  /* ------------------------------------------------------------
     Purpose + button state
     ------------------------------------------------------------ */
  function selectedPurposeRequiresText() {
    const option = purposeSelect.selectedOptions[0];
    return option?.dataset.requiresSpecification === "true";
  }

  function syncPurposeField() {
    const requires = selectedPurposeRequiresText();
    customField.hidden = !requires;
    if (!requires) customInput.value = "";
    if (requires && !state.activeVisit) customInput.focus();
    updateUi();
  }

  purposeSelect.addEventListener("change", syncPurposeField);
  customInput.addEventListener("input", updateUi);

  function updateUi() {
    const hasVisitor = Boolean(state.visitor);
    const active = Boolean(state.activeVisit);
    const hasPurpose = Boolean(purposeSelect.value);
    const requiresText = selectedPurposeRequiresText();
    const hasText = customInput.value.trim().length > 0;

    timeInButton.hidden = active;
    timeOutButton.hidden = !active;

    timeInButton.disabled =
      state.busy || !hasVisitor || !hasPurpose || (requiresText && !hasText);
    timeOutButton.disabled = state.busy || !active;

    if (active) {
      kioskHint.textContent = "This visitor is currently inside. Time out to close the session.";
    } else if (!hasVisitor) {
      kioskHint.textContent = COPY[state.type].hint;
    } else if (!hasPurpose) {
      kioskHint.textContent = "Select a visit purpose to enable time in.";
    } else if (requiresText && !hasText) {
      kioskHint.textContent = "Describe the concern to continue.";
    } else {
      kioskHint.textContent = "Ready to record this visit.";
    }
  }

  /* ------------------------------------------------------------
     Camera QR scanner
     ------------------------------------------------------------ */
  function scannerSupported() {
    return Boolean(
      navigator.mediaDevices?.getUserMedia &&
        typeof window.jsQR === "function" &&
        scannerOverlay &&
        scannerVideo &&
        scannerCanvas,
    );
  }

  function stopScannerStream() {
    if (scanner.frame) {
      cancelAnimationFrame(scanner.frame);
      scanner.frame = null;
    }
    scanner.active = false;
    scanner.busy = false;
    if (scanner.stream) {
      scanner.stream.getTracks().forEach((track) => track.stop());
      scanner.stream = null;
    }
    scannerVideo.srcObject = null;
  }

  function closeScanner() {
    stopScannerStream();
    scannerOverlay.hidden = true;
    scannerRetry.hidden = true;
    scannerStatus.textContent = "Point the camera at the visitor's QR code.";
    scannerHint.textContent = "Hold the QR code inside the frame.";
  }

  function scannerFailure(message) {
    scannerStatus.textContent = "QR code not recognized.";
    scannerHint.textContent = message;
    scannerRetry.hidden = false;
    scanner.active = false;
    scanner.busy = false;
  }

  async function handleScannedCode(text) {
    scannerStatus.textContent = "Checking QR code…";
    scannerHint.textContent = "Please wait.";

    try {
      const data = await postJSON(urls.qr_scan, { qr: text });
      const visitor = data.visitor;
      closeScanner();
      setType(visitor.visitor_type, { focusSearch: false });
      applyVisitor(visitor);
      if (!visitor.active_visit) purposeSelect.focus();
      showSuccess(
        "QR code recognized",
        visitor.active_visit
          ? `${visitor.name} · already inside`
          : `${visitor.name} · choose a purpose to check in`,
      );
      refreshActiveList();
    } catch (error) {
      scannerFailure(error.message);
    }
  }

  function scanFrame() {
    if (!scanner.active) return;

    if (scannerVideo.readyState === scannerVideo.HAVE_ENOUGH_DATA) {
      const width = scannerVideo.videoWidth;
      const height = scannerVideo.videoHeight;

      if (width && height) {
        // Decode a capped-size frame: fast enough for live video and still
        // detailed enough to read a printed visitor badge.
        const scale = Math.min(1, 640 / Math.max(width, height));
        const frameWidth = Math.round(width * scale);
        const frameHeight = Math.round(height * scale);
        const context = scannerCanvas.getContext("2d", { willReadFrequently: true });
        scannerCanvas.width = frameWidth;
        scannerCanvas.height = frameHeight;
        context.drawImage(scannerVideo, 0, 0, frameWidth, frameHeight);
        const image = context.getImageData(0, 0, frameWidth, frameHeight);
        const result = window.jsQR(image.data, frameWidth, frameHeight, {
          inversionAttempts: "dontInvert",
        });

        if (result?.data && !scanner.busy) {
          scanner.busy = true;
          handleScannedCode(result.data);
          return;
        }
      }
    }

    scanner.frame = requestAnimationFrame(scanFrame);
  }

  scanButton?.addEventListener("click", startScanner);
  scannerClose?.addEventListener("click", closeScanner);
  scannerCancel?.addEventListener("click", closeScanner);
  scannerRetry?.addEventListener("click", retryScanner);
  scannerOverlay?.addEventListener("click", (event) => {
    if (event.target === scannerOverlay) closeScanner();
  });

  /* ------------------------------------------------------------
     Time in / time out
     ------------------------------------------------------------ */
  async function handleTimeIn() {
    if (state.busy || !state.visitor) return;

    const purposeId = purposeSelect.value;
    const requiresText = selectedPurposeRequiresText();
    const customPurpose = customInput.value.trim();

    if (!purposeId) {
      toast("Select a visit purpose first.", "warning");
      purposeSelect.focus();
      return;
    }
    if (requiresText && !customPurpose) {
      toast("Please specify the concern.", "warning");
      customInput.focus();
      return;
    }

    state.busy = true;
    updateUi();
    try {
      const data = await postJSON(urls.time_in, {
        visitor_id: state.visitor.id,
        purpose_id: purposeId,
        custom_purpose: customPurpose,
      });
      const visit = data.visit;
      state.activeVisit = visit;
      setActiveVisit(visit);
      showSuccess("Time in recorded", `${visit.visitor.name} · ${visit.purpose}`);
      purposeSelect.value = "";
      customInput.value = "";
      customField.hidden = true;
      refreshActiveList();
    } catch (error) {
      toast(error.message, "error");
    } finally {
      state.busy = false;
      updateUi();
    }
  }

  async function handleTimeOut() {
    const visit = state.activeVisit;
    if (state.busy || !visit) return;

    state.busy = true;
    updateUi();
    try {
      const data = await postJSON(visit.time_out_url, {});
      const closed = data.visit;
      showSuccess("Time out recorded", `${closed.visitor.name} · ${closed.time_out}`);
      resetAll({ focus: false });
      refreshActiveList();
    } catch (error) {
      toast(error.message, "error");
    } finally {
      state.busy = false;
      updateUi();
    }
  }

  timeInButton.addEventListener("click", handleTimeIn);
  timeOutButton.addEventListener("click", handleTimeOut);

  /* ------------------------------------------------------------
     Success overlay
     ------------------------------------------------------------ */
  function showSuccess(title, detail) {
    overlayTitle.textContent = title;
    overlayDetail.textContent = detail;
    overlay.hidden = false;
    clearTimeout(overlayTimer);
    overlayTimer = window.setTimeout(() => {
      overlay.hidden = true;
    }, 1900);
  }

  overlay.addEventListener("click", () => {
    clearTimeout(overlayTimer);
    overlay.hidden = true;
  });

  /* ------------------------------------------------------------
     "Inside now" panel
     ------------------------------------------------------------ */
  function renderActiveList(visits) {
    activeList.replaceChildren();

    const activeCount = document.getElementById("active-count");
    if (activeCount) {
      activeCount.textContent = String(visits.length);
      activeCount.hidden = visits.length === 0;
    }

    if (!visits.length) {
      const empty = document.createElement("p");
      empty.className = "empty-state small";
      empty.textContent = "No one is inside right now.";
      activeList.appendChild(empty);
      return;
    }

    visits.forEach((visit) => {
      const item = document.createElement("div");
      item.className = "active-item";

      const avatar = document.createElement("span");
      avatar.className = "avatar";
      avatar.textContent = (visit.visitor.name || "?").slice(0, 1).toUpperCase();

      const body = document.createElement("div");
      body.className = "active-body";
      const name = document.createElement("strong");
      name.textContent = visit.visitor.name;
      const purpose = document.createElement("small");
      purpose.textContent = visit.purpose;
      body.append(name, purpose);

      const time = document.createElement("span");
      time.className = "active-time";
      time.textContent = visit.time_in.split(", ").pop() || visit.time_in;

      item.append(avatar, body, time);
      activeList.appendChild(item);
    });
  }

  async function refreshActiveList() {
    try {
      const data = await getJSON(urls.active);
      renderActiveList(data.visits || []);
    } catch (error) {
      if (!activeList.querySelector(".active-item")) {
        activeList.replaceChildren();
        const message = document.createElement("p");
        message.className = "empty-state small";
        message.textContent = "Unable to load the active list.";
        activeList.appendChild(message);
      }
    }
  }

  refreshButton.addEventListener("click", refreshActiveList);
  window.setInterval(() => {
    if (!document.hidden) refreshActiveList();
  }, 30000);

  /* ------------------------------------------------------------
     Initial state (including prefill after registration)
     ------------------------------------------------------------ */
  setType("STUDENT", { focusSearch: false });

  if (bootstrap.visitor) {
    const visitor = bootstrap.visitor;
    setType(visitor.visitor_type, { focusSearch: false });
    applyVisitor(visitor);
  }

  refreshActiveList();
}
