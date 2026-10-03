"""API route modules, mounted under /api by famtree.app."""

from fastapi import APIRouter

from famtree.api.routes import (
    admin,
    attributes,
    auth,
    export,
    health,
    people,
    relationships,
    tree,
)

api_router = APIRouter(prefix="/api")
for module in (health, auth, admin, tree, people, relationships, attributes, export):
    api_router.include_router(module.router)
