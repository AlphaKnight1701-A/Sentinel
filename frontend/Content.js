// ==============================
// BobRossRocks - Facebook Side Notes (Robust v2)
// ==============================

const badges = new Map();   // post el → badge el
const pendingRetry = new Set(); // posts waiting for text to load
let taggingEnabled = true;

// ------------------------------
// Extract the main post text
// Strategy order:
//   1. data-ad-comet-preview="message"  (Facebook's message attr)
//   2. Longest visible div[dir='auto']  (generic text container)
//   3. Any span with enough text        (last resort)
// ------------------------------
function extractPostText(post) {
  // Strategy 1 – Facebook's internal "message" marker
  const msgEl = post.querySelector('[data-ad-comet-preview="message"], [data-ad-preview="message"]');
  if (msgEl) {
    const t = msgEl.innerText.trim();
    if (t.length >= 10) return truncate(t);
  }

  // Strategy 2 – longest visible div[dir='auto'] that isn't a name/label
  const dirAutos = Array.from(post.querySelectorAll("div[dir='auto'], span[dir='auto']"))
    .filter(el => {
      // must be visible
      if (el.offsetParent === null) return false;
      const text = el.innerText.trim();
      // skip very short strings (names, labels)
      return text.length >= 20;
    });

  if (dirAutos.length > 0) {
    const best = dirAutos.reduce((a, b) =>
      b.innerText.trim().length > a.innerText.trim().length ? b : a
    );
    return truncate(best.innerText.trim());
  }

  // Strategy 3 – any span with reasonable text
  const spans = Array.from(post.querySelectorAll("span"))
    .filter(el => el.offsetParent !== null && el.innerText.trim().length >= 30);

  if (spans.length > 0) {
    const best = spans.reduce((a, b) =>
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
// Only grab TOP-LEVEL articles
// (avoids duplicating badges for
//  comment articles nested inside)
// ------------------------------
function getTopLevelPosts() {
  return Array.from(document.querySelectorAll("div[role='article']")).filter(el => {
    // check that no ancestor is also a role=article
    let parent = el.parentElement;
    while (parent) {
      if (parent.getAttribute && parent.getAttribute("role") === "article") return false;
      parent = parent.parentElement;
    }
    return true;
  });
}

// ------------------------------
// Create badge for a post
// ------------------------------
function createBadge(post) {
  if (!taggingEnabled) return;
  if (badges.has(post)) {
    // already has a badge — update its text in case it loaded later
    const text = extractPostText(post);
    if (text) {
      badges.get(post).querySelector(".bobross-text").innerText = text;
      pendingRetry.delete(post);
    }
    return;
  }

  const text = extractPostText(post);
  if (!text) {
    pendingRetry.add(post); // retry later when content loads
    return;
  }

  const badge = document.createElement("div");
  badge.className = "bobross-side-badge";
  badge.innerHTML = `
    <div class="bobross-badge-header">📝 Post Note</div>
    <div class="cobross-divider"></div>
    <div class="bobross-text">${escapeHtml(text)}</div>
  `;

  document.body.appendChild(badge);
  badges.set(post, badge);
  positionBadge(post, badge);
}

function escapeHtml(str) {
  return str.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}

// ------------------------------
// Position badge to the right of post
// ------------------------------
function positionBadge(post, badge) {
  const rect = post.getBoundingClientRect();
  // Use fixed positioning relative to viewport
  const top = rect.top + window.scrollY;
  const left = rect.right + window.scrollX + 14;
  badge.style.top = `${top}px`;
  badge.style.left = `${left}px`;
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
// Scan all top-level posts
// ------------------------------
function scanPosts() {
  if (!taggingEnabled) return;
  getTopLevelPosts().forEach(post => createBadge(post));

  // Retry posts that didn't have text yet
  if (pendingRetry.size > 0) {
    pendingRetry.forEach(post => {
      if (document.body.contains(post)) {
        createBadge(post);
      } else {
        pendingRetry.delete(post);
      }
    });
  }
}

// ------------------------------
// Update badge positions on scroll/resize
// ------------------------------
function updatePositions() {
  badges.forEach((badge, post) => {
    if (!document.body.contains(post)) {
      badge.remove();
      badges.delete(post);
    } else {
      positionBadge(post, badge);
    }
  });
}

// ------------------------------
// Control overlay UI
// ------------------------------
function createOverlay() {
  const overlay = document.createElement("div");
  overlay.id = "bobross-overlay";
  overlay.innerHTML = `
    <div id="bobross-panel">
      <div id="bobross-title">🎨 BobRossRocks</div>
      <div id="bobross-sub">Post notes on the side</div>
      <button id="toggle-btn">Disable</button>
    </div>
  `;
  document.body.appendChild(overlay);

  document.getElementById("toggle-btn").addEventListener("click", () => {
    taggingEnabled = !taggingEnabled;
    document.getElementById("toggle-btn").innerText = taggingEnabled ? "Disable" : "Enable";
    if (!taggingEnabled) removeAllBadges();
    else scanPosts();
  });
}

// ------------------------------
// Inject CSS
// ------------------------------
function injectStyles() {
  const style = document.createElement("style");
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
      background: linear-gradient(135deg, #1a1a2e, #16213e);
      color: white;
      padding: 14px 18px;
      border-radius: 14px;
      width: 190px;
      text-align: center;
      box-shadow: 0 8px 32px rgba(0,0,0,0.45);
      border: 1px solid rgba(255,255,255,0.08);
    }
    #bobross-title {
      font-size: 15px;
      font-weight: 700;
      letter-spacing: 0.3px;
    }
    #bobross-sub {
      font-size: 11px;
      opacity: 0.6;
      margin: 4px 0 10px;
    }
    #bobross-panel button {
      padding: 6px 16px;
      border-radius: 20px;
      cursor: pointer;
      font-weight: 600;
      font-size: 12px;
      background: #e91e8c;
      color: white;
      border: none;
      transition: opacity 0.2s;
    }
    #bobross-panel button:hover { opacity: 0.8; }

    /* ===== Side Note Badges ===== */
    .bobross-side-badge {
      position: absolute;
      background: linear-gradient(135deg, #ffffff, #f0f4ff);
      color: #1a1a2e;
      padding: 10px 12px;
      border-radius: 12px;
      width: 230px;
      font-size: 11.5px;
      line-height: 1.5;
      box-shadow: 0 4px 18px rgba(0,0,0,0.18);
      z-index: 999999;
      pointer-events: none;
      border-left: 4px solid #e91e8c;
      word-break: break-word;
      white-space: pre-wrap;
    }
    .bobross-badge-header {
      font-size: 10px;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.8px;
      color: #e91e8c;
      margin-bottom: 5px;
    }
    .bobross-text {
      color: #2d2d45;
      font-size: 11.5px;
    }
  `;
  document.head.appendChild(style);
}

// ------------------------------
// Wait for the feed, then start
// ------------------------------
function waitForFeed() {
  const interval = setInterval(() => {
    // Facebook uses role="feed" for the main news feed
    const feed = document.querySelector("div[role='feed']");
    if (feed) {
      clearInterval(interval);

      injectStyles();
      createOverlay();
      scanPosts();

      // Watch for new posts as user scrolls
      const observer = new MutationObserver(() => {
        scanPosts();
        updatePositions();
      });
      observer.observe(feed, { childList: true, subtree: true });

      // Reposition on scroll/resize
      window.addEventListener("scroll", updatePositions, { passive: true });
      window.addEventListener("resize", updatePositions, { passive: true });

      // Periodic retry for pending posts (handles slow-loading content)
      setInterval(() => {
        if (pendingRetry.size > 0) scanPosts();
      }, 1500);
    }
  }, 500);
}

// Start!
waitForFeed();