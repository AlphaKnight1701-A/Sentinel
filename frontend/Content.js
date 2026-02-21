// ==============================
// BobRossRocks - Twitter/X Side Notes
// ==============================
// Twitter uses stable data-testid attributes — much more reliable than class names.
// Key selectors:
//   Tweet container : article[data-testid="tweet"]
//   Tweet text      : div[data-testid="tweetText"]
//   Timeline        : div[data-testid="primaryColumn"]

const badges = new Map();   // tweet el → badge el
const pendingRetry = new Set();
let taggingEnabled = true;

// ------------------------------
// Extract tweet text
// ------------------------------
function extractTweetText(tweet) {
  // Primary: Twitter's own stable testid for tweet text
  const textEl = tweet.querySelector('[data-testid="tweetText"]');
  if (textEl) {
    const text = textEl.innerText.trim();
    if (text.length >= 1) return truncate(text);
  }

  // Fallback: look for longest span with lang attribute (tweet text spans have lang)
  const langSpans = Array.from(tweet.querySelectorAll("span[lang]"))
    .filter(el => el.innerText.trim().length >= 5);
  if (langSpans.length > 0) {
    const best = langSpans.reduce((a, b) =>
      b.innerText.trim().length > a.innerText.trim().length ? b : a
    );
    return truncate(best.innerText.trim());
  }

  return null;
}

function truncate(text, max = 220) {
  return text.length > max ? text.substring(0, max) + "…" : text;
}

// ------------------------------
// Get all top-level tweets
// (avoids nested quoted tweets getting their own badge)
// ------------------------------
function getTopLevelTweets() {
  return Array.from(document.querySelectorAll('article[data-testid="tweet"]')).filter(el => {
    // filter out tweets nested inside another tweet (quoted tweets)
    let parent = el.parentElement;
    while (parent) {
      if (parent.getAttribute && parent.getAttribute("data-testid") === "tweet") return false;
      parent = parent.parentElement;
    }
    return true;
  });
}

// ------------------------------
// Create side note badge for a tweet
// ------------------------------
function createBadge(tweet) {
  if (!taggingEnabled) return;

  if (badges.has(tweet)) {
    // Update text if it loaded later
    const text = extractTweetText(tweet);
    if (text) {
      badges.get(tweet).querySelector(".bobross-text").innerText = text;
      pendingRetry.delete(tweet);
    }
    return;
  }

  const text = extractTweetText(tweet);
  if (!text) {
    pendingRetry.add(tweet);
    return;
  }

  const badge = document.createElement("div");
  badge.className = "bobross-side-badge";
  badge.innerHTML = `
    <div class="bobross-badge-header">🐦 Tweet Note</div>
    <div class="bobross-text">${escapeHtml(text)}</div>
  `;

  document.body.appendChild(badge);
  badges.set(tweet, badge);
  positionBadge(tweet, badge);
}

function escapeHtml(str) {
  return str
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');
}

// ------------------------------
// Position badge to the right of tweet
// ------------------------------
function positionBadge(tweet, badge) {
  const rect = tweet.getBoundingClientRect();
  badge.style.top = `${rect.top + window.scrollY}px`;
  badge.style.left = `${rect.right + window.scrollX + 14}px`;
}

// ------------------------------
// Remove all badges
// ------------------------------
function removeAllBadges() {
  badges.forEach(b => b.remove());
  badges.clear();
  pendingRetry.clear();
}

// ------------------------------
// Scan all top-level tweets
// ------------------------------
function scanTweets() {
  if (!taggingEnabled) return;
  getTopLevelTweets().forEach(tweet => createBadge(tweet));

  // Retry pending tweets (text may not be loaded yet)
  if (pendingRetry.size > 0) {
    pendingRetry.forEach(tweet => {
      if (document.body.contains(tweet)) {
        createBadge(tweet);
      } else {
        pendingRetry.delete(tweet);
      }
    });
  }
}

// ------------------------------
// Update positions on scroll/resize
// ------------------------------
function updatePositions() {
  badges.forEach((badge, tweet) => {
    if (!document.body.contains(tweet)) {
      badge.remove();
      badges.delete(tweet);
    } else {
      positionBadge(tweet, badge);
    }
  });
}

// ------------------------------
// Control panel UI
// ------------------------------
function createOverlay() {
  if (document.getElementById("bobross-overlay")) return;

  const overlay = document.createElement("div");
  overlay.id = "bobross-overlay";
  overlay.innerHTML = `
    <div id="bobross-panel">
      <div id="bobross-title">🎨 BobRossRocks</div>
      <div id="bobross-sub">Tweet notes on the side</div>
      <button id="toggle-btn">Disable</button>
    </div>
  `;
  document.body.appendChild(overlay);

  document.getElementById("toggle-btn").addEventListener("click", () => {
    taggingEnabled = !taggingEnabled;
    document.getElementById("toggle-btn").innerText = taggingEnabled ? "Disable" : "Enable";
    if (!taggingEnabled) removeAllBadges();
    else scanTweets();
  });
}

// ------------------------------
// Inject CSS
// ------------------------------
function injectStyles() {
  if (document.getElementById("bobross-styles")) return;

  const style = document.createElement("style");
  style.id = "bobross-styles";
  style.textContent = `
    /* ===== Control Panel ===== */
    #bobross-overlay {
      position: fixed;
      top: 20px;
      right: 20px;
      z-index: 2147483647;
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
    }
    #bobross-panel {
      background: linear-gradient(135deg, #0f1923, #1a2744);
      color: white;
      padding: 14px 18px;
      border-radius: 14px;
      width: 190px;
      text-align: center;
      box-shadow: 0 8px 32px rgba(0,0,0,0.5);
      border: 1px solid rgba(29,161,242,0.3);
    }
    #bobross-title {
      font-size: 15px;
      font-weight: 700;
    }
    #bobross-sub {
      font-size: 11px;
      opacity: 0.55;
      margin: 4px 0 10px;
    }
    #bobross-panel button {
      padding: 6px 16px;
      border-radius: 20px;
      cursor: pointer;
      font-weight: 600;
      font-size: 12px;
      background: #1d9bf0;
      color: white;
      border: none;
      transition: opacity 0.2s;
    }
    #bobross-panel button:hover { opacity: 0.8; }

    /* ===== Tweet Side Note Badges ===== */
    .bobross-side-badge {
      position: absolute;
      background: #ffffff;
      color: #0f1923;
      padding: 10px 13px;
      border-radius: 14px;
      width: 230px;
      font-size: 12px;
      line-height: 1.5;
      box-shadow: 0 4px 20px rgba(0,0,0,0.15);
      z-index: 999999;
      pointer-events: none;
      border-left: 4px solid #1d9bf0;
      word-break: break-word;
      white-space: pre-wrap;
    }
    .bobross-badge-header {
      font-size: 10px;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.8px;
      color: #1d9bf0;
      margin-bottom: 5px;
    }
    .bobross-text {
      color: #1a1a2e;
      font-size: 12px;
    }
  `;
  document.head.appendChild(style);
}

// ------------------------------
// Wait for Twitter's timeline to load
// Twitter is a SPA — the timeline may not exist on initial page load
// ------------------------------
function waitForTimeline() {
  const interval = setInterval(() => {
    // Twitter's primary column contains the timeline
    const timeline = document.querySelector('[data-testid="primaryColumn"]');
    if (timeline) {
      clearInterval(interval);

      injectStyles();
      createOverlay();
      scanTweets();

      // Watch for new tweets as user scrolls
      const observer = new MutationObserver(() => {
        scanTweets();
        updatePositions();
      });
      observer.observe(timeline, { childList: true, subtree: true });

      window.addEventListener("scroll", updatePositions, { passive: true });
      window.addEventListener("resize", updatePositions, { passive: true });

      // Retry pending tweets (for slow image/text loading)
      setInterval(() => {
        if (pendingRetry.size > 0) scanTweets();
      }, 1500);
    }
  }, 500);
}

// ------------------------------
// Twitter is a SPA — re-init on navigation
// (e.g. clicking from Home to Profile and back)
// ------------------------------
let lastUrl = location.href;
new MutationObserver(() => {
  if (location.href !== lastUrl) {
    lastUrl = location.href;
    removeAllBadges();
    waitForTimeline();
  }
}).observe(document, { subtree: true, childList: true });

// Start!
waitForTimeline();