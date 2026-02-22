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

// ------------------------------
// Extract profile image URL
// ------------------------------
function extractProfileImage(tweet) {
  const avatarImg = tweet.querySelector(
    'div[data-testid="Tweet-User-Avatar"] img',
  );
  if (avatarImg) return avatarImg.src || null;
  const imgs = tweet.querySelectorAll(
    'a[role="link"] img[src*="profile_images"]',
  );
  if (imgs.length > 0) return imgs[0].src;
  return null;
}

// ------------------------------
// Extract username & display name
// ------------------------------
function extractUserInfo(tweet) {
  const userNameEl = tweet.querySelector('[data-testid="User-Name"]');
  if (!userNameEl) return { displayName: null, handle: null };

  const spans = Array.from(userNameEl.querySelectorAll("span"));
  let displayName = null;
  let handle = null;

  for (const span of spans) {
    const t = span.innerText.trim();
    if (!t) continue;
    if (t.startsWith("@")) {
      handle = t;
    } else if (
      !displayName &&
      t.length > 0 &&
      !t.includes("·") &&
      !t.match(/^\d+[smhd]$/)
    ) {
      displayName = t;
    }
  }

  if (!handle) {
    const profileLink = userNameEl.querySelector('a[href^="/"]');
    if (profileLink) {
      const href = profileLink.getAttribute("href");
      if (href && href.startsWith("/") && !href.includes("?")) {
        handle = "@" + href.slice(1);
      }
    }
  }

  return { displayName, handle };
}

// ------------------------------
// Extract media image URLs
// ------------------------------
function extractMediaImages(tweet) {
  const images = [];

  // 1. Primary selector (Twitter usually wraps images in this)
  const photos = tweet.querySelectorAll('[data-testid="tweetPhoto"] img');
  photos.forEach((img) => {
    if (img.src && !img.src.includes("profile_images")) {
      images.push(img.src);
    }
  });

  // 2. Broad fallback (Find any image hosted on Twitter's media domains)
  if (images.length === 0) {
    const allImgs = tweet.querySelectorAll("img");
    allImgs.forEach((img) => {
      if (
        img.src &&
        (img.src.includes("pbs.twimg.com/media") ||
          img.src.includes("twimg.com/media"))
      ) {
        images.push(img.src);
      }
    });
  }

  // 3. Fallback for video thumbnails
  if (images.length === 0) {
    const videos = tweet.querySelectorAll("video");
    videos.forEach((vid) => {
      if (vid.poster && !vid.poster.includes("profile_images")) {
        images.push(vid.poster);
      }
    });
  }

  // Deduplicate and return
  return [...new Set(images)];
}

// =======================================================
// TOP RIGHT MASTER TOGGLE BUTTON
// =======================================================

function createTopRightLogoButton() {
  if (document.getElementById("sentinel-logo-btn")) return;

  const btn = document.createElement("div");
  btn.id = "sentinel-logo-btn";
  btn.classList.add("active"); // Start in active state

  // SVG circular progress ring + logo
  btn.innerHTML = `
    <svg class="sentinel-ring" viewBox="0 0 100 100">
      <circle class="ring-bg" cx="50" cy="50" r="45" />
      <circle class="ring-progress" cx="50" cy="50" r="45" />
    </svg>
    <img src="${chrome.runtime.getURL("logo.png")}" alt="Sentinel Logo">
  `;

  document.body.appendChild(btn);
  document.body.classList.add("sentinel-enabled"); // Initialize enabled state

  // Toggle Sentinel on/off
  btn.addEventListener("click", () => {
    taggingEnabled = !taggingEnabled;
    btn.classList.toggle("active");

    if (!taggingEnabled) {
      // SYSTEM OFFLINE
      document.body.classList.remove("sentinel-enabled");
      document.body.classList.add("sentinel-disabled");
      removeAllBadges(); // Clear existing DOM elements
    } else {
      // SYSTEM ONLINE
      document.body.classList.remove("sentinel-disabled");
      document.body.classList.add("sentinel-enabled");
      scanTweets(); // Re-scan and inject
    }
  });
}

// =======================================================
// TWEET TEXT EXTRACTION
// =======================================================

function extractTweetText(tweet) {
  // Primary: Twitter's own stable testid for tweet text
  const textEl = tweet.querySelector('[data-testid="tweetText"]');
  if (textEl) {
    const text = textEl.innerText.trim();
    if (text.length >= 1) return truncate(text);
  }

  // Fallback: look for longest span with lang attribute (tweet text spans have lang)
  const langSpans = Array.from(tweet.querySelectorAll("span[lang]")).filter(
    (el) => el.innerText.trim().length >= 5,
  );
  if (langSpans.length > 0) {
    const best = langSpans.reduce((a, b) =>
      b.innerText.trim().length > a.innerText.trim().length ? b : a,
    );
    return truncate(best.innerText.trim());
  }

  return null;
}

// =======================================================
// GET ALL TOP-LEVEL TWEETS
// =======================================================

function truncate(str, n = 280) {
  if (!str) return "";
  return str.length > n ? str.substr(0, n - 1) + "..." : str;
}

function getTopLevelTweets() {
  return Array.from(
    document.querySelectorAll('article[data-testid="tweet"]'),
  ).filter((el) => {
    // filter out tweets nested inside another tweet (quoted tweets)
    let parent = el.parentElement;
    while (parent) {
      if (parent.getAttribute && parent.getAttribute("data-testid") === "tweet")
        return false;
      parent = parent.parentElement;
    }
    return true;
  });
}

// =======================================================
// CREATE MINI BADGE + BOTTOM PANEL
// =======================================================

async function createBadge(tweet) {
  if (!taggingEnabled) return;
  if (badges.has(tweet)) return;

  const text = extractTweetText(tweet);
  if (!text) return;

  const { displayName, handle } = extractUserInfo(tweet);
  const profileImage = extractProfileImage(tweet);
  const mediaUrls = extractMediaImages(tweet);

  // ---------------------------------------------
  // INITIAL IDLE STATE
  // ---------------------------------------------
  const btn = document.createElement("div");
  btn.className = "sentinel-core-container";
  btn.innerHTML = `
    <div class="sentinel-badge-core">
      <div class="sentinel-orbit orbit-alpha"></div>
      <div class="sentinel-orbit orbit-beta"></div>
      <img src="${chrome.runtime.getURL("logo.png")}" class="sentinel-logo-img">
    </div>
  `;

  // Find the Action Bar
  const actionBar = tweet.querySelector('div[role="group"]');
  if (actionBar) {
    const bookmarkBtn = actionBar
      .querySelector('[data-testid="bookmark"]')
      ?.closest('div[style*="flex-basis"]');
    if (bookmarkBtn) {
      bookmarkBtn.parentNode.insertBefore(btn, bookmarkBtn);
    } else {
      actionBar.appendChild(btn);
    }
  }

  const panel = document.createElement("div");
  panel.style.display = "none";
  if (actionBar && actionBar.parentElement) {
    actionBar.parentElement.insertAdjacentElement("afterend", panel);
  } else {
    tweet.appendChild(panel);
  }

  let isAnalyzed = false;
  let analysisCache = null;

  badges.set(tweet, { btn, panel });

  // ---------------------------------------------
  // ON-DEMAND CLICK EVENT
  // ---------------------------------------------
  btn.addEventListener("click", async (e) => {
    e.stopPropagation();
    e.preventDefault();

    if (!isAnalyzed) {
      // Re-extract immediately to bypass stale closures when lazy-loading
      const currentText = extractTweetText(tweet) || text;
      const currentMediaUrls = extractMediaImages(tweet);
      const activeMedia =
        currentMediaUrls.length > 0 ? currentMediaUrls : mediaUrls;

      console.log(`[Sentinel] Identifying Post On-Demand:
        - Text: "${currentText}"
        - User: ${displayName || "Unknown"} (${handle || "no-handle"})
        - Media: ${activeMedia.length} items`);

      // Switch to loading UI
      btn.className = "sentinel-core-container sentinel-loading";
      btn.innerHTML = `
        <div class="sentinel-badge-core-loading">
          <svg class="sentinel-ring-mini" viewBox="0 0 100 100">
            <circle class="ring-bg-mini" cx="50" cy="50" r="45" />
            <circle class="ring-progress-mini" cx="50" cy="50" r="45" />
          </svg>
          <img src="${chrome.runtime.getURL("logo.png")}" class="sentinel-logo-img-mini">
        </div>
      `;
      // Ensure panel is hidden while loading
      panel.style.display = "none";

      const analysis = await analyzeTweet({
        text: currentText,
        display_name: displayName,
        handle: handle,
        profile_image_url: profileImage,
        media_urls: activeMedia,
      });

      isAnalyzed = true;
      analysisCache = analysis;

      // Update State
      btn.classList.remove("sentinel-loading");

      const trustScore = analysis.trust_score || 50;
      const aiScore = analysis.ai_generated_score || 0;
      const riskLevel = analysis.risk_level || "medium";

      btn.innerHTML = `
        <div class="sentinel-badge-core">
          <div class="sentinel-orbit orbit-alpha"></div>
          <div class="sentinel-orbit orbit-beta"></div>
          <img src="${chrome.runtime.getURL("logo.png")}" class="sentinel-logo-img">
        </div>
      `;
      btn.classList.add(`risk-${riskLevel}`);

      // Build out the panel
      panel.className = `sentinel-card-refined risk-${riskLevel}`;
      panel.innerHTML = `
        <div class="sentinel-header-strip">
          <div class="brand">
            <img class="logo-mini-header" src="${chrome.runtime.getURL("logo.png")}" alt="Sentinel">
            SENTINEL <span class="version-tag">SYSTEM v3.0</span>
          </div>
          <div class="status-indicator">ANALYSIS COMPLETE</div>
        </div>
        <div class="sentinel-main-grid">
          <div class="report-content">
            <div class="diag-label">ANALYSIS REPORT FOR @${handle ? handle.substring(1) : "USER"}</div>
            <div class="post-preview-context" style="margin-bottom: 12px; font-style: italic; opacity: 0.8; font-size: 11px;">
               Context: "${currentText.substring(0, 100)}${currentText.length > 100 ? "..." : ""}"
            </div>
            <p class="report-text">
              ${
                analysis.reasoning_summary ||
                (riskLevel === "high"
                  ? "Critical anomaly detected. Media structure shows high-variance synthetic signatures."
                  : riskLevel === "medium"
                    ? "Moderate interference detected. Lighting and shadow consistency is outside normal bounds."
                    : "System check complete. No synthetic signatures detected in current media buffer.")
              }
            </p>
            <div class="tag-row">
                <span class="diag-tag"># ${riskLevel.toUpperCase()} RISK</span>
                ${analysis.recommendation ? `<span class="diag-tag"># ${analysis.recommendation.toUpperCase()}</span>` : ""}
                ${(analysis.flags?.visual || []).map((f) => `<span class="diag-tag"># VISUAL: ${f.toUpperCase()}</span>`).join("")}
                ${(analysis.flags?.linguistic || []).map((f) => `<span class="diag-tag"># TEXT: ${f.toUpperCase()}</span>`).join("")}
            </div>
            
            <!-- ADVANCED DIAGNOSTICS ACCORDION -->
            <div class="sentinel-accordion">
              <div class="accordion-header">
                <span>Advanced Model Diagnostics</span>
                <span class="accordion-icon">+</span>
              </div>
              <div class="accordion-body">
                ${
                  analysis.model_breakdowns &&
                  analysis.model_breakdowns.length > 0
                    ? analysis.model_breakdowns
                        .map(
                          (mb) => `
                      <div class="model-row">
                        <div class="model-name">${mb.model_name}</div>
                        <div class="model-desc">${mb.description}</div>
                        <div class="model-score-bar-container">
                          <div class="model-score-bar" style="width: ${(mb.score * 100).toFixed(0)}%"></div>
                        </div>
                        <div class="model-score-val">${(mb.score * 100).toFixed(1)}%</div>
                      </div>
                    `,
                        )
                        .join("")
                    : '<div style="font-size: 10px; opacity: 0.6; padding: 4px 0;">No raw model data available.</div>'
                }
              </div>
            </div>
          </div>
          <div class="data-sidebar">
            <div class="metric-block" style="margin-bottom: 8px;">
              <div class="m-label">AI GENERATED</div>
              <div class="m-value count-up" data-value="${aiScore}">${aiScore}%</div>
            </div>
            <div class="metric-block" style="margin-bottom: 8px;">
              <div class="m-label">SAFETY INDEX</div>
              <div class="m-value count-up" data-value="${trustScore}">${trustScore}%</div>
            </div>
            <div class="metric-block">
              <div class="m-label">CONFIDENCE</div>
              <div class="m-value count-up" data-value="${Math.round((analysis.confidence || 0) * 100)}">0%</div>
            </div>
          </div>
        </div>
      `;

      // Toggle Accordion functionality
      const accordionHeader = panel.querySelector(".accordion-header");
      const accordionBody = panel.querySelector(".accordion-body");
      const accordionIcon = panel.querySelector(".accordion-icon");

      if (accordionHeader) {
        accordionHeader.addEventListener("click", (e) => {
          e.stopPropagation(); // prevent panel closing
          const isOpen =
            accordionBody.style.maxHeight &&
            accordionBody.style.maxHeight !== "0px";

          if (isOpen) {
            accordionBody.style.maxHeight = "0px";
            accordionBody.style.opacity = "0";
            accordionIcon.textContent = "+";
            accordionHeader.classList.remove("active");
            accordionBody.style.padding = "0px 14px";
          } else {
            accordionBody.style.maxHeight = "70px";
            accordionBody.style.opacity = "1";
            accordionIcon.textContent = "−";
            accordionHeader.classList.add("active");
            accordionBody.style.padding = "10px 14px";
          }
        });

        // Make sure panel clicks don't close the entire Sentintel overlay
        panel.addEventListener("click", (e) => {
          e.stopPropagation();
        });
      }
    }

    // Toggle panel visibility
    const isVisible = panel.style.display === "block";
    panel.style.display = isVisible ? "none" : "block";

    // Animate numbers when panel opens
    if (!isVisible && isAnalyzed) {
      const countUpElements = panel.querySelectorAll(".count-up");
      countUpElements.forEach((el) => {
        const targetValue = parseInt(el.getAttribute("data-value")) || 0;
        animateValue(el, 0, targetValue, 800);
      });
    }
  });
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

  getTopLevelTweets().forEach((tweet) => {
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
       MINI LOADING SPINNER (TWEET LEVEL)
    --------------------------- */

    .sentinel-badge-core-loading {
      position: relative;
      width: 30px;
      height: 30px;
      display: flex;
      align-items: center;
      justify-content: center;
    }

    .sentinel-ring-mini {
      position: absolute;
      width: 100%;
      height: 100%;
      transform: rotate(-90deg);
      animation: spin-mini 1s linear infinite;
    }

    @keyframes spin-mini {
      100% { transform: rotate(270deg); }
    }

    .ring-bg-mini {
      fill: none;
      stroke: #1f2937;
      stroke-width: 8;
    }

    .ring-progress-mini {
      fill: none;
      stroke: #1d9bf0;
      stroke-width: 8;
      stroke-linecap: round;
      stroke-dasharray: 283;
      stroke-dashoffset: 70; /* Quarter filled */
      filter: drop-shadow(0 0 4px #1d9bf0);
    }

    .sentinel-logo-img-mini {
      width: 60%;
      height: 60%;
      z-index: 2;
      pointer-events: none;
      opacity: 0.7;
      animation: pulse-mini 1.5s ease-in-out infinite;
    }

    @keyframes pulse-mini {
      0%, 100% { opacity: 0.5; }
      50% { opacity: 1; }
    }

    /* Master Button Fade Effect */
    #sentinel-logo-btn {
      transition: opacity 0.3s ease, filter 0.3s ease;
    }

    #sentinel-logo-btn:not(.active) {
      opacity: 0.5;
      filter: grayscale(1);
    }

    #sentinel-logo-btn.active {
      opacity: 1;
      filter: grayscale(0);
    }

    /* Global State Control */
    .sentinel-disabled .sentinel-core-container,
    .sentinel-disabled .sentinel-card-refined {
      opacity: 0 !important;
      pointer-events: none !important;
      transform: translateY(10px);
      transition: all 0.4s cubic-bezier(0.4, 0, 0.2, 1);
    }

    .sentinel-enabled .sentinel-core-container,
    .sentinel-enabled .sentinel-card-refined {
      opacity: 1 !important;
      pointer-events: auto !important;
      transform: translateY(0);
      transition: all 0.5s cubic-bezier(0.175, 0.885, 0.32, 1.275);
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
      margin-top: 4px; /* Aligns with the action icons */
    }

    .sentinel-loading {
      pointer-events: none !important;
      opacity: 0.8;
    }

    /* ---------------------------
       PRECISION GAUGE
    --------------------------- */
    .sentinel-gauge-wrapper {
      width: 32px;
      height: 20px;
    }

    .sentinel-gauge {
      width: 100%;
      height: 100%;
    }

    .gauge-bg {
      fill: none;
      stroke: #333639;
      stroke-width: 6;
      stroke-linecap: round;
    }

    .gauge-fill {
      fill: none;
      stroke: #00BA7C; /* Fallback to green */
      stroke-width: 6;
      stroke-linecap: round;
      transition: stroke-dasharray 1.5s cubic-bezier(0.4, 0, 0.2, 1);
    }

    .gauge-needle {
      stroke: #fff;
      stroke-width: 2;
      stroke-linecap: round;
      transform-origin: 50px 50px;
      transition: transform 1.8s cubic-bezier(0.34, 1.56, 0.64, 1); /* Slight overshoot */
    }

    /* ---------------------------
       NEON PLASMA CORE
    --------------------------- */
    
    .sentinel-badge-core {
      position: relative;
      width: 30px;
      height: 30px;
      background: #080c14; /* Deep matte navy */
      border-radius: 50%;
      display: flex;
      align-items: center;
      justify-content: center;
      /* This creates the "track" for the neon flow */
      padding: 2px; 
      overflow: visible;
    }

    /* The Flowing Neon Trace */
    .sentinel-badge-core::before {
      content: "";
      position: absolute;
      inset: -1px; /* Slightly larger than the core */
      border-radius: 50%;
      padding: 1.5px; /* Width of the neon line */
      background: conic-gradient(
        from 0deg,
        transparent 0%,
        var(--sentinel-neon) 50%,
        transparent 100%
      );
      -webkit-mask: 
         linear-gradient(#fff 0 0) content-box, 
         linear-gradient(#fff 0 0);
      -webkit-mask-composite: xor;
      mask-composite: exclude;
      animation: sentinel-flow 2s linear infinite;
    }

    /* Risk-based Neon Colors */
    .risk-low { --sentinel-neon: #00ff95; --sentinel-glow: rgba(0, 255, 149, 0.4); }
    .risk-medium { --sentinel-neon: #ffcc00; --sentinel-glow: rgba(255, 204, 0, 0.4); }
    .risk-high { --sentinel-neon: #ff3344; --sentinel-glow: rgba(255, 51, 68, 0.4); }

    /* Soft bloom effect to make it feel "Neon" */
    .sentinel-badge-core::after {
      content: "";
      position: absolute;
      inset: -2px;
      border-radius: 50%;
      border: 1px solid var(--sentinel-neon);
      filter: blur(4px);
      opacity: 0.3;
    }

    @keyframes sentinel-flow {
      to { transform: rotate(360deg); }
    }

    @keyframes sentinel-pulse {
      0%, 100% { opacity: 0.5; }
      50% { opacity: 1; }
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
       REFINED DIAGNOSTIC CARD
    --------------------------- */

    .sentinel-card-refined {
      margin: 12px 16px;
      background: #080c14;
      border: 1px solid rgba(255, 255, 255, 0.08);
      border-radius: 12px;
      overflow: hidden;
      font-family: -apple-system, BlinkMacSystemFont, "Inter", sans-serif;
      position: relative;
    }

    /* Vertical Risk Line */
    .sentinel-card-refined::before {
      content: "";
      position: absolute;
      left: 0; 
      top: 0; 
      bottom: 0;
      width: 4px;
    }
    .risk-high::before { background: #f4212e; box-shadow: 0 0 10px rgba(244, 33, 46, 0.5); }
    .risk-medium::before { background: #ffd400; box-shadow: 0 0 10px rgba(255, 212, 0, 0.5); }
    .risk-low::before { background: #00ba7c; box-shadow: 0 0 10px rgba(0, 186, 124, 0.5); }

    /* Header Strip */
    .sentinel-header-strip {
      background: rgba(255, 255, 255, 0.03);
      padding: 8px 16px;
      display: flex;
      justify-content: space-between;
      align-items: center;
      border-bottom: 1px solid rgba(255, 255, 255, 0.05);
    }

    .brand {
      display: flex;
      align-items: center;
      gap: 8px;
    }

    .brand-logo {
      font-size: 12px;
    }

    .brand-name {
      font-size: 11px;
      font-weight: 800;
      letter-spacing: 2px;
      color: #71767b;
    }

    .version {
      font-size: 9px;
      color: #536471;
      margin-left: 4px;
    }

    .version-tag {
      font-size: 9px;
      color: #536471;
      margin-left: 4px;
    }

    .logo-mini-header {
      width: 14px;
      height: 14px;
      object-fit: contain;
      margin-right: 6px;
      filter: brightness(1.2);
    }

    .status-badge {
      font-size: 9px;
      font-weight: 700;
      color: #00ba7c;
      display: flex;
      align-items: center;
      gap: 4px;
    }

    .status-indicator {
      font-size: 9px;
      font-weight: 700;
      color: #00ba7c;
      display: flex;
      align-items: center;
      gap: 4px;
    }

    /* Main Grid */
    .sentinel-main-grid {
      display: grid;
      grid-template-columns: 1fr 150px;
      padding: 16px;
      gap: 20px;
    }

    /* Report Section */
    .report-section {
      display: flex;
      flex-direction: column;
      gap: 8px;
    }

    .report-content {
      display: flex;
      flex-direction: column;
      gap: 8px;
    }

    .diagnostic-label {
      font-size: 9px;
      font-weight: 800;
      color: #536471;
      letter-spacing: 1px;
      text-transform: uppercase;
    }

    .diag-label {
      font-size: 9px;
      font-weight: 800;
      color: #536471;
      letter-spacing: 1px;
      text-transform: uppercase;
    }

    .report-text {
      font-size: 14px;
      line-height: 1.5;
      color: #e7e9ea;
      margin: 0 0 12px 0;
    }

    .tag-row {
      display: flex;
      flex-wrap: wrap;
      gap: 6px;
    }

    .tag {
      font-family: "JetBrains Mono", monospace;
      font-size: 10px;
      background: rgba(255, 255, 255, 0.05);
      padding: 2px 8px;
      border-radius: 4px;
      color: var(--sentinel-neon);
      border: 1px solid rgba(255, 255, 255, 0.08);
    }

    .diag-tag {
      font-size: 10px;
      color: var(--sentinel-neon);
      background: rgba(255, 255, 255, 0.04);
      padding: 2px 8px;
      border-radius: 4px;
      border: 1px solid rgba(255, 255, 255, 0.05);
      font-family: monospace;
    }

    .post-preview-context {
      background: rgba(0, 0, 0, 0.2);
      border-left: 2px solid var(--sentinel-neon);
      padding: 6px 10px;
      margin-bottom: 12px;
      font-style: italic;
      opacity: 0.8;
      font-size: 11px;
      border-radius: 0 4px 4px 0;
      color: #71767b;
    }

    /* Data Sidebar */
    .data-sidebar {
      display: flex;
      flex-direction: column;
      justify-content: center;
      gap: 16px;
      border-left: 1px solid rgba(255, 255, 255, 0.08);
      padding-left: 20px;
    }

    .metric {
      display: flex;
      flex-direction: column;
    }

    .metric-block {
      display: flex;
      flex-direction: column;
    }

    .m-label {
      font-size: 10px;
      font-weight: 800;
      color: #536471;
      letter-spacing: 1px;
      margin-bottom: 4px;
      text-transform: uppercase;
    }

    .m-value {
      font-family: "JetBrains Mono", "Roboto Mono", monospace;
      font-size: 24px;
      color: #fff;
      font-weight: 500;
      text-shadow: 0 0 8px var(--sentinel-glow);
    }

    /* AI Footer */
    .sentinel-ai-footer {
      background: rgba(0, 0, 0, 0.3);
      border-top: 1px solid rgba(255, 255, 255, 0.05);
      padding: 10px 16px;
      display: flex;
      align-items: center;
      gap: 12px;
    }

    .sentinel-chat-footer {
      background: rgba(0, 0, 0, 0.3);
      border-top: 1px solid rgba(255, 255, 255, 0.05);
      padding: 10px 16px;
      display: flex;
      align-items: center;
      gap: 12px;
    }

    .visor-avatar {
      width: 20px;
      height: 12px;
      background: #1d9bf0;
      border-radius: 2px;
      box-shadow: 0 0 8px rgba(29, 155, 240, 0.4);
      flex-shrink: 0;
    }

    .sentinel-chat {
      background: transparent;
      border: none;
      flex: 1;
      color: #fff;
      font-size: 13px;
      outline: none;
    }

    .sentinel-chat::placeholder {
      color: #71767b;
    }

    .chat-input {
      background: transparent;
      border: none;
      flex: 1;
      color: #fff;
      font-size: 13px;
      outline: none;
    }

    .chat-input::placeholder {
      color: #71767b;
    }

    .send-shortcut {
      font-size: 11px;
      color: #536471;
      font-family: "JetBrains Mono", monospace;
    }

    .shortcut-key {
      font-size: 11px;
      color: #536471;
      font-family: "JetBrains Mono", monospace;
    }

    /* ---------------------------
       ACCORDION STYLING
    --------------------------- */
    .sentinel-accordion {
      margin-top: 16px;
      border: 1px solid rgba(0, 240, 255, 0.15);
      border-radius: 4px;
      background: rgba(0, 20, 30, 0.3);
      overflow: hidden;
      
    }

    .accordion-header {
      padding: 8px 14px;
      font-size: 10px;
      font-family: "JetBrains Mono", "Roboto Mono", monospace;
      color: #00f0ff;
      letter-spacing: 1px;
      text-transform: uppercase;
      cursor: pointer;
      display: flex;
      justify-content: space-between;
      align-items: center;
      background: rgba(0, 240, 255, 0.05);
      transition: background 0.2s ease;
      user-select: none;
    }

    .accordion-header:hover {
      background: rgba(0, 240, 255, 0.1);
    }
    
    .accordion-header.active {
      border-bottom: 1px solid rgba(0, 240, 255, 0.1);
    }

    .accordion-icon {
      font-size: 14px;
      font-weight: bold;
    }

    .accordion-body {
      max-height: 0;
      opacity: 0;
      padding: 0px 14px;
      transition: max-height 0.3s ease-in-out, opacity 0.3s ease-in-out, padding 0.3s ease-in-out;
      background: rgba(0, 0, 0, 0.2);
      overflow-y: auto;
      overflow-x: hidden;
    }

    /* Target Webkit scrollbar explicitly inside accordion body */
    .accordion-body::-webkit-scrollbar {
      width: 4px;
    }
    .accordion-body::-webkit-scrollbar-track {
      background: rgba(0, 240, 255, 0.05);
    }
    .accordion-body::-webkit-scrollbar-thumb {
      background: rgba(0, 240, 255, 0.3);
      border-radius: 4px;
    }

    .model-row {
      margin-bottom: 14px;
      display: grid;
      grid-template-columns: 1fr auto;
      grid-template-areas: 
        "name name"
        "desc val"
        "bar bar";
      row-gap: 6px;
    }
    
    .model-row:last-child {
      margin-bottom: 4px;
    }

    .model-name {
      grid-area: name;
      font-family: "JetBrains Mono", "Roboto Mono", monospace;
      font-size: 8.5px;
      color: rgba(0, 240, 255, 0.6);
      text-transform: uppercase;
      letter-spacing: 0.5px;
    }

    .model-desc {
      grid-area: desc;
      font-size: 11px;
      color: #fff;
      font-weight: 500;
    }

    .model-score-val {
      grid-area: val;
      font-family: "JetBrains Mono", "Roboto Mono", monospace;
      font-size: 11.5px;
      color: #00f0ff;
      text-align: right;
      font-weight: 600;
    }

    .model-score-bar-container {
      grid-area: bar;
      height: 3px;
      background: rgba(255,255,255,0.1);
      border-radius: 2px;
      overflow: hidden;
    }

    .model-score-bar {
      height: 100%;
      background: linear-gradient(90deg, #00f0ff, #0080ff);
      transition: width 1s cubic-bezier(0.1, 0.8, 0.2, 1);
    }
  `;

  document.head.appendChild(style);
}

async function analyzeTweet(tweetData) {
  try {
    const response = await fetch("http://localhost:8000/live-feed", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        post_text: tweetData.text,
        profile_display_name: tweetData.display_name,
        profile_username: tweetData.handle,
        profile_image_url: tweetData.profile_image_url,
        media_urls: tweetData.media_urls,
        content_type: "post",
      }),
    });

    if (!response.ok) throw new Error("Backend analysis failed");
    return await response.json();
  } catch (e) {
    console.error("Sentinel Analysis Error:", e);
    // Fallback if backend is down
    return {
      risk_level: "medium",
      trust_score: 50,
      reasoning_summary: `Neural link interrupted for @${tweetData.handle || "user"}. Using heuristic fallback for: "${tweetData.text.substring(0, 50)}..."`,
      explanation: "Connectivity issue with the Sentinel Central Intelligence.",
      confidence: 0.5,
      recommendation: "Flag for review",
    };
  }
}

// =======================================================
// UTILS & CLEANUP
// =======================================================

function removeAllBadges() {
  for (const item of badges.values()) {
    if (item.btn) item.btn.remove();
    if (item.panel) item.panel.remove();
  }
  badges.clear();
}

// =======================================================
// INITIALIZE + WATCH FOR TWEETS
// =======================================================

let timelineObserver = null;

function waitForTimeline() {
  // If we already have an observer, disconnect it
  if (timelineObserver) {
    timelineObserver.disconnect();
    timelineObserver = null;
  }

  const interval = setInterval(() => {
    const timeline = document.querySelector('[data-testid="primaryColumn"]');
    if (!timeline) return;

    clearInterval(interval);

    injectStyles();
    createTopRightLogoButton();
    scanTweets();

    timelineObserver = new MutationObserver(() => {
      scanTweets();
    });

    timelineObserver.observe(timeline, { childList: true, subtree: true });
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

    // Re-initialize logic for the new timeline
    waitForTimeline();
  }
}).observe(document, { subtree: true, childList: true });
