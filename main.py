import os, time, re
from pathlib import Path

from fastapi import FastAPI, File, UploadFile, Header, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

# --- settings ---
UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(exist_ok=True)
ADMIN_TOKEN = os.getenv("ADMIN_TOKEN", "devtoken")
SLOT_RE = re.compile(r"^[a-zA-Z0-9_-]{1,80}$")

def cache_busted(url: str) -> str:
    return f"{url}?v={int(time.time())}"

def check_slot(slot: str):
    if not SLOT_RE.match(slot):
        raise HTTPException(400, "Invalid slot")

# --- static mounts ---
folders = [
    "assets",
    "home1_files",          # homepage uses this (your console 404s are from this)
    "index1_files",
    "menu2_files",
    "gallery5_files",
    "contact6_files",
    "catering3_files",
    "bookins4html_files",
    "uploads",
]
for f in folders:
    if os.path.isdir(f):
        app.mount(f"/{f}", StaticFiles(directory=f), name=f)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- swapper API (MUST be above catch-all) ---
@app.get("/manifest.json")
def manifest():
    return {p.stem: cache_busted(f"/uploads/{p.name}") for p in UPLOAD_DIR.glob("*.jpg")}

@app.post("/admin/upload/{slot}")
async def upload(slot: str, file: UploadFile = File(...), x_admin_token: str = Header(None)):
    check_slot(slot)
    if x_admin_token != ADMIN_TOKEN:
        raise HTTPException(401, "Invalid Token")
    content = await file.read()
    (UPLOAD_DIR / f"{slot}.jpg").write_bytes(content)
    return {"ok": True, "url": cache_busted(f"/uploads/{slot}.jpg")}

@app.delete("/admin/delete/{slot}")
def delete(slot: str, x_admin_token: str = Header(None)):
    check_slot(slot)
    if x_admin_token != ADMIN_TOKEN:
        raise HTTPException(401, "Invalid Token")
    p = UPLOAD_DIR / f"{slot}.jpg"
    if p.exists():
        p.unlink()
    return {"ok": True}

# --- pages ---
PAGES = {
    "/": "index1.html",
    "/menu": "menu2.html",
    "/gallery": "gallery5.html",
    "/contact": "contact6.html",
    "/catering": "catering3.html",
    "/bookings": "bookins4.html",
}

@app.get("/{path:path}", include_in_schema=False)
def serve_pages(path: str):
    if path == "":
        return FileResponse(PAGES["/"])
    page_file = PAGES.get(f"/{path}")
    if page_file and os.path.exists(page_file):
        return FileResponse(page_file)
    raise HTTPException(404)
