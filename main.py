import os, time, re
from pathlib import Path
from typing import Optional
from fastapi import FastAPI, File, UploadFile, Header, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

# 1. Mount all static folders (Assets, Images, CSS)
# This loop replaces 40 lines of manual mounting code
folders = ["assets", "index1_files", "menu2_files", "gallery5_files", "contact6_files", "catering3_files", "bookins4html_files", "uploads"]
for f in folders:
    if os.path.isdir(f):
        app.mount(f"/{f}", StaticFiles(directory=f), name=f)

app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(exist_ok=True)
ADMIN_TOKEN = os.getenv("ADMIN_TOKEN", "devtoken") # Set your password here or in Render Env

# 2. Page Routes - Direct mapping to your files
PAGES = {
    "/": "index1.html",
    "/menu": "menu2.html",
    "/gallery": "gallery5.html",
    "/contact": "contact6.html",
    "/catering": "catering3.html",
    "/bookings": "bookins4.html"
}

@app.get("/{path:path}")
async def serve_pages(path: str):
    # Check if the path is in our page list
    page_file = PAGES.get(f"/{path}") or PAGES.get("/") if path == "" else None
    if page_file and os.path.exists(page_file):
        return FileResponse(page_file)
    # If not a page, FastAPI will check the mounted static folders automatically
    raise HTTPException(status_code=404)

# 3. Image Swapper Logic (The "Brain")
def cache_busted(url: str):
    return f"{url}?v={int(time.time())}"

@app.get("/manifest.json")
def manifest():
    # Shows the editor which images have been replaced
    return {p.stem: cache_busted(f"/uploads/{p.name}") for p in UPLOAD_DIR.glob("*.jpg")}

@app.post("/admin/upload/{slot}")
async def upload(slot: str, file: UploadFile = File(...), x_admin_token: str = Header(None)):
    if x_admin_token != ADMIN_TOKEN: raise HTTPException(401, "Invalid Token")
    content = await file.read()
    (UPLOAD_DIR / f"{slot}.jpg").write_bytes(content)
    return {"ok": True, "url": cache_busted(f"/uploads/{slot}.jpg")}

@app.delete("/admin/delete/{slot}")
def delete(slot: str, x_admin_token: str = Header(None)):
    if x_admin_token != ADMIN_TOKEN: raise HTTPException(401)
    p = UPLOAD_DIR / f"{slot}.jpg"
    if p.exists(): p.unlink()
    return {"ok": True}