(() => {
  const EDIT_FLAG = "__EDIT_MODE__";
  const TOKEN_KEY = "__ADMIN_TOKEN__";

  const isEdit = () => sessionStorage.getItem(EDIT_FLAG) === "1";
  const getToken = () => sessionStorage.getItem(TOKEN_KEY) || "";

  // small UI
  function addBadge(text) {
    let badge = document.querySelector(".__editBadge");
    if (!badge) {
      badge = document.createElement("div");
      badge.className = "__editBadge";
      document.body.appendChild(badge);
    }
    badge.textContent = text;
  }

  function addStyles() {
    if (document.getElementById("__editStyles")) return;
    const style = document.createElement("style");
    style.id = "__editStyles";
    style.textContent = `
      img.__editable { outline: 2px dashed rgba(0,255,255,.35); cursor: pointer; }
      img.__editable:hover { outline-color: rgba(0,255,255,.85); }
      .__editBadge {
        position: fixed; right: 14px; bottom: 14px; z-index: 999999;
        background: rgba(0,0,0,.75); color: #fff; font: 12px/1.2 Arial;
        padding: 10px 12px; border: 1px solid rgba(255,255,255,.18);
        border-radius: 12px;
      }
    `;
    document.head.appendChild(style);
  }

  // stable slot: prefer data-slot, otherwise hash src
  async function slotForImg(img) {
    const ds = (img.dataset && img.dataset.slot) ? img.dataset.slot.trim() : "";
    if (ds) return ds;

    const src = (img.currentSrc || img.src || "").split("?")[0].split("#")[0];
    const enc = new TextEncoder().encode(src);
    const hashBuf = await crypto.subtle.digest("SHA-256", enc);
    const hashArr = Array.from(new Uint8Array(hashBuf));
    const hashHex = hashArr.map(b => b.toString(16).padStart(2, "0")).join("");
    return "img_" + hashHex.slice(0, 24);
  }

  function isSkippable(img) {
    if (img.dataset && img.dataset.noedit === "1") return true;
    const src = img.currentSrc || img.src || "";
    if (!src) return true;
    if (src.startsWith("data:")) return true;
    if (src.toLowerCase().endsWith(".svg")) return true;
    if ((img.naturalWidth && img.naturalWidth < 80) || (img.naturalHeight && img.naturalHeight < 80)) return true;
    return false;
  }

  async function applyManifestToImages() {
    // This makes uploaded images show up for normal visitors too (no edit mode needed)
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
      const slot = await slotForImg(img);
      if (manifest[slot]) img.src = `/media/${encodeURIComponent(slot)}?v=${manifest[slot].updated || Date.now()}`;
    }
  }

  // hidden file picker
  const picker = document.createElement("input");
  picker.type = "file";
  picker.accept = "image/*";
  picker.style.display = "none";
  document.addEventListener("DOMContentLoaded", () => document.body.appendChild(picker));

  let currentImg = null;
  let currentSlot = null;

  async function makeEditable(img) {
    if (isSkippable(img)) return;

    img.classList.add("__editable");
    img.title = "Click to replace this image";

    img.addEventListener("click", async (e) => {
      if (!isEdit()) return;
      e.preventDefault();
      e.stopPropagation();

      currentImg = img;
      currentSlot = await slotForImg(img);

      picker.value = "";
      picker.click();
    }, true);
  }

  picker.addEventListener("change", async () => {
    const file = picker.files[0];
    if (!file || !currentImg || !currentSlot) return;

    const token = getToken();
    if (!token) {
      alert("No admin token saved. Press Ctrl+Alt+E again.");
      return;
    }

    const form = new FormData();
    form.append("file", file);

    const res = await fetch(`/admin/upload/${encodeURIComponent(currentSlot)}`, {
      method: "POST",
      headers: { "X-Admin-Token": token },
      body: form
    });

    if (!res.ok) {
      alert("Upload failed: " + await res.text());
      return;
    }

    const out = await res.json();
    currentImg.src = `/media/${encodeURIComponent(currentSlot)}?v=${Date.now()}`;
  });

  function enableEditMode() {
    addStyles();
    addBadge("EDIT MODE ON — click an image to replace (Ctrl+Alt+E to exit)");

    const imgs = Array.from(document.images);
    imgs.forEach(makeEditable);

    const mo = new MutationObserver((mutations) => {
      for (const m of mutations) {
        for (const node of m.addedNodes) {
          if (node && node.tagName === "IMG") makeEditable(node);
          if (node && node.querySelectorAll) node.querySelectorAll("img").forEach(makeEditable);
        }
      }
    });
    mo.observe(document.documentElement, { childList: true, subtree: true });
  }

  // Ctrl+Alt+E toggles edit mode WITHOUT reloading the page (so it won’t “break” it)
  document.addEventListener("keydown", async (e) => {
    if (!(e.ctrlKey && e.altKey && (e.key === "e" || e.key === "E"))) return;
    e.preventDefault();

    if (!isEdit()) {
      const token = prompt("Admin token:");
      if (!token) return;
      sessionStorage.setItem(TOKEN_KEY, token);
      sessionStorage.setItem(EDIT_FLAG, "1");
      enableEditMode();
    } else {
      sessionStorage.removeItem(EDIT_FLAG);
      // easiest clean exit: reload without edit overlays
      location.reload();
    }
  });

  // Always apply uploaded replacements (so normal view shows the updated images)
  document.addEventListener("DOMContentLoaded", () => {
    applyManifestToImages();

    if (isEdit()) {
      enableEditMode();
      addBadge("EDIT MODE ON — click an image to replace (Ctrl+Alt+E to exit)");
    }
  });
})();
