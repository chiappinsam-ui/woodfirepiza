(() => {
  // ---- Guard so it only loads once
  if (window.__IMG_EDITOR_LOADED) return;
  window.__IMG_EDITOR_LOADED = true;

  const EDIT_FLAG = "__EDIT_MODE__";
  const TOKEN_KEY = "__ADMIN_TOKEN__";

  const state = {
    open: false,
    editing: false,
    token: "",
    pickerImg: null,
    pickerBg: null,
    pickerSlot: null,
  };

  function forceImgSrc(img, url) {
    // If srcset exists, the browser may ignore img.src and keep showing a srcset candidate
    img.removeAttribute("srcset");
    img.removeAttribute("sizes");

    // Some WP themes also stash lazy attrs; clear the common ones
    img.removeAttribute("data-srcset");
    img.removeAttribute("data-sizes");

    img.src = url;
  }

  const isEdit = () => sessionStorage.getItem(EDIT_FLAG) === "1";
  const getToken = () => sessionStorage.getItem(TOKEN_KEY) || "";

  // Expose simple hooks for debugging
  window.__IMG_EDITOR__ = {
    open: () => openModal(true),
    close: () => closeModal(),
    isEdit,
  };

  // ---------- Styles (modal)
  function ensureStyles() {
    if (document.getElementById("__imgEditorStyles")) return;
    const style = document.createElement("style");
    style.id = "__imgEditorStyles";
    style.textContent = `
      img.__imgEditable { outline: 2px dashed rgba(0,255,255,.35); cursor: pointer; }
      img.__imgEditable:hover { outline-color: rgba(0,255,255,.85); }
      .__editableBg { outline: 2px dashed rgba(0,255,255,.35); cursor: pointer; }
      .__editableBg:hover { outline-color: rgba(0,255,255,.85); }

      #__imgEditorModal {
        position: fixed; inset: 0; z-index: 1000000;
        display: none; align-items: center; justify-content: center;
        background: rgba(0,0,0,.45);
      }
      #__imgEditorModal[data-open="1"] { display: flex; }
      #__imgEditorModal .panel {
        width: 360px; max-width: calc(100% - 24px);
        background: rgba(0,0,0,.88);
        border: 1px solid rgba(255,255,255,.18);
        border-radius: 14px;
        padding: 14px;
        box-shadow: 0 18px 50px rgba(0,0,0,.55);
        color: #fff;
        font-family: Arial, sans-serif;
      }
      #__imgEditorModal h4 { margin: 0 0 10px; font-size: 15px; letter-spacing: .3px; }
      #__imgEditorModal .row { margin-bottom: 10px; }
      #__imgEditorModal label { display:block; font-size: 12px; opacity: .82; margin-bottom: 4px; }
      #__imgEditorModal input {
        width: 100%; box-sizing: border-box;
        padding: 10px 10px;
        border-radius: 10px;
        border: 1px solid rgba(255,255,255,.22);
        background: rgba(255,255,255,.08);
        color: #fff;
        font-size: 13px;
        outline: none;
      }
      #__imgEditorModal .actions {
        display: grid; grid-template-columns: repeat(2, minmax(0, 1fr));
        gap: 8px;
      }
      #__imgEditorModal button {
        cursor: pointer;
        border: 1px solid rgba(255,255,255,.24);
        background: rgba(255,255,255,.10);
        color: #fff;
        padding: 10px 10px;
        border-radius: 10px;
        font-size: 13px;
      }
      #__imgEditorModal button:hover { background: rgba(255,255,255,.16); }
      #__imgEditorModal .hint { margin-top: 10px; font-size: 11px; opacity: .7; }
      #__imgEditorModal .error { margin-top: 8px; font-size: 12px; color: #fca5a5; min-height: 16px; }
    `;
    document.head.appendChild(style);
  }

  // ---------- Hashing / slot selection
  function fallbackHashHex(str) {
    // simple stable hash (NOT crypto) for environments without crypto.subtle
    let h1 = 0x811c9dc5;
    for (let i = 0; i < str.length; i++) {
      h1 ^= str.charCodeAt(i);
      h1 = (h1 * 0x01000193) >>> 0;
    }
    return ("00000000" + h1.toString(16)).slice(-8).repeat(3); // 24 hex chars
  }

  async function sha256Hex(str) {
    if (!crypto?.subtle) return fallbackHashHex(str);
    const enc = new TextEncoder().encode(str);
    const buf = await crypto.subtle.digest("SHA-256", enc);
    const arr = Array.from(new Uint8Array(buf));
    return arr.map(b => b.toString(16).padStart(2, "0")).join("");
  }

  function stableImgKey(img) {
    // Use the rendered URL if available
    const src = img.currentSrc || img.src || "";

    // Assign a stable per-page index based on DOM order (only once)
    if (!img.dataset.editIdx) {
      const all = Array.from(document.images);
      const idx = all.indexOf(img);
      img.dataset.editIdx = String(idx >= 0 ? idx : 0);
    }

    // Key is per-page + per-image-position + url
    return `${location.pathname}::${img.dataset.editIdx}::${src}`;
  }

  async function hashToSlot(key) {
    const hex = await sha256Hex(key);
    return "img_" + hex.slice(0, 24);
  }

  async function makeSlot(img) {
    const ds = (img.dataset && img.dataset.slot) ? img.dataset.slot.trim() : "";
    if (ds) return ds;
    const key = stableImgKey(img);
    return hashToSlot(key);
  }

  function isSkippable(img) {
    if (!img) return true;
    if (img.dataset && img.dataset.noedit === "1") return true;

    const src = img.currentSrc || img.src || "";
    if (!src) return true;
    if (src.startsWith("data:")) return true;
    if (src.toLowerCase().endsWith(".svg")) return true;

    // ignore tiny UI icons
    if ((img.naturalWidth && img.naturalWidth < 80) || (img.naturalHeight && img.naturalHeight < 80)) return true;
    return false;
  }

  // ---------- Apply manifest (shows uploads to normal visitors too)
  async function applyManifestToImages() {
    let manifest = {};
    try {
      const res = await fetch("/manifest.json", { cache: "no-store" });
      if (!res.ok) return;
      manifest = await res.json();
    } catch {
      return;
    }

    const imgs = Array.from(document.images);
    for (const img of imgs) {
      if (isSkippable(img)) continue;
      const slot = await makeSlot(img);
      if (manifest[slot]) {
        forceImgSrc(img, `/media/${encodeURIComponent(slot)}?v=${manifest[slot].updated || Date.now()}`);
      }
    }
  }

  async function applyManifestToBackgrounds() {
    let manifest = {};
    try {
      const res = await fetch("/manifest.json", { cache: "no-store" });
      if (!res.ok) return;
      manifest = await res.json();
    } catch {
      return;
    }

    document.querySelectorAll("[data-bg-slot]").forEach((el) => {
      const slot = el.getAttribute("data-bg-slot");
      if (!slot) return;
      const info = manifest[slot];
      if (!info) return;
      el.style.backgroundImage = `url(/media/${encodeURIComponent(slot)}?v=${info.updated || Date.now()})`;
    });
  }

  // ---------- Backend calls
  async function doUpload(slot, file) {
    const token = getToken();
    if (!token) throw new Error("No admin token set.");

    const form = new FormData();
    form.append("file", file);

    const res = await fetch(`/admin/upload/${encodeURIComponent(slot)}`, {
      method: "POST",
      headers: { "X-Admin-Token": token },
      body: form
    });

    if (!res.ok) throw new Error(await res.text());
  }

  async function doDelete(slot) {
    const token = getToken();
    if (!token) throw new Error("No admin token set.");

    const res = await fetch(`/admin/delete/${encodeURIComponent(slot)}`, {
      method: "DELETE",
      headers: { "X-Admin-Token": token }
    });

    if (!res.ok) throw new Error(await res.text());
  }

  // ---------- File picker
  const picker = document.createElement("input");
  picker.type = "file";
  picker.accept = "image/*";
  picker.style.display = "none";

  picker.addEventListener("change", async () => {
    const file = picker.files?.[0];
    const target = state.pickerImg || state.pickerBg;
    if (!file || !target || !state.pickerSlot) return;

    try {
      await doUpload(state.pickerSlot, file);
      const newUrl = `/media/${encodeURIComponent(state.pickerSlot)}?v=${Date.now()}`;

      if (state.pickerImg) {
        forceImgSrc(state.pickerImg, newUrl);
      } else if (state.pickerBg) {
        state.pickerBg.style.backgroundImage = `url("${newUrl}")`;
      }
    } catch (err) {
      alert("Upload failed:\n" + (err?.message || String(err)));
    } finally {
      picker.value = "";
    }
  });

  // ---------- Edit mode binding (click any image to replace)
  const bound = new WeakSet();
  const boundBg = new WeakSet();

  async function bindImage(img) {
    if (isSkippable(img)) return;
    if (bound.has(img)) return;
    bound.add(img);

    img.classList.add("__imgEditable");
    img.title = "Click to replace this image";

    img.addEventListener("click", async (e) => {
      if (!isEdit()) return;
      e.preventDefault();
      e.stopPropagation();

      state.pickerImg = img;
      state.pickerBg = null;
      state.pickerSlot = await makeSlot(img);

    picker.value = "";
    picker.click();
    }, true);
  }

  function makeBgEditable(el) {
    const slot = el.getAttribute("data-bg-slot");
    if (!slot) return;
    if (boundBg.has(el)) return;
    boundBg.add(el);

    el.classList.add("__editableBg");
    el.title = "Click to replace this background image";

    el.addEventListener("click", (e) => {
      if (!isEdit()) return;

      // don’t hijack clicks on real links/buttons inside the slide
      const t = e.target;
      if (t && (t.closest("a, button, input, textarea, select, label"))) return;

      e.preventDefault();
      e.stopPropagation();

      state.pickerBg = el;
      state.pickerImg = null;
      state.pickerSlot = slot;

      picker.value = "";
      picker.click();
    }, true);
  }

  const mo = new MutationObserver((mutations) => {
    for (const m of mutations) {
      for (const node of m.addedNodes) {
        if (!node) continue;
        if (node.tagName === "IMG") bindImage(node);
        if (node.nodeType === 1 && node.hasAttribute("data-bg-slot")) makeBgEditable(node);
        if (node.querySelectorAll) {
          node.querySelectorAll("img").forEach(bindImage);
          node.querySelectorAll("[data-bg-slot]").forEach(makeBgEditable);
        }
      }
    }
  });

  function enableEditMode() {
    ensureStyles();
    Array.from(document.images).forEach(bindImage);
    document.querySelectorAll("[data-bg-slot]").forEach(makeBgEditable);
    mo.observe(document.documentElement, { childList: true, subtree: true });
    state.editing = true;
  }

  function disableEditMode() {
    sessionStorage.removeItem(EDIT_FLAG);
    // easiest clean exit so we remove outlines/observers cleanly
    const url = new URL(location.href);
    url.searchParams.delete("edit");
    location.href = url.toString();
  }

  // ---------- Modal (login menu)
  const modal = document.createElement("div");
  modal.id = "__imgEditorModal";
  modal.innerHTML = `
    <div class="panel">
      <h4>Image Editor Admin</h4>
      <div class="row">
        <label>Admin token</label>
        <input type="password" data-field="token" placeholder="Paste your ADMIN token…" />
      </div>
      <div class="actions">
        <button type="button" data-action="enable">Enable edit</button>
        <button type="button" data-action="disable">Disable / exit</button>
        <button type="button" data-action="close">Close</button>
        <button type="button" data-action="clear">Clear token</button>
      </div>
      <div class="error" data-field="error"></div>
      <div class="hint">
        Shortcut: Ctrl + Alt + E<br/>
        Force open: add <b>?edit=1</b> to the URL
      </div>
    </div>
  `;

  const tokenInput = modal.querySelector('[data-field="token"]');
  const errorEl = modal.querySelector('[data-field="error"]');

  function setError(msg) {
    errorEl.textContent = msg || "";
  }

  function openModal(focusToken = false) {
    ensureStyles();
    modal.dataset.open = "1";
    state.open = true;
    // preload stored token if any
    tokenInput.value = getToken() || "";
    setError("");
    if (focusToken) setTimeout(() => tokenInput.focus(), 0);
  }

  function closeModal() {
    modal.dataset.open = "0";
    state.open = false;
    setError("");
  }

  modal.addEventListener("click", (e) => {
    if (e.target === modal) closeModal(); // click outside panel
  });

  modal.querySelector('[data-action="enable"]').addEventListener("click", () => {
    const t = tokenInput.value.trim();
    if (!t) return setError("Enter your admin token first.");
    sessionStorage.setItem(TOKEN_KEY, t);
    sessionStorage.setItem(EDIT_FLAG, "1");
    enableEditMode();
    closeModal();
  });

  modal.querySelector('[data-action="disable"]').addEventListener("click", () => {
    disableEditMode();
  });

  modal.querySelector('[data-action="close"]').addEventListener("click", () => {
    closeModal();
  });

  modal.querySelector('[data-action="clear"]').addEventListener("click", () => {
    sessionStorage.removeItem(TOKEN_KEY);
    tokenInput.value = "";
    setError("Token cleared (this tab only).");
  });

  function openLoginAndEnable() {
    const token = prompt("Admin token:");
    if (!token) return;
    sessionStorage.setItem(TOKEN_KEY, token);
    sessionStorage.setItem(EDIT_FLAG, "1");
    enableEditMode();
  }

  // expose a manual opener (super useful for testing)
  window.__OPEN_IMAGE_EDITOR_LOGIN__ = openLoginAndEnable;

  function hotkey(e) {
    const keyIsE = (e.code === "KeyE") || ((e.key || "").toLowerCase() === "e");
    if (!(e.ctrlKey && e.altKey && keyIsE)) return;

    // ignore when typing in inputs
    const t = e.target;
    const tag = t && t.tagName ? t.tagName.toLowerCase() : "";
    if (tag === "input" || tag === "textarea" || t?.isContentEditable) return;

    e.preventDefault();

    if (!isEdit()) {
      openModal(true); // only open the menu
    } else {
      disableEditMode(); // clean exit
    }
  }

  // capture=true makes it MUCH harder for other scripts to swallow it
  window.addEventListener("keydown", hotkey, true);
  document.addEventListener("keydown", hotkey, true);

  // ---------- Init on load
  document.addEventListener("DOMContentLoaded", () => {
    ensureStyles();                 // ✅ inject CSS immediately
    modal.dataset.open = "0";       // ✅ make sure it starts hidden

    document.body.appendChild(picker);
    document.body.appendChild(modal);
    // document.body.appendChild(xWrap); // ❌ leave this out if you don’t want the floating X

    applyManifestToImages();
    applyManifestToBackgrounds();

    const params = new URLSearchParams(location.search);

    // if you still want ?edit=1 to open the menu:
    if (params.get("edit") === "1" && !isEdit()) {
      openModal(true);
    }

    if (isEdit()) {
      enableEditMode();
      // addBadge(...)  // ❌ leave out so the bottom badge never comes back
    }
  });
})();
