// ==============================
// BobRossRocks – Video URL Interceptor (MAIN world)
// Patches fetch() to read Twitter's GraphQL API responses,
// which contain the actual mp4 URLs for videos.
// Stores them in window.__BR_VIDS for Content.js to consume.
// ==============================

window.__BR_VIDS = [];

const _origFetch = window.fetch;
window.fetch = async function (...args) {
  const response = await _origFetch.apply(this, args);

  try {
    const url = typeof args[0] === 'string' ? args[0] : (args[0]?.url || '');
    // Only intercept Twitter API responses (GraphQL or legacy API)
    if (url.includes('/graphql/') || url.includes('/i/api/')) {
      // Clone so Twitter's own code still gets to read the response
      const clone = response.clone();
      clone.json().then(json => {
        extractVideoUrls(json);
      }).catch(() => {});
    }
  } catch (e) {
    // Never break normal fetch behavior
  }

  return response;
};

// Also patch XHR for older API calls
const _xhrOpen = XMLHttpRequest.prototype.open;
const _xhrSend = XMLHttpRequest.prototype.send;

XMLHttpRequest.prototype.open = function (method, url, ...rest) {
  this.__br_url = url;
  return _xhrOpen.apply(this, [method, url, ...rest]);
};

XMLHttpRequest.prototype.send = function (...args) {
  if (this.__br_url && (this.__br_url.includes('/graphql/') || this.__br_url.includes('/i/api/'))) {
    this.addEventListener('load', function () {
      try {
        const json = JSON.parse(this.responseText);
        extractVideoUrls(json);
      } catch (e) {}
    });
  }
  return _xhrSend.apply(this, args);
};

// ── Recursively walk JSON to find video_info.variants ──────────────────────
function extractVideoUrls(obj) {
  if (!obj || typeof obj !== 'object') return;

  // Check if this node has video_info with variants
  if (obj.video_info && Array.isArray(obj.video_info.variants)) {
    const mp4s = obj.video_info.variants
      .filter(v => v.content_type === 'video/mp4' && v.url)
      .sort((a, b) => (b.bitrate || 0) - (a.bitrate || 0));

    if (mp4s.length > 0) {
      const best = mp4s[0].url;
      const clean = best.split('?')[0];
      if (!window.__BR_VIDS.some(v => v.clean === clean)) {
        window.__BR_VIDS.push({ url: best, clean, ts: Date.now() });
        // Keep only last 100
        if (window.__BR_VIDS.length > 100) window.__BR_VIDS.shift();
        // Dispatch event so Content.js (ISOLATED world) can receive it
        document.dispatchEvent(new CustomEvent('__br_video', {
          detail: { url: best }
        }));
      }
    }
  }

  // Recurse into arrays and objects
  if (Array.isArray(obj)) {
    for (const item of obj) extractVideoUrls(item);
  } else {
    for (const key of Object.keys(obj)) {
      if (typeof obj[key] === 'object' && obj[key] !== null) {
        extractVideoUrls(obj[key]);
      }
    }
  }
}
