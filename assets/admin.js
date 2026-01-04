(() => {
  // Change this to your real token (better: prompt for it or store in localStorage)
  const TOKEN_KEY = "admin_token";
  let adminToken = localStorage.getItem(TOKEN_KEY) || "";

  // Toggle admin mode (Ctrl+Alt+E)
  let adminMode = false;
  window.addEventListener("keydown", (e) => {
    if (e.ctrlKey && e.altKey && e.key.toLowerCase() === "e") {
      adminMode = !adminMode;
      if (adminMode && !adminToken) {
        adminToken = prompt("Admin token:") || "";
        localStorage.setItem(TOKEN_KEY, adminToken);
      }
      renderOverlays();
    }
  });

  function renderOverlays() {
    // remove old overlays
    document.querySelectorAll(".img-admin-wrap").forEach(w => w.replaceWith(...w.childNodes));
    document.querySelectorAll(".img-admin-x").forEach(x => x.remove());

    if (!adminMode) return;

    document.querySelectorAll("img[data-slot]").forEach((img) => {
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

        const slot = img.getAttribute("data-slot");
        const choice = prompt(`Slot: ${slot}\nType:\nR = replace\nD = delete`, "R");
        if (!choice) return;

        if (choice.toLowerCase() === "d") {
          await doDelete(slot);
          // optionally hide image
          img.src = "";
          return;
        }

        // replace
        const file = await pickFile();
        if (!file) return;
        await doUpload(slot, file);

        // refresh image with cache bust
        const base = `/media/${encodeURIComponent(slot)}`;
        img.src = `${base}?v=${Date.now()}`;
      });

      wrap.appendChild(x);
    });
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
      headers: {
        "X-Admin-Token": adminToken,
      },
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
      headers: {
        "X-Admin-Token": adminToken,
      },
    });

    if (!res.ok) {
      const t = await res.text();
      alert(`Delete failed: ${res.status}\n${t}`);
      throw new Error(t);
    }
  }

  // If you want overlays immediately after toggle, nothing else needed
})();
