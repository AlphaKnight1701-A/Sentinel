// ==============================
// BobRossRocks - Twitter/X Side Notes
// ==============================
// Twitter uses stable data-testid attributes — much more reliable than class names.
// Key selectors:
//   Tweet container : article[data-testid="tweet"]
//   Tweet text      : div[data-testid="tweetText"]
//   Timeline        : div[data-testid="primaryColumn"]

const badges = new Map();        // tweet el → badge el
const pendingRetry = new Set();  // tweets where text hasn't loaded
const hiddenTweets = new Set();  // tweet el → {tweet, cell} - hidden posts
let taggingEnabled = true;

// ── Video URL cache (populated via CustomEvent from interceptor.js) ──────
const capturedVideoUrls = [];

document.addEventListener('__br_video', (e) => {
  if (e.detail && e.detail.url) {
    capturedVideoUrls.push(e.detail.url);
    // Re-scan tweets so any video tweet that was missing a URL gets updated
    scanTweets();
  }
});

// ------------------------------
// Extract tweet text
// ------------------------------
function extractTweetText(tweet) {
  const textEl = tweet.querySelector('[data-testid="tweetText"]');
  if (textEl) {
    const text = textEl.innerText.trim();
    if (text.length >= 1) return truncate(text);
  }

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
// Extract profile image URL
// ------------------------------
function extractProfileImage(tweet) {
  const avatarImg = tweet.querySelector('div[data-testid="Tweet-User-Avatar"] img');
  if (avatarImg) return avatarImg.src || null;
  const imgs = tweet.querySelectorAll('a[role="link"] img[src*="profile_images"]');
  if (imgs.length > 0) return imgs[0].src;
  return null;
}

// ------------------------------
// Extract username & display name
// ------------------------------
function extractUserInfo(tweet) {
  const userNameEl = tweet.querySelector('[data-testid="User-Name"]');
  if (!userNameEl) return { displayName: null, handle: null };

  const spans = Array.from(userNameEl.querySelectorAll('span'));
  let displayName = null;
  let handle = null;

  for (const span of spans) {
    const t = span.innerText.trim();
    if (!t) continue;
    if (t.startsWith('@')) {
      handle = t;
    } else if (!displayName && t.length > 0 && !t.includes('·') && !t.match(/^\d+[smhd]$/)) {
      displayName = t;
    }
  }

  if (!handle) {
    const profileLink = userNameEl.querySelector('a[href^="/"]');
    if (profileLink) {
      const href = profileLink.getAttribute('href');
      if (href && href.startsWith('/') && !href.includes('?')) {
        handle = '@' + href.slice(1);
      }
    }
  }

  return { displayName, handle };
}

// ------------------------------
// Extract direct video mp4 URL
// Uses capturedVideoUrls (from interceptor.js via CustomEvent)
// ------------------------------
function extractVideoUrl(tweet) {
  const hasVideo = !!(tweet.querySelector('[data-testid="videoPlayer"]') ||
                      tweet.querySelector('video'));
  if (!hasVideo) return null;

  // If we already assigned a URL to this tweet, reuse it
  if (tweet.__br_video_url) return tweet.__br_video_url;

  // Claim the next available mp4 URL
  if (capturedVideoUrls.length > 0) {
    const url = capturedVideoUrls.shift();
    tweet.__br_video_url = url;
    return url;
  }

  // URL not captured yet — will be picked up on next scan after event fires
  return null;
}


// ------------------------------
// Extract media image URLs (photos in tweet)
// ------------------------------
function extractMediaImages(tweet) {
  const images = [];
  // Tweet photos use data-testid="tweetPhoto"
  const photos = tweet.querySelectorAll('[data-testid="tweetPhoto"] img');
  photos.forEach(img => {
    if (img.src && !img.src.includes('profile_images')) {
      images.push(img.src);
    }
  });
  return images;
}

// ------------------------------
// Extract engagement metrics
// ------------------------------
function extractMetrics(tweet) {
  const metrics = {};

  // Reply / Comments
  const replyBtn = tweet.querySelector('[data-testid="reply"]');
  if (replyBtn) {
    const count = replyBtn.querySelector('[data-testid="app-text-transition-container"]');
    metrics.comments = count ? count.innerText.trim() : '0';
  }

  // Retweet / Repost
  const retweetBtn = tweet.querySelector('[data-testid="retweet"]');
  if (retweetBtn) {
    const count = retweetBtn.querySelector('[data-testid="app-text-transition-container"]');
    metrics.reposts = count ? count.innerText.trim() : '0';
  }

  // Like
  const likeBtn = tweet.querySelector('[data-testid="like"]');
  if (likeBtn) {
    const count = likeBtn.querySelector('[data-testid="app-text-transition-container"]');
    metrics.likes = count ? count.innerText.trim() : '0';
  }

  // Bookmark
  const bookmarkBtn = tweet.querySelector('[data-testid="bookmark"]');
  if (bookmarkBtn) {
    const count = bookmarkBtn.querySelector('[data-testid="app-text-transition-container"]');
    metrics.bookmarks = count ? count.innerText.trim() : '0';
  }

  // Views — Twitter shows views in an aria-label on a link near the analytics icon
  // Selector: a[href*="/analytics"] or role="link" with "Views" in aria-label
  const analyticsLink = tweet.querySelector('a[href*="/analytics"]');
  if (analyticsLink) {
    const aria = analyticsLink.getAttribute('aria-label') || '';
    const match = aria.match(/([\d,KkMm\.]+)\s*[Vv]iew/);
    if (match) {
      metrics.views = match[1];
    } else {
      const viewText = analyticsLink.innerText.trim();
      if (viewText) metrics.views = viewText;
    }
  }

  // Fallback for views: look for aria-label containing "views" anywhere in tweet action group
  if (!metrics.views) {
    const actionGroup = tweet.querySelector('[role="group"]');
    if (actionGroup) {
      const allLinks = actionGroup.querySelectorAll('a, button');
      allLinks.forEach(el => {
        const aria = (el.getAttribute('aria-label') || '').toLowerCase();
        if (aria.includes('view') && !metrics.views) {
          const match = aria.match(/([\d,]+)/);
          if (match) metrics.views = match[1];
        }
      });
    }
  }

  return metrics;
}

// ------------------------------
// Get all top-level tweets
// (avoids nested quoted tweets getting their own badge)
// ------------------------------
function getTopLevelTweets() {
  return Array.from(document.querySelectorAll('article[data-testid="tweet"]')).filter(el => {
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
    // Update all fields if they loaded later
    updateBadgeContent(tweet, badges.get(tweet));
    return;
  }

  const text = extractTweetText(tweet);
  if (!text) {
    pendingRetry.add(tweet);
    return;
  }

  const badge = document.createElement("div");
  badge.className = "bobross-side-badge";
  document.body.appendChild(badge);
  badges.set(tweet, badge);

  updateBadgeContent(tweet, badge);
  positionBadge(tweet, badge);
}

function updateBadgeContent(tweet, badge) {
  const text = extractTweetText(tweet);
  const profileImg = extractProfileImage(tweet);
  const { displayName, handle } = extractUserInfo(tweet);
  const videoUrl = extractVideoUrl(tweet);
  const mediaImages = extractMediaImages(tweet);
  const metrics = extractMetrics(tweet);


  const metricItems = [
    { icon: '💬', label: 'Replies', value: metrics.comments },
    { icon: '🔁', label: 'Reposts', value: metrics.reposts },
    { icon: '❤️', label: 'Likes', value: metrics.likes },
    { icon: '👁️', label: 'Views', value: metrics.views },
    { icon: '🔖', label: 'Bookmarks', value: metrics.bookmarks },
  ].filter(m => m.value && m.value !== '0' && m.value !== '');

  const metricsHTML = metricItems.length > 0
    ? `<div class="bobross-metrics">
        ${metricItems.map(m => `
          <div class="bobross-metric-item" title="${m.label}">
            <span class="bobross-metric-icon">${m.icon}</span>
            <span class="bobross-metric-value">${escapeHtml(m.value)}</span>
            <span class="bobross-metric-label">${m.label}</span>
          </div>
        `).join('')}
      </div>`
    : '';

  const avatarHTML = profileImg
    ? `<img class="bobross-avatar" src="${escapeHtml(profileImg)}" alt="avatar" />`
    : `<div class="bobross-avatar-placeholder">👤</div>`;

  const userHTML = (displayName || handle)
    ? `<div class="bobross-user-info">
        ${avatarHTML}
        <div class="bobross-user-text">
          ${displayName ? `<div class="bobross-display-name">${escapeHtml(displayName)}</div>` : ''}
          ${handle ? `<div class="bobross-handle">${escapeHtml(handle)}</div>` : ''}
        </div>
      </div>`
    : '';

  let mediaHTML = '';
  if (videoUrl) {
    mediaHTML += `
      <div class="bobross-video-box">
        <div class="bobross-video-row">
          <span class="bobross-media-icon">🎬</span>
          <span class="bobross-video-url" title="${escapeHtml(videoUrl)}">${escapeHtml(videoUrl)}</span>
        </div>
        <a class="bobross-play-btn" href="${escapeHtml(videoUrl)}" target="_blank">▶ Watch Video ↗</a>
      </div>`;
  }
  if (mediaImages.length > 0) {
    const visibleImgs = mediaImages.slice(0, 4);
    const extra = mediaImages.length - visibleImgs.length;
    mediaHTML += `<div class="bobross-image-grid">
      ${visibleImgs.map((src, i) => {
        const isLast = i === visibleImgs.length - 1 && extra > 0;
        return `<div class="bobross-image-wrap">
          <img class="bobross-thumb" src="${escapeHtml(src)}" alt="tweet image" />
          ${isLast ? `<div class="bobross-image-more">+${extra}</div>` : ''}
        </div>`;
      }).join('')}
    </div>`;
  }
  const mediaSectionHTML = mediaHTML ? `<div class="bobross-media-section">${mediaHTML}</div>` : '';

  badge.innerHTML = `
    <div class="bobross-badge-header">
      🐦 Tweet Note
      <button class="bobross-hide-btn" title="Hide this post">✕</button>
    </div>
    ${userHTML}
    <div class="bobross-divider"></div>
    ${text ? `<div class="bobross-text">${escapeHtml(text)}</div>` : ''}
    ${metricsHTML}
    ${mediaSectionHTML}
  `;

  // Re-enable pointer events for links and the hide button
  badge.querySelectorAll('a').forEach(a => { a.style.pointerEvents = 'auto'; });
  const hideBtn = badge.querySelector('.bobross-hide-btn');
  if (hideBtn) {
    hideBtn.style.pointerEvents = 'auto';
    hideBtn.addEventListener('click', (e) => {
      e.stopPropagation();
      hideTweet(tweet, badge);
    });
  }
}

function escapeHtml(str) {
  if (!str) return '';
  return str
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
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
// Hide a single tweet (soft-delete)
// ------------------------------
function hideTweet(tweet, badge) {
  // Find the outermost cell/wrapper Twitter wraps each timeline item in
  const cell = tweet.closest('[data-testid="cellInnerDiv"]') || tweet;
  cell.style.display = 'none';
  badge.remove();
  badges.delete(tweet);
  hiddenTweets.add({ tweet, cell });
  updateHiddenCount();
}

function updateHiddenCount() {
  const btn = document.getElementById('restore-btn');
  if (!btn) return;
  const n = hiddenTweets.size;
  if (n === 0) {
    btn.style.display = 'none';
  } else {
    btn.style.display = '';
    btn.innerText = `👁 Unhide (${n})`;
  }
}

function restoreAllHidden() {
  hiddenTweets.forEach(({ tweet, cell }) => {
    cell.style.display = '';
  });
  hiddenTweets.clear();
  updateHiddenCount();
  scanTweets();
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
      <div id="bobross-title">Sentinel</div>
      <div id="bobross-sub">Tweet notes on the side</div>
      <div id="bobross-btn-row">
        <button id="toggle-btn">Disable</button>
        <button id="restore-btn" style="display:none">👁 Unhide (0)</button>
      </div>
    </div>
  `;
  document.body.appendChild(overlay);

  document.getElementById("toggle-btn").addEventListener("click", () => {
    taggingEnabled = !taggingEnabled;
    document.getElementById("toggle-btn").innerText = taggingEnabled ? "Disable" : "Enable";
    if (!taggingEnabled) removeAllBadges();
    else scanTweets();
  });

  document.getElementById("restore-btn").addEventListener("click", restoreAllHidden);
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
      width: 120px;
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
    #bobross-btn-row {
      display: flex;
      flex-direction: column;
      gap: 6px;
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
      width: 100%;
    }
    #restore-btn {
      background: #2d3748 !important;
      border: 1px solid rgba(255,255,255,0.15) !important;
    }
    #bobross-panel button:hover { opacity: 0.8; }

    /* ===== Tweet Side Note Badges ===== */
    .bobross-side-badge {
      position: absolute;
      background: #ffffff;
      color: #0f1923;
      padding: 10px 13px;
      border-radius: 14px;
      width: 250px;
      font-size: 12px;
      line-height: 1.5;
      box-shadow: 0 4px 20px rgba(0,0,0,0.15);
      z-index: 999999;
      pointer-events: none;
      border-left: 4px solid #1d9bf0;
      word-break: break-word;
      white-space: normal;
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
    }
    .bobross-badge-header {
      font-size: 10px;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.8px;
      color: #1d9bf0;
      margin-bottom: 7px;
      display: flex;
      align-items: center;
      justify-content: space-between;
    }
    .bobross-hide-btn {
      background: none;
      border: none;
      color: #94a3b8;
      font-size: 13px;
      line-height: 1;
      cursor: pointer;
      padding: 0 2px;
      border-radius: 4px;
      pointer-events: auto;
      transition: color 0.15s, background 0.15s;
      font-weight: 400;
    }
    .bobross-hide-btn:hover {
      color: #ef4444;
      background: #fee2e2;
    }

    /* ===== User Info Row ===== */
    .bobross-user-info {
      display: flex;
      align-items: center;
      gap: 8px;
      margin-bottom: 6px;
    }
    .bobross-avatar {
      width: 34px;
      height: 34px;
      border-radius: 50%;
      object-fit: cover;
      flex-shrink: 0;
      border: 2px solid #1d9bf0;
    }
    .bobross-avatar-placeholder {
      width: 34px;
      height: 34px;
      border-radius: 50%;
      background: #e8f4fd;
      display: flex;
      align-items: center;
      justify-content: center;
      font-size: 18px;
      flex-shrink: 0;
    }
    .bobross-user-text {
      display: flex;
      flex-direction: column;
      gap: 1px;
      min-width: 0;
    }
    .bobross-display-name {
      font-weight: 700;
      font-size: 13px;
      color: #0f1923;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }
    .bobross-handle {
      font-size: 11px;
      color: #536471;
    }

    /* ===== Divider ===== */
    .bobross-divider {
      border: none;
      border-top: 1px solid #e8eaed;
      margin: 6px 0;
    }

    /* ===== Tweet Text ===== */
    .bobross-text {
      color: #1a1a2e;
      font-size: 12px;
      margin-bottom: 8px;
      white-space: pre-wrap;
    }

    /* ===== Metrics ===== */
    .bobross-metrics {
      display: flex;
      flex-wrap: wrap;
      gap: 6px 10px;
      margin-top: 6px;
      margin-bottom: 4px;
    }
    .bobross-metric-item {
      display: flex;
      align-items: center;
      gap: 3px;
      font-size: 11px;
      color: #536471;
      white-space: nowrap;
    }
    .bobross-metric-icon {
      font-size: 12px;
    }
    .bobross-metric-value {
      font-weight: 700;
      color: #0f1923;
    }
    .bobross-metric-label {
      color: #8899a6;
      font-size: 10px;
    }

    /* ===== Media Section ===== */
    .bobross-media-section {
      margin-top: 7px;
      border-top: 1px solid #e8eaed;
      padding-top: 6px;
      display: flex;
      flex-direction: column;
      gap: 4px;
    }
    .bobross-media-row {
      display: flex;
      align-items: center;
      gap: 5px;
      font-size: 11px;
    }
    .bobross-media-icon {
      font-size: 13px;
    }
    .bobross-media-label {
      color: #536471;
      font-weight: 600;
    }
    .bobross-media-url {
      color: #1d9bf0;
      text-decoration: none;
      font-size: 11px;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
      max-width: 140px;
      pointer-events: auto;
    }
    .bobross-media-url:hover { text-decoration: underline; }
    .bobross-blob { color: #8899a6; font-style: italic; }

    /* ===== Video Box ===== */
    .bobross-video-box {
      background: #f0f7ff;
      border: 1px solid #bfdbfe;
      border-radius: 8px;
      padding: 7px 9px;
      display: flex;
      flex-direction: column;
      gap: 5px;
    }
    .bobross-video-row {
      display: flex;
      align-items: center;
      gap: 5px;
      font-size: 11px;
    }
    .bobross-video-url {
      color: #374151;
      font-size: 10px;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
      flex: 1;
      min-width: 0;
      font-family: monospace;
    }
    .bobross-play-btn {
      display: block;
      text-align: center;
      background: #1d9bf0;
      color: #fff;
      text-decoration: none;
      font-size: 11px;
      font-weight: 700;
      border-radius: 6px;
      padding: 5px 0;
      pointer-events: auto;
      transition: background 0.15s;
    }
    .bobross-play-btn:hover { background: #1a8cd8; }

    /* ===== Image Grid ===== */
    .bobross-image-grid {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 4px;
      margin-top: 7px;
      border-radius: 10px;
      overflow: hidden;
    }
    .bobross-image-grid:has(.bobross-image-wrap:only-child) {
      grid-template-columns: 1fr;
    }
    .bobross-image-wrap {
      position: relative;
      aspect-ratio: 16 / 9;
      overflow: hidden;
      background: #e8eaed;
    }
    .bobross-thumb {
      width: 100%;
      height: 100%;
      object-fit: cover;
      display: block;
      border-radius: 0;
    }
    .bobross-image-more {
      position: absolute;
      inset: 0;
      background: rgba(0, 0, 0, 0.55);
      color: white;
      font-size: 18px;
      font-weight: 700;
      display: flex;
      align-items: center;
      justify-content: center;
      border-radius: 0;
    }
  `;
  document.head.appendChild(style);
}

// ------------------------------
// Wait for Twitter's timeline to load
// ------------------------------
function waitForTimeline() {
  const interval = setInterval(() => {
    const timeline = document.querySelector('[data-testid="primaryColumn"]');
    if (timeline) {
      clearInterval(interval);

      injectStyles();
      createOverlay();
      scanTweets();

      const observer = new MutationObserver(() => {
        scanTweets();
        updatePositions();
      });
      observer.observe(timeline, { childList: true, subtree: true });

      window.addEventListener("scroll", updatePositions, { passive: true });
      window.addEventListener("resize", updatePositions, { passive: true });

      setInterval(() => {
        if (pendingRetry.size > 0) scanTweets();
      }, 1500);
    }
  }, 500);
}

// ------------------------------
// Twitter is a SPA — re-init on navigation
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