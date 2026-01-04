(() => {
  const TOKEN_KEY = "admin_token";
  let adminToken = localStorage.getItem(TOKEN_KEY) || "";
  let adminMode = false;

  // --- tiny badge so you can SEE it toggled ---
  function setBadge(on) {
    let b = document.querySelector(".__adminBadge");
    if (!b) {
      b = document.createElement("div");
      b.className = "__adminBadge";
      Object.assign(b.style, {
        position: "fixed",
        right: "14px",
        bottom: "14px",
        zIndex: 999999,
        background: "rgba(0,0,0,.75)",
        color: "#fff",
        font: "12px/1.2 Arial",
        padding: "10px 12px",
        border: "1px solid rgba(255,255,255,.18)",
        borderRadius: "12px",
      });
      document.body.appendChild(b);
    }
    b.textContent = on ? "ADMIN MODE ON — click ✕ to delete/replace" : "";
    b.style.display = on ? "block" : "none";
  }

  // Fallback hash if crypto.subtle isn’t available
  function simpleHash(str) {
    let h = 2166136261;
    for (let i = 0; i < str.length; i++) {
      h ^= str.charCodeAt(i);
      h = Math.imul(h, 16777619);
    }
    return (h >>> 0).toString(16).padStart(8, "0");
  }

  async function slotForImg(img) {
    const ds = (img.dataset && img.dataset.slot) ? img.dataset.slot.trim() : "";
    if (ds) return ds;

    const src = (img.currentSrc || img.src || "").split("?")[0].split("#")[0];
    if (!src) return "";

    // Prefer crypto hash (stable + low collision)
    try {
      if (crypto?.subtle?.digest) {
        const enc = new TextEncoder().encode(src);
        const buf = await crypto.subtle.digest("SHA-256", enc);
        const hex = Array.from(new Uint8Array(buf))
          .map(b => b.toString(16).padStart(2, "0"))
          .join("");
        return "img_" + hex.slice(0, 24);
      }
    } catch {
      // fall through to simple hash
    }

    // Fallback: still stable per URL
    return ("img_" + simpleHash(src).repeat(4)).slice(0, 28);
  }

  function isSkippable(img) {
    const src = img.currentSrc || img.src || "";
    if (!src) return true;
    if (src.startsWith("data:")) return true;
    if (src.toLowerCase().endsWith(".svg")) return true;
    return false;
  }

  // Toggle admin mode (Ctrl+Alt+E) — capture=true so other scripts can’t steal it
  window.addEventListener("keydown", (e) => {
    const isHotkey =
      e.ctrlKey &&
      e.altKey &&
      (e.code === "KeyE" || (typeof e.key === "string" && e.key.toLowerCase() === "e"));

    if (!isHotkey) return;

    e.preventDefault();

    adminMode = !adminMode;

    if (adminMode && !adminToken) {
      adminToken = prompt("Admin token:") || "";
      localStorage.setItem(TOKEN_KEY, adminToken);
    }

    void renderOverlays();
  }, true);

  let mo = null;

  async function renderOverlays() {
    // remove old overlays
    document.querySelectorAll(".img-admin-wrap").forEach(w => w.replaceWith(...w.childNodes));
    document.querySelectorAll(".img-admin-x").forEach(x => x.remove());

    setBadge(adminMode);

    if (!adminMode) {
      if (mo) mo.disconnect();
      mo = null;
      return;
    }

    // Add overlays to ALL images (not only img[data-slot])
    const imgs = Array.from(document.images);
    for (const img of imgs) {
      if (isSkippable(img)) continue;

      const slot = await slotForImg(img);
      if (!slot) continue;

      // Ensure it has a slot so you can inspect it in devtools if needed
      if (!img.dataset.slot) img.dataset.slot = slot;

      // wrap image so we can position overlay
      const wrap = document.createElement("span");
      wrap.className = "img-admin-wrap";
      wrap.style.position = "relative";
      wrap.style.display = "inline-block";

      img.parentNode.insertBefore(wrap, img);
      wrap.appendChild(img);

      // X button
      const x = document.createElement("button");
      x.className = "img-admin-x";
      x.textContent = "✕";
      x.title = "Delete / Replace";
      Object.assign(x.style, {
        position: "absolute",
        top: "8px",
        right: "8px",
        zIndex: 9999,
        border: "none",
        borderRadius: "10px",
        padding: "6px 10px",
        cursor: "pointer",
        fontSize: "14px",
        background: "rgba(0,0,0,0.65)",
        color: "#fff",
      });

      x.addEventListener("click", async (ev) => {
        ev.preventDefault();
        ev.stopPropagation();

        const choice = prompt(`Slot: ${slot}\nType:\nR = replace\nD = delete`, "R");
        if (!choice) return;

        if (choice.toLowerCase() === "d") {
          await doDelete(slot);
          img.src = "";
          return;
        }

        const file = await pickFile();
        if (!file) return;

        await doUpload(slot, file);
        img.src = `/media/${encodeURIComponent(slot)}?v=${Date.now()}`;
      });

      wrap.appendChild(x);
    }

    // Watch for lazy-loaded / injected images while adminMode is on
    if (!mo) {
      mo = new MutationObserver(() => {
        // Re-render (cheap enough for your use-case)
        void renderOverlays();
      });
      mo.observe(document.documentElement, { childList: true, subtree: true });
    }
  }

  function pickFile() {
    return new Promise((resolve) => {
      const input = document.createElement("input");
      input.type = "file";
      input.accept = "image/*";
      input.onchange = () => resolve(input.files?.[0] || null);
      input.click();
    });
  }

  async function doUpload(slot, file) {
    const fd = new FormData();
    fd.append("file", file);

    const res = await fetch(`/admin/upload/${encodeURIComponent(slot)}`, {
      method: "POST",
      headers: { "X-Admin-Token": adminToken },
      body: fd,
    });

    if (!res.ok) {
      const t = await res.text();
      alert(`Upload failed: ${res.status}\n${t}`);
      throw new Error(t);
    }
  }

  async function doDelete(slot) {
    const res = await fetch(`/admin/delete/${encodeURIComponent(slot)}`, {
      method: "DELETE",
      headers: { "X-Admin-Token": adminToken },
    });

    if (!res.ok) {
      const t = await res.text();
      alert(`Delete failed: ${res.status}\n${t}`);
      throw new Error(t);
    }
  }

  // In case you toggle quickly before body exists
  document.addEventListener("DOMContentLoaded", () => setBadge(false));
})();
