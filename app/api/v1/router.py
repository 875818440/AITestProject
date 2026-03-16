from fastapi import APIRouter

from app.api.v1.endpoints import auth, events, risk, alerts, ml

api_router = APIRouter()

api_router.include_router(auth.router, prefix="/auth", tags=["Auth"])
api_router.include_router(events.router, prefix="/events", tags=["Events"])
api_router.include_router(risk.router, prefix="/risk", tags=["Risk"])
api_router.include_router(alerts.router, prefix="/alerts", tags=["Alerts"])
api_router.include_router(ml.router, prefix="/ml", tags=["ML"])
