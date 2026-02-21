// ==============================
// BobRossRocks – Background Service Worker
// Uses chrome.webRequest to intercept ALL video.twimg.com requests,
// including those from service workers (which the content-script patch can't see).
// ==============================

chrome.webRequest.onBeforeRequest.addListener(
  (details) => {
    const url = details.url;
    // Only care about HLS master playlists and direct mp4 clips
    // Skip segment playlists (they have /seg/ or are numeric-only filenames)
    if (!isMasterVideoUrl(url)) return;

    chrome.tabs.sendMessage(details.tabId, {
      type: 'BR_VIDEO_URL',
      url: url
    }).catch(() => {
      // Content script may not be ready yet — silently ignore
    });
  },
  {
    urls: ['*://*.twimg.com/*'],
    types: ['xmlhttprequest', 'media', 'other', 'fetch']
  }
);

function isMasterVideoUrl(url) {
  const path = url.split('?')[0];
  if (path.includes('.mp4')) return true;
  if (!path.includes('.m3u8')) return false;
  // Skip sub-quality playlists like /240x426/index.m3u8
  // Master playlist is usually just /index.m3u8 or /playlist.m3u8
  // We accept all m3u8 and deduplicate in the content script
  return true;
}
