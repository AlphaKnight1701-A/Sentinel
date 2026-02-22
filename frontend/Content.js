// =======================================================
// SENTINEL — Twitter/X Deepfake Detection Layer
// Content Script
// =======================================================



// =======================================================
// GLOBAL STATE
// =======================================================

// Map: tweet element → panel element
const badges = new Map();

// Global toggle state
let taggingEnabled = true;



// =======================================================
// TOP RIGHT MASTER TOGGLE BUTTON
// =======================================================

function createTopRightLogoButton() {
  if (document.getElementById("sentinel-logo-btn")) return;

  const btn = document.createElement("div");
  btn.id = "sentinel-logo-btn";

  // SVG circular progress ring + logo
  btn.innerHTML = `
    <svg class="sentinel-ring" viewBox="0 0 100 100">
      <circle class="ring-bg" cx="50" cy="50" r="45" />
      <circle class="ring-progress" cx="50" cy="50" r="45" />
    </svg>
    <img src="${chrome.runtime.getURL("logo.png")}" alt="Sentinel Logo">
  `;

  document.body.appendChild(btn);

  // Toggle Sentinel on/off
  btn.addEventListener("click", () => {
    taggingEnabled = !taggingEnabled;
    btn.classList.toggle("active");

    if (!taggingEnabled) {
      removeAllBadges();
    } else {
      scanTweets();
    }
  });
}



// =======================================================
// PLACEHOLDER ANALYSIS ENGINE
// (Replace with real model later)
// =======================================================

function analyzeTweet(text) {
  const synthetic = Math.floor(Math.random() * 100);
  const authentic = 100 - synthetic;
  const confidence = 80 + Math.floor(Math.random() * 20);

  const reasons =
    synthetic > 60
      ? ["Lip-sync desync", "Lighting inconsistency"]
      : ["Natural blink pattern", "Consistent shadow mapping"];

  return { synthetic, authentic, confidence, reasons };
}



// =======================================================
// TWEET TEXT EXTRACTION
// =======================================================

function extractTweetText(tweet) {
  const textEl = tweet.querySelector('[data-testid="tweetText"]');
  if (!textEl) return null;

  const text = textEl.innerText.trim();
  return text.length ? text : null;
}



// =======================================================
// GET ALL TOP-LEVEL TWEETS
// =======================================================

function getTopLevelTweets() {
  return Array.from(
    document.querySelectorAll('article[data-testid="tweet"]')
  );
}



// =======================================================
// CREATE MINI BADGE + BOTTOM PANEL
// =======================================================

function createBadge(tweet) {
  if (!taggingEnabled) return;
  if (badges.has(tweet)) return;

  const text = extractTweetText(tweet);
  if (!text) return;

  const analysis = analyzeTweet(text);

  // ---------------------------------------------
  // ACTION ROW BUTTON (Next to Bookmark)
  // ---------------------------------------------

  const btn = document.createElement("div");
  btn.className = "sentinel-core-container";

  const trustValue = analysis.authentic;
  const riskColor = trustValue > 70 ? '#00ff95' : trustValue > 30 ? '#ffcc00' : '#ff3344';

  btn.innerHTML = `
    <div class="sentinel-gauge-container">
      <svg viewBox="0 0 100 55" class="sentinel-speedo">
        <defs>
          <linearGradient id="gaugeGradient" x1="0%" y1="0%" x2="100%" y2="0%">
            <stop offset="0%" stop-color="#ff3344" />
            <stop offset="50%" stop-color="#ffcc00" />
            <stop offset="100%" stop-color="#00ff95" />
          </linearGradient>
          
          <filter id="gaugeGlow" x="-20%" y="-20%" width="140%" height="140%">
            <feGaussianBlur stdDeviation="2" result="blur" />
            <feComposite in="SourceGraphic" in2="blur" operator="over" />
          </filter>
        </defs>

        <g class="ticks" stroke="#333639" stroke-width="0.5">
          ${[...Array(11)].map((_, i) => {
            const angle = (i * 18) - 180;
            return `<line x1="50" y1="5" x2="50" y2="8" transform="rotate(${angle} 50 50)" />`;
          }).join('')}
        </g>

        <path class="gauge-track" d="M 10 50 A 40 40 0 0 1 90 50" fill="none" stroke="#1c2732" stroke-width="6" stroke-linecap="round" />

        <path class="gauge-fill-arc" d="M 10 50 A 40 40 0 0 1 90 50" 
              fill="none" stroke="url(#gaugeGradient)" stroke-width="6" stroke-linecap="round"
              stroke-dasharray="126" stroke-dashoffset="126" />

        <g class="needle-group" style="transform: rotate(-90deg); transform-origin: 50px 50px;">
          <line x1="50" y1="50" x2="50" y2="15" stroke="#fff" stroke-width="1.5" stroke-linecap="round" />
          <circle cx="50" cy="50" r="3" fill="#fff" />
        </g>
      </svg>
      
      <div class="gauge-number-wrapper">
         <span class="gauge-value" style="color: ${riskColor}; text-shadow: 0 0 10px ${riskColor}66;">0</span>
         <span class="gauge-unit">%</span>
      </div>
    </div>

    <div class="sentinel-badge-core">
      <div class="sentinel-orbit orbit-alpha"></div>
      <div class="sentinel-orbit orbit-beta"></div>
      <img src="${chrome.runtime.getURL("logo.png")}" class="sentinel-logo-img">
    </div>
  `;

  // Risk coloring (border/glow)
  if (analysis.synthetic > 70) {
    btn.classList.add("risk-high");
  } else if (analysis.synthetic > 30) {
    btn.classList.add("risk-medium");
  } else {
    btn.classList.add("risk-low");
  }

  // Find the Action Bar
  const actionBar = tweet.querySelector('div[role="group"]');
  let bookmarkBtn = null; // Declare outside the if block
  
  if (actionBar) {
    // Find the bookmark button container (usually the last child in the row)
    bookmarkBtn = actionBar.querySelector('[data-testid="bookmark"]')?.closest('div[style*="flex-basis"]');
    
    if (bookmarkBtn) {
      // Insert Sentinel specifically to the left of the Bookmark button
      bookmarkBtn.parentNode.insertBefore(btn, bookmarkBtn);
    } else {
      // Fallback: Append to the end of the action bar if bookmark isn't found
      actionBar.appendChild(btn);
    }
  }

  // Trigger gauge animation on mount
  setTimeout(() => {
    const gaugeContainer = btn.querySelector('.sentinel-gauge-container');
    if (gaugeContainer) {
      startGaugeAnimation(gaugeContainer, analysis.authentic);
    }
  }, 100);


  // ---------------------------------------------
  // BOTTOM CYBER PANEL
  // ---------------------------------------------

  const panel = document.createElement("div");
  panel.className = `sentinel-card-unified ${analysis.synthetic > 70 ? 'risk-high' : analysis.synthetic > 30 ? 'risk-medium' : 'risk-low'}`;
  panel.style.display = "none";

  panel.innerHTML = `
    <div class="sentinel-card-header">
      <div class="header-brand">
        <span class="brand-logo">🛡️</span>
        <span class="brand-name">SENTINEL</span>
      </div>
      <div class="header-status">SYSTEM ACTIVE</div>
    </div>
    
    <div class="sentinel-card-body">
      <div class="diagnostic-grid">
        <div class="main-report">
          <p class="diagnostic-text">
            ${analysis.synthetic > 70 ? "High probability of synthetic manipulation detected in media stream." : 
              analysis.synthetic > 30 ? "Potential AI-generated artifacts identified in lighting/textures." : 
              "Media appears consistent with authentic capture standards."}
          </p>
          <div class="reason-pills">
            ${analysis.reasons.map(r => `<span class="pill">${r}</span>`).join("")}
          </div>
        </div>
        
        <div class="score-sidebar">
          <div class="data-point">
            <span class="label">TRUST</span>
            <span class="value count-up" data-value="${analysis.authentic}">0%</span>
          </div>
          <div class="data-point">
            <span class="label">CONFIDENCE</span>
            <span class="value count-up" data-value="${analysis.confidence}">0%</span>
          </div>
        </div>
      </div>

      <div class="sentinel-ai-input-wrapper">
        <div class="ai-avatar-visor"></div>
        <input type="text" class="sentinel-ai-field" placeholder="Ask Sentinel AI about this content...">
        <button class="ai-send-btn">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M5 12h14M12 5l7 7-7 7"/></svg>
        </button>
      </div>
    </div>
  `;

  // Insert panel BELOW action row (Reply / Repost / Like)
  if (actionBar && actionBar.parentElement) {
    actionBar.parentElement.insertAdjacentElement("afterend", panel);
  } else {
    tweet.appendChild(panel);
  }

  // Toggle panel visibility
  btn.addEventListener("click", () => {
    const isVisible = panel.style.display === "block";
    panel.style.display = isVisible ? "none" : "block";
    
    // Animate numbers when panel opens
    if (!isVisible) {
      const countUpElements = panel.querySelectorAll('.count-up');
      countUpElements.forEach(el => {
        const targetValue = parseInt(el.getAttribute('data-value')) || 0;
        animateValue(el, 0, targetValue, 800);
      });
    }
  });

  badges.set(tweet, { btn, panel });
}



// =======================================================
// GAUGE SPEEDOMETER ANIMATION
// =======================================================

function startGaugeAnimation(container, finalValue) {
  const fillArc = container.querySelector('.gauge-fill-arc');
  const needle = container.querySelector('.needle-group');
  const numberText = container.querySelector('.gauge-value');
  
  if (!fillArc || !needle || !numberText) return;
  
  const duration = 1500; // 1.5 seconds
  const startTime = performance.now();

  function update(now) {
    const elapsed = now - startTime;
    const progress = Math.min(elapsed / duration, 1);
    
    // Ease-out cubic: smooth slowdown at the end
    const easeProgress = 1 - Math.pow(1 - progress, 3);
    
    const currentValue = Math.floor(easeProgress * finalValue);
    
    // 1. Update Number
    numberText.innerText = currentValue;
    
    // 2. Update Arc Fill (126 is the total length of the path)
    const offset = 126 - (easeProgress * (finalValue / 100) * 126);
    fillArc.style.strokeDashoffset = offset;
    
    // 3. Update Needle Rotation (-90deg to +90deg range)
    const rotation = (easeProgress * (finalValue / 100) * 180) - 90;
    needle.style.transform = `rotate(${rotation}deg)`;

    if (progress < 1) requestAnimationFrame(update);
  }
  requestAnimationFrame(update);
}


// =======================================================
// ANIMATED NUMBER COUNTER
// =======================================================

function animateValue(obj, start, end, duration) {
  let startTimestamp = null;
  const step = (timestamp) => {
    if (!startTimestamp) startTimestamp = timestamp;
    const progress = Math.min((timestamp - startTimestamp) / duration, 1);
    obj.innerHTML = Math.floor(progress * (end - start) + start) + "%";
    if (progress < 1) { 
      window.requestAnimationFrame(step);
    }
  };
  window.requestAnimationFrame(step);
}



// =======================================================
// REMOVE ALL PANELS
// =======================================================

function removeAllBadges() {
  badges.forEach(({ btn, panel }) => {
    if (btn && btn.parentNode) btn.remove();
    if (panel && panel.parentNode) panel.remove();
  });
  badges.clear();
}



// =======================================================
// SCAN PAGE FOR NEW TWEETS
// =======================================================

function scanTweets() {
  if (!taggingEnabled) return;

  getTopLevelTweets().forEach(tweet => {
    createBadge(tweet);
  });
}



// =======================================================
// STYLE INJECTION
// =======================================================

function injectStyles() {
  if (document.getElementById("sentinel-styles")) return;

  const style = document.createElement("style");
  style.id = "sentinel-styles";

  style.textContent = `
    /* ---------------------------
       MASTER BUTTON
    --------------------------- */

    #sentinel-logo-btn {
      position: fixed;
      top: 20px;
      right: 20px;
      width: 52px;
      height: 52px;
      border-radius: 50%;
      background: #0b1220;
      display: flex;
      align-items: center;
      justify-content: center;
      cursor: pointer;
      z-index: 999999;
    }

    #sentinel-logo-btn img {
      position: absolute;
      width: 60%;
      height: 60%;
      pointer-events: none;
    }

    .sentinel-ring {
      position: absolute;
      width: 100%;
      height: 100%;
      transform: rotate(-225deg);
    }

    .ring-bg {
      fill: none;
      stroke: #1f2937;
      stroke-width: 6;
    }

    .ring-progress {
      fill: none;
      stroke: #1d9bf0;
      stroke-width: 6;
      stroke-linecap: round;
      stroke-dasharray: 283;
      stroke-dashoffset: 283;
      opacity: 0;
      transition: stroke-dashoffset 0.6s ease, opacity 0.4s ease;
    }

    #sentinel-logo-btn.active .ring-progress {
      stroke-dashoffset: 0;
      opacity: 1;
      filter: drop-shadow(0 0 8px #1d9bf0);
    }

    /* ---------------------------
       SENTINEL CORE CONTAINER
    --------------------------- */

    /* Container for Gauge + Button */
    .sentinel-core-container {
      display: flex;
      align-items: center;
      gap: 8px;
      cursor: pointer;
      padding: 0 8px;
      height: 34px;
    }

    /* ---------------------------
       SPEEDOMETER GAUGE
    --------------------------- */
    .sentinel-gauge-container {
      width: 120px;
      position: relative;
      display: flex;
      flex-direction: column;
      align-items: center;
      background: transparent;
    }

    .sentinel-speedo {
      width: 100%;
      filter: drop-shadow(0 0 5px rgba(0,0,0,0.5));
    }

    .gauge-track {
      fill: none;
      stroke: #1c2732;
      stroke-width: 6;
      stroke-linecap: round;
    }

    .gauge-fill-arc {
      filter: url(#gaugeGlow);
      transition: stroke-width 0.3s ease;
    }

    .needle-group {
      transform-origin: 50px 50px;
    }

    .gauge-number-wrapper {
      margin-top: -15px;
      display: flex;
      align-items: baseline;
    }

    .gauge-value {
      font-family: 'JetBrains Mono', 'Roboto Mono', monospace;
      font-size: 22px;
      font-weight: 700;
    }

    .gauge-unit {
      font-size: 10px;
      color: #536471;
      margin-left: 2px;
      font-weight: 800;
    }

    /* Subtle Hover Effect */
    .sentinel-gauge-container:hover .gauge-fill-arc {
      stroke-width: 8;
      transition: stroke-width 0.3s ease;
    }

    /* ---------------------------
       ORBITAL BADGE
    --------------------------- */
    .sentinel-badge-core {
      position: relative;
      width: 28px;
      height: 28px;
      background: #0a0f1a;
      border-radius: 50%;
      display: flex;
      align-items: center;
      justify-content: center;
      border: 1px solid rgba(255, 255, 255, 0.1);
      perspective: 100px;
      transform-style: preserve-3d;
    }

    /* The Orbits - Thin, subtle, and elegant */
    .sentinel-orbit {
      position: absolute;
      border: 0.5px solid rgba(29, 155, 240, 0.4);
      border-radius: 50%;
      pointer-events: none;
      top: 50%;
      left: 50%;
    }

    .orbit-alpha {
      width: 32px;
      height: 32px;
      margin-left: -16px;
      margin-top: -16px;
      border-color: rgba(29, 155, 240, 0.3);
      animation: sentinel-rotate-alpha 10s linear infinite;
    }

    .orbit-beta {
      width: 36px;
      height: 36px;
      margin-left: -18px;
      margin-top: -18px;
      border-color: rgba(29, 155, 240, 0.15);
      animation: sentinel-rotate-beta 15s linear infinite;
    }

    @keyframes sentinel-rotate-alpha {
      from { transform: rotateX(60deg) rotateY(10deg) rotateZ(0deg); }
      to { transform: rotateX(60deg) rotateY(10deg) rotateZ(360deg); }
    }

    @keyframes sentinel-rotate-beta {
      from { transform: rotateX(-45deg) rotateY(20deg) rotateZ(360deg); }
      to { transform: rotateX(-45deg) rotateY(20deg) rotateZ(0deg); }
    }

    /* Risk-based Ring Glow */
    .risk-high .sentinel-badge-core { 
      border: 1.5px solid #F4212E; 
      box-shadow: 0 0 8px rgba(244, 33, 46, 0.3); 
    }
    
    .risk-medium .sentinel-badge-core { 
      border: 1.5px solid #FFD400; 
      box-shadow: 0 0 8px rgba(255, 212, 0, 0.3); 
    }
    
    .risk-low .sentinel-badge-core { 
      border: 1.5px solid #00BA7C; 
      box-shadow: 0 0 8px rgba(0, 186, 124, 0.3); 
    }

    .sentinel-logo-img {
      width: 65%;
      height: 65%;
      z-index: 2;
      pointer-events: none;
    }

    /* ---------------------------
       CLEAN HOVER STATE
    --------------------------- */

    /* Remove the default grey background/halo */
    .sentinel-action-btn, 
    .sentinel-mini-btn,
    .sentinel-core-container {
      background-color: transparent !important;
      outline: none !important;
      -webkit-tap-highlight-color: transparent !important;
    }

    /* Ensure no grey circle appears on click/active state */
    .sentinel-core-container:active,
    .sentinel-core-container:focus {
      background-color: transparent !important;
      box-shadow: none !important;
    }

    /* ---------------------------
       DIAGNOSTIC CARD PANEL
    --------------------------- */

    .sentinel-panel {
      margin: 12px 16px;
      padding: 0;
      font-family: TwitterChirp, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
      position: relative;
    }

    .sentinel-card {
      background: #0a0f1a;
      border: 1px solid rgba(255, 255, 255, 0.05);
      box-shadow: inset 0 2px 10px rgba(0, 0, 0, 0.5);
      border-radius: 12px;
      display: grid;
      grid-template-columns: 1fr 200px;
      gap: 20px;
      padding: 16px;
    }

    /* Left accent border */
    .sentinel-panel::before {
      content: "";
      position: absolute;
      left: 0;
      top: 0;
      bottom: 0;
      width: 4px;
      border-radius: 12px 0 0 12px;
    }
    .risk-high-panel::before { background-color: #F4212E; }
    .risk-medium-panel::before { background-color: #FFD400; }
    .risk-low-panel::before { background-color: #00BA7C; }

    .sentinel-main-section {
      grid-column: 1;
    }

    /* Header Row */
    .sentinel-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 12px;
    }

    .sentinel-header-left {
      display: flex;
      align-items: center;
      gap: 8px;
    }

    .sentinel-label {
      font-weight: 700;
      font-size: 15px;
      color: #e7e9ea;
    }

    .sentinel-alpha {
      font-size: 10px;
      color: #71767b;
      vertical-align: middle;
      border: 1px solid #71767b;
      padding: 0 4px;
      border-radius: 4px;
      margin-left: 4px;
    }

    .sentinel-header-right {
      font-size: 13px;
      color: #71767b;
    }

    .sentinel-headline {
      font-size: 15px;
      line-height: 20px;
      color: #e7e9ea;
      margin: 0 0 12px 0;
    }

    .sentinel-reasons-list {
      display: flex;
      flex-wrap: wrap;
      gap: 6px;
    }

    .reason-tag {
      background: #16181c;
      border: 1px solid #333639;
      color: #71767b;
      padding: 2px 8px;
      border-radius: 99px;
      font-size: 12px;
    }

    /* Stats Box with Monospace Font */
    .sentinel-stats-box {
      border-left: 1px solid rgba(255, 255, 255, 0.1);
      padding-left: 20px;
      display: flex;
      flex-direction: column;
      justify-content: center;
      gap: 16px;
    }

    .data-box {
      display: flex;
      flex-direction: column;
    }

    .data-label {
      font-size: 11px;
      color: #71767b;
      text-transform: uppercase;
      letter-spacing: 0.5px;
      margin-bottom: 4px;
    }

    .stat-value {
      font-family: 'JetBrains Mono', 'Courier New', monospace;
      font-size: 24px;
      letter-spacing: -1px;
      font-weight: 500;
      color: #fff;
    }

    .stat-value.red { color: #F4212E; }
    .stat-value.green { color: #00BA7C; }

    /* Sentinel AI Chat Section */
    .sentinel-chat-section {
      grid-column: 1 / -1;
      display: flex;
      align-items: center;
      gap: 12px;
      background: rgba(255, 255, 255, 0.03);
      padding: 8px 12px;
      border-radius: 8px;
      margin-top: 8px;
    }

    .sentinel-avatar {
      width: 24px;
      height: 24px;
      background: linear-gradient(135deg, #1d9bf0 0%, #004a7c 100%);
      clip-path: polygon(25% 0%, 75% 0%, 100% 50%, 75% 100%, 25% 100%, 0% 50%);
      position: relative;
      flex-shrink: 0;
    }

    .visor-line {
      position: absolute;
      top: 40%;
      left: 15%;
      right: 15%;
      height: 2px;
      background: #fff;
      box-shadow: 0 0 8px rgba(255, 255, 255, 0.8);
    }

    .sentinel-chat-input {
      flex: 1;
      background: transparent;
      border: none;
      border-bottom: 1px solid rgba(255, 255, 255, 0.1);
      color: #e7e9ea;
      font-size: 13px;
      font-family: TwitterChirp, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      padding: 6px 0;
      outline: none;
      transition: border-color 0.2s;
    }

    .sentinel-chat-input:focus {
      border-bottom-color: #1d9bf0;
    }

    .sentinel-chat-input::placeholder {
      color: #71767b;
    }

    .sentinel-send-btn {
      background: transparent;
      border: none;
      color: #1d9bf0;
      font-size: 18px;
      cursor: pointer;
      padding: 4px 8px;
      opacity: 0.5;
      transition: opacity 0.2s;
    }

    .sentinel-send-btn:hover {
      opacity: 1;
    }
  `;

  document.head.appendChild(style);
}



// =======================================================
// INITIALIZE + WATCH FOR TWEETS
// =======================================================

function waitForTimeline() {
  const interval = setInterval(() => {
    const timeline = document.querySelector('[data-testid="primaryColumn"]');
    if (!timeline) return;

    clearInterval(interval);

    injectStyles();
    createTopRightLogoButton();
    scanTweets();

    const observer = new MutationObserver(() => {
      scanTweets();
    });

    observer.observe(timeline, { childList: true, subtree: true });

  }, 500);
}

waitForTimeline();

// Reinitialize when Twitter URL changes (SPA navigation)
let lastUrl = location.href;

new MutationObserver(() => {
  if (location.href !== lastUrl) {
    lastUrl = location.href;

    // Clean old panels
    removeAllBadges();

    // Re-scan after short delay
    setTimeout(() => {
      scanTweets();
    }, 500);
  }
}).observe(document, { subtree: true, childList: true });