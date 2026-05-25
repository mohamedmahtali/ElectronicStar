from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from apps.api.src.routers import ops, products, search
from apps.api.src.search.es_client import close_es_client


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    await close_es_client()


app = FastAPI(
    title="Electronic-Star Search API",
    version="1.0.0",
    description="API de comparaison de prix — catalogue canonique et offres marchands",
    lifespan=lifespan,
)

app.include_router(search.router)
app.include_router(products.router)
app.include_router(ops.router)

WEB_STATIC_DIR = Path(__file__).resolve().parents[1] / "web" / "static"
if WEB_STATIC_DIR.exists():

    @app.get("/ui/demo", include_in_schema=False)
    async def ui_demo():
        return FileResponse(WEB_STATIC_DIR / "index.html")

    @app.get("/ui/ops", include_in_schema=False)
    async def ui_ops():
        return FileResponse(WEB_STATIC_DIR / "index.html")

    @app.get("/ui/product/{product_id}", include_in_schema=False)
    async def ui_product_detail(product_id: str):
        return FileResponse(WEB_STATIC_DIR / "index.html")

    app.mount("/ui", StaticFiles(directory=WEB_STATIC_DIR, html=True), name="ui")


@app.get("/", include_in_schema=False)
async def root():
    if WEB_STATIC_DIR.exists():
        return RedirectResponse(url="/ui/")
    return {"name": "ElectronicStar API", "docs": "/docs"}


@app.get("/healthz", tags=["ops"])
async def healthz():
    return {"status": "ok"}


@app.get("/livez", tags=["ops"])
async def livez():
    return {"status": "ok"}
