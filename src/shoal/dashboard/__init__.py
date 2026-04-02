"""Shoal web dashboard — FastAPI sub-application factory.

Mount at ``/ui`` on the main Shoal API server::

    from shoal.dashboard import create_dashboard_app
    app.mount("/ui", create_dashboard_app())
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

_STATIC_DIR = Path(__file__).parent / "static"
_TEMPLATES_DIR = Path(__file__).parent / "templates"


def create_dashboard_app() -> FastAPI:
    """Create and configure the dashboard sub-application.

    Returns:
        A FastAPI app with Jinja2 templates, static files, and all
        dashboard routes registered.  Mount at ``/ui``.
    """
    from shoal.dashboard.routes import init_templates, router

    dashboard = FastAPI(
        title="Shoal Dashboard",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )

    templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))
    init_templates(templates)

    dashboard.include_router(router)
    dashboard.mount(
        "/static",
        StaticFiles(directory=str(_STATIC_DIR)),
        name="dashboard-static",
    )

    return dashboard
