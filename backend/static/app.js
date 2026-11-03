/**
 * Find-My-Keys Dashboard Client Application
 * Vanilla JS + Chart.js
 * In-place 2-second polling with zero flicker & dark-mode awareness
 */

(() => {
  // ---------------------------------------------------------------------------
  // State
  // ---------------------------------------------------------------------------
  let currentDeviceId = "esp32_keys_01";
  let isRingingState = false;
  let isDeviceOnline = false;
  let showAllEvents = false;
  let lastRefreshTimestamp = Date.now();
  let pollIntervalId = null;
  let timerIntervalId = null;
  let cachedEvents = [];

  // Chart instances
  let wifiChartInstance = null;
  let ringsChartInstance = null;

  // DOM Elements
  const statusDot = document.getElementById("status-dot");
  const statusText = document.getElementById("status-text");
  const statusCard = document.getElementById("device-status-card");
  const lastSeenText = document.getElementById("last-seen-text");
  const wifiRssi = document.getElementById("wifi-rssi");
  const wifiQuality = document.getElementById("wifi-quality");
  const ringsCount = document.getElementById("rings-count");
  const ringBtn = document.getElementById("ring-btn");
  const actionMessage = document.getElementById("action-message");
  const updateTimer = document.getElementById("update-timer");
  const eventsTbody = document.getElementById("events-tbody");
  const eventCounter = document.getElementById("event-counter");
  const tableFooter = document.getElementById("table-footer");
  const showMoreBtn = document.getElementById("show-more-btn");
  const demoDataBtn = document.getElementById("demo-data-btn");
  const clearDemoBtn = document.getElementById("clear-demo-btn");
  const demoDivider = document.getElementById("demo-divider");
  const footerDeviceId = document.getElementById("footer-device-id");
  const voiceBtn = document.getElementById("voice-btn");

  // ---------------------------------------------------------------------------
  // Time Formatting Helpers
  // ---------------------------------------------------------------------------
  function formatRelativeTime(dateString) {
    if (!dateString) return "Never";
    const date = new Date(dateString);
    const now = new Date();
    const diffSec = Math.max(0, Math.floor((now - date) / 1000));

    if (diffSec < 5) return "Just now";
    if (diffSec < 60) return `${diffSec}s ago`;
    const diffMin = Math.floor(diffSec / 60);
    if (diffMin < 60) return `${diffMin}m ago`;
    const diffHour = Math.floor(diffMin / 60);
    if (diffHour < 24) return `${diffHour}h ago`;
    return date.toLocaleDateString(undefined, { month: "short", day: "numeric" });
  }

  function formatEventTimestamp(dateString) {
    if (!dateString) return "--";
    const date = new Date(dateString);
    const now = new Date();
    const isToday = date.toDateString() === now.toDateString();

    const timeStr = date.toLocaleTimeString([], { hour: "numeric", minute: "2-digit", second: "2-digit" });
    if (isToday) {
      return `Today, ${timeStr}`;
    }
    const dateStr = date.toLocaleDateString([], { month: "short", day: "numeric" });
    return `${dateStr}, ${timeStr}`;
  }

  function formatEventType(type) {
    switch (type) {
      case "clap_ring":
        return "Double clap detected";
      case "find_phone":
        return "Find phone triggered";
      case "ring_requested":
        return "Ring command sent";
      case "ring_acknowledged":
        return "Buzzer active (acknowledged)";
      case "ring_stopped":
        return "Buzzer stopped";
      default:
        return type.replace(/_/g, " ");
    }
  }

  function formatSource(source) {
    switch (source?.toLowerCase()) {
      case "clap":
        return "Clap";
      case "telegram":
        return "Telegram Bot";
      case "mobile_shortcut":
      case "shortcut":
        return "Mobile Shortcut";
      case "button":
        return "Device Button";
      case "dashboard":
        return "Dashboard";
      case "device":
        return "Device";
      default:
        return source || "System";
    }
  }

  // ---------------------------------------------------------------------------
  // Chart Colors & Configuration (Theme Responsive)
  // ---------------------------------------------------------------------------
  function getThemeColors() {
    const isDark = window.matchMedia("(prefers-color-scheme: dark)").matches;
    return {
      accent: isDark ? "#818CF8" : "#4F46E5",
      accentBg: isDark ? "rgba(129, 140, 248, 0.12)" : "rgba(79, 70, 229, 0.08)",
      barColor: isDark ? "rgba(129, 140, 248, 0.3)" : "rgba(79, 70, 229, 0.2)",
      barHover: isDark ? "rgba(129, 140, 248, 0.6)" : "rgba(79, 70, 229, 0.45)",
      gridColor: isDark ? "#1F242D" : "#F3F4F6",
      textColor: isDark ? "#6B7280" : "#9CA3AF",
      tooltipBg: isDark ? "#171A21" : "#111827",
      tooltipText: isDark ? "#F3F4F6" : "#FFFFFF"
    };
  }

  function initCharts() {
    const colors = getThemeColors();
    const commonOptions = {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { display: false },
        tooltip: {
          backgroundColor: colors.tooltipBg,
          titleColor: colors.tooltipText,
          bodyColor: colors.tooltipText,
          padding: 8,
          cornerRadius: 6,
          boxPadding: 4,
          displayColors: false
        }
      }
    };

    // 1. Wi-Fi Line Chart
    const wifiCtx = document.getElementById("wifiChart").getContext("2d");
    wifiChartInstance = new Chart(wifiCtx, {
      type: "line",
      data: {
        labels: [],
        datasets: [{
          data: [],
          borderColor: colors.accent,
          backgroundColor: colors.accentBg,
          borderWidth: 2,
          pointRadius: 0,
          pointHoverRadius: 4,
          pointHoverBackgroundColor: colors.accent,
          tension: 0.35,
          fill: true
        }]
      },
      options: {
        ...commonOptions,
        scales: {
          x: {
            display: false,
            grid: { display: false }
          },
          y: {
            grid: { color: colors.gridColor, drawBorder: false },
            ticks: {
              color: colors.textColor,
              font: { family: "Inter, sans-serif", size: 10 },
              maxTicksLimit: 4
            },
            suggestedMin: -90,
            suggestedMax: -45
          }
        }
      }
    });

    // 2. Rings Per Hour Bar Chart
    const ringsCtx = document.getElementById("ringsChart").getContext("2d");
    ringsChartInstance = new Chart(ringsCtx, {
      type: "bar",
      data: {
        labels: [],
        datasets: [{
          data: [],
          backgroundColor: colors.barColor,
          hoverBackgroundColor: colors.barHover,
          borderRadius: 4,
          borderSkipped: false
        }]
      },
      options: {
        ...commonOptions,
        scales: {
          x: {
            grid: { display: false },
            ticks: {
              color: colors.textColor,
              font: { family: "Inter, sans-serif", size: 10 },
              maxTicksLimit: 7
            }
          },
          y: {
            beginAtZero: true,
            grid: { color: colors.gridColor, drawBorder: false },
            ticks: {
              stepSize: 1,
              color: colors.textColor,
              font: { family: "Inter, sans-serif", size: 10 },
              maxTicksLimit: 4
            }
          }
        }
      }
    });

    // Watch for system theme changes and update chart styles dynamically
    window.matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => {
      const updatedColors = getThemeColors();
      if (wifiChartInstance) {
        wifiChartInstance.data.datasets[0].borderColor = updatedColors.accent;
        wifiChartInstance.data.datasets[0].backgroundColor = updatedColors.accentBg;
        wifiChartInstance.options.scales.y.grid.color = updatedColors.gridColor;
        wifiChartInstance.options.scales.y.ticks.color = updatedColors.textColor;
        wifiChartInstance.update("none");
      }
      if (ringsChartInstance) {
        ringsChartInstance.data.datasets[0].backgroundColor = updatedColors.barColor;
        ringsChartInstance.data.datasets[0].hoverBackgroundColor = updatedColors.barHover;
        ringsChartInstance.options.scales.y.grid.color = updatedColors.gridColor;
        ringsChartInstance.options.scales.x.ticks.color = updatedColors.textColor;
        ringsChartInstance.options.scales.y.ticks.color = updatedColors.textColor;
        ringsChartInstance.update("none");
      }
    });
  }

  function updateCharts(chartData) {
    if (!chartData) return;

    // Update Wi-Fi Line Chart
    if (wifiChartInstance && chartData.rssi_history) {
      const history = chartData.rssi_history;
      wifiChartInstance.data.labels = history.timestamps.map(t => formatEventTimestamp(t));
      wifiChartInstance.data.datasets[0].data = history.values;
      wifiChartInstance.update("none"); // No heavy animation for smooth 2s update
    }

    // Update Rings Per Hour Bar Chart
    if (ringsChartInstance && chartData.rings_per_hour) {
      const rings = chartData.rings_per_hour;
      ringsChartInstance.data.labels = rings.labels;
      ringsChartInstance.data.datasets[0].data = rings.values;
      ringsChartInstance.update("none");
    }
  }

  // ---------------------------------------------------------------------------
  // Data Fetching & DOM Updating (Zero-Flicker)
  // ---------------------------------------------------------------------------
  async function fetchDashboardData() {
    try {
      const [statusRes, eventsRes, chartRes] = await Promise.all([
        fetch(`/api/status?device_id=${encodeURIComponent(currentDeviceId)}`),
        fetch(`/api/events?limit=100`),
        fetch(`/api/chart-data?device_id=${encodeURIComponent(currentDeviceId)}`)
      ]);

      if (statusRes.ok) {
        const status = await statusRes.json();
        updateStatusCard(status);
      }

      if (eventsRes.ok) {
        const events = await eventsRes.json();
        cachedEvents = events;
        updateEventsTable(events);
      }

      if (chartRes.ok) {
        const chartData = await chartRes.json();
        updateCharts(chartData);
      }

      lastRefreshTimestamp = Date.now();
      updateTimer.textContent = "Last updated just now";
    } catch (err) {
      console.warn("Auto-refresh fetch error:", err);
      updateTimer.textContent = "Reconnecting to server...";
    }
  }

  function updateStatusCard(status) {
    currentDeviceId = status.device_id || currentDeviceId;
    footerDeviceId.textContent = currentDeviceId;
    isDeviceOnline = Boolean(status.online);
    isRingingState = Boolean(status.is_ringing || status.pending_ring);

    // 1. Online / Offline Status
    if (isDeviceOnline) {
      statusDot.className = "status-dot online";
      statusText.textContent = "Online";
      statusCard.classList.remove("device-offline");
      
      const sec = status.seconds_since_last_seen;
      lastSeenText.textContent = `Last seen ${sec} second${sec !== 1 ? "s" : ""} ago`;
    } else {
      statusDot.className = "status-dot offline";
      statusText.textContent = "Offline";
      statusCard.classList.add("device-offline");

      if (status.last_seen) {
        lastSeenText.textContent = `Last seen ${formatRelativeTime(status.last_seen)}`;
      } else {
        lastSeenText.textContent = "Never connected";
      }
    }

    // 2. Wi-Fi Signal
    if (status.rssi !== null && status.rssi !== undefined) {
      wifiRssi.textContent = status.rssi;
      wifiQuality.textContent = `${status.rssi_quality} connection`;
    } else {
      wifiRssi.textContent = "--";
      wifiQuality.textContent = "No signal reported";
    }

    // 3. Rings Today
    ringsCount.textContent = status.rings_today ?? 0;

    // 4. Update Ring Button State
    updateButtonState();
  }

  // ---------------------------------------------------------------------------
  // Web Audio Synthesizer (Realistic Key Finder Beeper & Voice Feedback)
  // ---------------------------------------------------------------------------
  let audioContext = null;
  let buzzerLoopTimer = null;

  function getAudioContext() {
    if (!audioContext) {
      const AudioCtx = window.AudioContext || window.webkitAudioContext;
      if (AudioCtx) {
        audioContext = new AudioCtx();
      }
    }
    if (audioContext && audioContext.state === "suspended") {
      audioContext.resume();
    }
    return audioContext;
  }

  function playTone(freq, durationMs, type = "square", volume = 0.15) {
    try {
      const ctx = getAudioContext();
      if (!ctx) return;
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();
      osc.type = type;
      osc.frequency.setValueAtTime(freq, ctx.currentTime);

      gain.gain.setValueAtTime(volume, ctx.currentTime);
      gain.gain.exponentialRampToValueAtTime(0.0001, ctx.currentTime + (durationMs / 1000));

      osc.connect(gain);
      gain.connect(ctx.destination);
      osc.start();
      osc.stop(ctx.currentTime + (durationMs / 1000));
    } catch (err) {
      console.warn("Audio error:", err);
    }
  }

  function playConfirmationChime() {
    playTone(1320, 80, "sine", 0.12);
    setTimeout(() => playTone(1760, 100, "sine", 0.15), 90);
  }

  function startBrowserBuzzer() {
    // Sound is generated by the physical ESP32 hardware buzzer, not laptop speakers
    stopBrowserBuzzer();
  }

  function stopBrowserBuzzer() {
    if (buzzerLoopTimer) {
      clearInterval(buzzerLoopTimer);
      buzzerLoopTimer = null;
    }
  }

  function updateButtonState() {
    if (isRingingState) {
      ringBtn.textContent = "Stop ringing";
      ringBtn.classList.add("is-ringing");
      if (!actionMessage.textContent || actionMessage.textContent.includes("scheduled")) {
        actionMessage.textContent = "🔔 Buzzer is currently ringing";
        actionMessage.className = "action-feedback";
      }
      if (!buzzerLoopTimer) {
        startBrowserBuzzer();
      }
    } else {
      ringBtn.textContent = "Ring my keys";
      ringBtn.classList.remove("is-ringing");
      stopBrowserBuzzer();
    }
  }

  function updateEventsTable(events) {
    if (!events || events.length === 0) {
      eventsTbody.innerHTML = '<tr><td colspan="3" class="empty-state">No events recorded yet. Double-clap or click "Ring my keys" to create events.</td></tr>';
      eventCounter.textContent = "0 events";
      tableFooter.style.display = "none";
      demoDataBtn.style.display = "inline-block";
      clearDemoBtn.style.display = "none";
      demoDivider.style.display = "none";
      return;
    }

    eventCounter.textContent = `${events.length} event${events.length !== 1 ? "s" : ""}`;
    
    // Check if any demo data exists
    const hasDemoData = events.some(e => e.is_demo);
    if (hasDemoData) {
      clearDemoBtn.style.display = "inline-block";
      demoDivider.style.display = "inline";
    } else {
      clearDemoBtn.style.display = "none";
      demoDivider.style.display = "none";
    }

    const visibleEvents = showAllEvents ? events : events.slice(0, 20);
    
    // Build HTML rows cleanly
    const rowsHtml = visibleEvents.map(event => {
      const timeStr = formatEventTimestamp(event.timestamp);
      const titleStr = formatEventType(event.type);
      const sourceStr = formatSource(event.source);
      const demoBadge = event.is_demo ? '<span class="pill demo-pill">Demo</span>' : '';

      return `
        <tr>
          <td class="event-time-cell">${timeStr}</td>
          <td class="event-name-cell">${titleStr}</td>
          <td class="source-cell">
            <span class="pill">${sourceStr}</span>${demoBadge}
          </td>
        </tr>
      `;
    }).join("");

    eventsTbody.innerHTML = rowsHtml;

    // Show more toggle
    if (events.length > 20) {
      tableFooter.style.display = "block";
      showMoreBtn.textContent = showAllEvents ? "Show fewer events" : `Show all ${events.length} events`;
    } else {
      tableFooter.style.display = "none";
    }
  }

  // ---------------------------------------------------------------------------
  // Voice Recognition (Web Speech API) & Audio Command Handling
  // ---------------------------------------------------------------------------
  let recognition = null;
  let isListening = false;

  function initVoiceRecognition() {
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SpeechRecognition) {
      if (voiceBtn) {
        voiceBtn.title = "Voice recognition not supported in this browser (Use Chrome or Edge)";
      }
      return false;
    }
    return true;
  }

  async function startVoiceRecognition() {
    getAudioContext();

    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SpeechRecognition) {
      actionMessage.textContent = "Voice recognition is not supported in this browser. Please use Chrome or Edge.";
      actionMessage.className = "action-feedback warning";
      return;
    }

    if (isListening) {
      if (recognition) {
        try { recognition.stop(); } catch (e) {}
      }
      isListening = false;
      voiceBtn.classList.remove("listening");
      actionMessage.textContent = "Microphone stopped.";
      actionMessage.className = "action-feedback";
      return;
    }

    try {
      recognition = new SpeechRecognition();
      recognition.continuous = false;
      recognition.interimResults = false; // Deliver accurate complete phrase
      recognition.maxAlternatives = 5;
      recognition.lang = "en-US";

      recognition.onstart = () => {
        isListening = true;
        voiceBtn.classList.add("listening");
        voiceBtn.setAttribute("title", "Listening... Click to cancel");
        actionMessage.textContent = "🎙️ Listening... Say 'Keys', 'Ring keys', or 'Ring'!";
        actionMessage.className = "action-feedback";
      };

      recognition.onend = () => {
        isListening = false;
        voiceBtn.classList.remove("listening");
        voiceBtn.setAttribute("title", "Voice command (Say 'Keys', 'Ring', etc.)");
      };

      recognition.onresult = (event) => {
        if (!event.results || !event.results[0]) return;

        // Collect all alternative transcripts
        let phrases = [];
        for (let i = 0; i < event.results[0].length; i++) {
          phrases.push(event.results[0][i].transcript.toLowerCase().trim());
        }
        const spoken = phrases[0] || "";
        console.log("Voice recognized alternatives:", phrases);

        // Keywords to trigger ringing
        const ringKeywords = [
          "key", "keys", "ring", "ring keys", "ring the keys", "ring my keys",
          "find", "find keys", "find my keys", "where are my keys",
          "locate", "locate keys", "beep", "beeper", "buzzer"
        ];
        // Keywords to stop
        const stopKeywords = [
          "stop", "stop ringing", "cancel", "quiet", "silence", "shut", "hush", "turn off"
        ];

        const hasStop = phrases.some(p => stopKeywords.some(kw => p.includes(kw)));
        const hasRing = phrases.some(p => ringKeywords.some(kw => p.includes(kw)));

        if (hasStop) {
          playConfirmationChime();
          actionMessage.textContent = `🎙️ Heard: "${spoken}" → Stopping buzzer`;
          actionMessage.className = "action-feedback";
          if (isRingingState) {
            handleRingClick();
          } else {
            actionMessage.textContent = "Buzzer is already stopped.";
          }
        } else if (hasRing) {
          playConfirmationChime();
          actionMessage.textContent = `🎙️ Heard: "${spoken}" → Ringing keys!`;
          actionMessage.className = "action-feedback";
          if (!isRingingState) {
            handleRingClick();
          } else {
            actionMessage.textContent = "Keys are already ringing!";
          }
        } else {
          actionMessage.textContent = `Heard "${spoken}". Try saying "Keys", "Ring keys", or "Ring".`;
          actionMessage.className = "action-feedback";
        }
      };

      recognition.onerror = (event) => {
        isListening = false;
        voiceBtn.classList.remove("listening");
        if (event.error === "no-speech") {
          actionMessage.textContent = "No speech detected. Click the mic and say 'Keys' or 'Ring'.";
          actionMessage.className = "action-feedback";
        } else if (event.error === "not-allowed" || event.error === "service-not-allowed") {
          actionMessage.textContent = "Microphone access blocked. Please allow mic permission in your browser.";
          actionMessage.className = "action-feedback warning";
        } else {
          actionMessage.textContent = `Voice recognition error: ${event.error}`;
          actionMessage.className = "action-feedback warning";
        }
      };

      recognition.start();
    } catch (err) {
      console.warn("Could not start SpeechRecognition directly:", err);
      // Attempt explicit mic prompt
      if (navigator.mediaDevices && navigator.mediaDevices.getUserMedia) {
        navigator.mediaDevices.getUserMedia({ audio: true })
          .then(() => {
            if (recognition) {
              try { recognition.start(); } catch (e) {}
            }
          })
          .catch(() => {
            actionMessage.textContent = "Microphone access blocked. Please allow mic permissions.";
            actionMessage.className = "action-feedback warning";
          });
      }
    }
  }

  // ---------------------------------------------------------------------------
  // User Actions (Buttons)
  // ---------------------------------------------------------------------------
  async function handleRingClick() {
    getAudioContext(); // Unlock audio on user interaction
    if (isRingingState) {
      // User clicked "Stop ringing"
      stopBrowserBuzzer();
      actionMessage.textContent = "Stopping buzzer...";
      actionMessage.className = "action-feedback";
      try {
        const res = await fetch("/api/stop", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ device_id: currentDeviceId, source: "dashboard" })
        });
        if (res.ok) {
          isRingingState = false;
          updateButtonState();
          actionMessage.textContent = "Buzzer stopped";
          fetchDashboardData();
        }
      } catch (err) {
        actionMessage.textContent = "Failed to send stop command";
        actionMessage.className = "action-feedback warning";
      }
    } else {
      // User clicked "Ring my keys"
      actionMessage.textContent = "🔔 Sending ring command...";
      actionMessage.className = "action-feedback";
      startBrowserBuzzer(); // Immediate audible feedback in browser!

      try {
        const res = await fetch("/api/ring", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ device_id: currentDeviceId, source: "dashboard" })
        });
        if (res.ok) {
          const data = await res.json();
          isRingingState = true;
          updateButtonState();
          actionMessage.textContent = data.device_online ? "🔔 Ringing now!" : "🔔 Ringing! (Hardware queued for reconnect)";
          actionMessage.className = "action-feedback";
          fetchDashboardData();
        }
      } catch (err) {
        actionMessage.textContent = "Error sending ring command";
        actionMessage.className = "action-feedback warning";
      }
    }
  }

  async function handleLoadDemoData() {
    demoDataBtn.textContent = "Loading...";
    try {
      const res = await fetch(`/api/demo-data?device_id=${encodeURIComponent(currentDeviceId)}`, {
        method: "POST"
      });
      if (res.ok) {
        demoDataBtn.textContent = "Load demo data";
        actionMessage.textContent = "Sample demo data loaded";
        actionMessage.className = "action-feedback";
        await fetchDashboardData();
      }
    } catch (err) {
      demoDataBtn.textContent = "Load demo data";
    }
  }

  async function handleClearDemoData() {
    clearDemoBtn.textContent = "Clearing...";
    try {
      const res = await fetch(`/api/demo-data?device_id=${encodeURIComponent(currentDeviceId)}`, {
        method: "DELETE"
      });
      if (res.ok) {
        clearDemoBtn.textContent = "Clear demo data";
        actionMessage.textContent = "Demo data cleared";
        actionMessage.className = "action-feedback";
        await fetchDashboardData();
      }
    } catch (err) {
      clearDemoBtn.textContent = "Clear demo data";
    }
  }

  // ---------------------------------------------------------------------------
  // Timers & Initialization
  // ---------------------------------------------------------------------------
  function startTimers() {
    // 2-second auto-refresh
    pollIntervalId = setInterval(fetchDashboardData, 2000);

    // 1-second UI timer for "Last updated N s ago"
    timerIntervalId = setInterval(() => {
      const sec = Math.floor((Date.now() - lastRefreshTimestamp) / 1000);
      if (sec <= 1) {
        updateTimer.textContent = "Last updated just now";
      } else {
        updateTimer.textContent = `Last updated ${sec}s ago`;
      }
    }, 1000);
  }

  function init() {
    initCharts();

    // Initialize voice recognition
    initVoiceRecognition();

    // Event listeners
    ringBtn.addEventListener("click", handleRingClick);
    voiceBtn.addEventListener("click", startVoiceRecognition);

    demoDataBtn.addEventListener("click", handleLoadDemoData);
    clearDemoBtn.addEventListener("click", handleClearDemoData);

    showMoreBtn.addEventListener("click", () => {
      showAllEvents = !showAllEvents;
      updateEventsTable(cachedEvents);
    });

    // Mobile Shortcut setup
    const shortcutInput = document.getElementById("shortcut-url-input");
    const copyShortcutBtn = document.getElementById("copy-shortcut-btn");
    const openShortcutBtn = document.getElementById("open-shortcut-btn");
    const qrImg = document.getElementById("shortcut-qr-img");

    async function setupMobileShortcuts() {
      try {
        const res = await fetch("/api/config-info");
        if (res.ok) {
          const cfg = await res.json();
          const quickUrl = cfg.mobile_quick_url || `${window.location.protocol}//${window.location.host}/quick?token=${cfg.quick_token || ""}`;
          if (shortcutInput) shortcutInput.value = quickUrl;
          if (openShortcutBtn) openShortcutBtn.href = `/quick?token=${cfg.quick_token || ""}`;
          if (qrImg) {
            qrImg.src = `https://api.qrserver.com/v1/create-qr-code/?size=160x160&data=${encodeURIComponent(quickUrl)}`;
          }
        }
      } catch (e) {
        console.error("Failed to load config info:", e);
      }
    }
    setupMobileShortcuts();

    if (copyShortcutBtn && shortcutInput) {
      copyShortcutBtn.addEventListener("click", () => {
        navigator.clipboard.writeText(shortcutInput.value).then(() => {
          const origText = copyShortcutBtn.textContent;
          copyShortcutBtn.textContent = "Copied!";
          setTimeout(() => {
            copyShortcutBtn.textContent = origText;
          }, 2000);
        }).catch(() => {
          shortcutInput.select();
          document.execCommand("copy");
        });
      });
    }

    // Initial data fetch and timer start
    fetchDashboardData();
    startTimers();
  }

  // Run on DOM ready
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
