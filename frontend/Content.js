// ==============================
// BobRossRocks - Full Version
// ==============================

let taggingEnabled = true;

// ------------------------------
// Overlay UI
// ------------------------------
function createOverlay() {
  const overlay = document.createElement("div");
  overlay.id = "bobross-overlay";

  overlay.innerHTML = `
    <div id="bobross-panel">
      <h2>🎨 BobRossRocks</h2>
      <button id="toggle-btn">Disable Tags</button>
    </div>
  `;

  document.body.appendChild(overlay);

  document.getElementById("toggle-btn").addEventListener("click", () => {
    taggingEnabled = !taggingEnabled;
    document.getElementById("toggle-btn").innerText =
      taggingEnabled ? "Disable Tags" : "Enable Tags";

    if (!taggingEnabled) {
      removeAllTags();
    } else {
      processPosts();
    }
  });
}

// ------------------------------
// Inject All Styles (Overlay + Tags)
// ------------------------------
function injectStyles() {
  const style = document.createElement("style");
  style.textContent = `
    /* Overlay */
    #bobross-overlay {
      position: fixed;
      top: 20px;
      right: 20px;
      z-index: 999999999;
    }

    #bobross-panel {
      background: linear-gradient(135deg, #ff6b6b, #f7d794);
      padding: 18px;
      border-radius: 14px;
      box-shadow: 0 12px 28px rgba(0,0,0,0.35);
      font-family: Arial, sans-serif;
      color: white;
      width: 220px;
      text-align: center;
    }

    #bobross-panel h2 {
      margin: 0 0 10px 0;
      font-size: 16px;
    }

    #bobross-panel button {
      padding: 8px 12px;
      border: none;
      border-radius: 8px;
      cursor: pointer;
      font-weight: bold;
    }

    #bobross-panel button:hover {
      opacity: 0.85;
    }

    /* Inline Tag */
    .bobross-inline-tag {
      background: #ff6b6b;
      color: white;
      padding: 3px 8px;
      border-radius: 12px;
      font-size: 11px;
      margin-left: 6px;
      font-weight: bold;
    }

    /* Post Border Highlight */
    div[role="article"].bobross-highlight {
      border: 3px solid #ff6b6b !important;
      border-radius: 14px !important;
      box-shadow: 0 0 12px rgba(255,107,107,0.4);
    }
  `;
  document.head.appendChild(style);
}

// ------------------------------
// Add Tag + Border To Posts
// ------------------------------
function processPosts() {
  if (!taggingEnabled) return;

  const posts = document.querySelectorAll('div[role="article"]');

  posts.forEach(post => {
    // Add border highlight (React-safe via class)
    post.classList.add("bobross-highlight");

    const header = post.querySelector("h2, h3");
    if (!header) return;

    // Prevent duplicates
    if (!header.querySelector(".bobross-inline-tag")) {
      const tag = document.createElement("span");
      tag.innerText = " 🎨 Bob Ross Approved";
      tag.className = "bobross-inline-tag";
      header.appendChild(tag);
    }
  });
}

// ------------------------------
// Remove All Tags + Borders
// ------------------------------
function removeAllTags() {
  document
    .querySelectorAll(".bobross-inline-tag")
    .forEach(tag => tag.remove());

  document
    .querySelectorAll("div[role='article']")
    .forEach(post => post.classList.remove("bobross-highlight"));
}

// ------------------------------
// Mutation Observer (React-proof)
// ------------------------------
const observer = new MutationObserver(() => {
  processPosts();
});

// ------------------------------
// Init
// ------------------------------
window.addEventListener("load", () => {
  injectStyles();
  createOverlay();
  processPosts();

  observer.observe(document.body, {
    childList: true,
    subtree: true
  });

  // Extra safety loop (in case React replaces nodes)
  setInterval(processPosts, 1000);
});