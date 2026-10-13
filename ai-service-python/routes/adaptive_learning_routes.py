"""Internal Python endpoints; browsers access these through the Java /api proxy."""
try:
    from fastapi import APIRouter
    from fastapi.responses import JSONResponse
except ModuleNotFoundError:  # pragma: no cover
    from tests.fastapi_stubs import APIRouter, JSONResponse

from schemas.adaptive_learning import AdaptiveLearningActionRequest, AdaptiveLearningStartRequest
from services.adaptive_learning_service import LearningConflict, start_activity, transition_activity

adaptive_learning_router = APIRouter()


@adaptive_learning_router.post("/adaptive-learning/start")
async def start_adaptive_learning(request: AdaptiveLearningStartRequest):
    try:
        return JSONResponse(start_activity(request))
    except ValueError as error:
        return JSONResponse({"status": "error", "message": str(error)}, status_code=422)
    except Exception:
        return JSONResponse({"status": "error", "message": "learning_provider_failed"}, status_code=503)


@adaptive_learning_router.post("/adaptive-learning/action")
async def adaptive_learning_action(request: AdaptiveLearningActionRequest):
    try:
        return JSONResponse(transition_activity(request))
    except LearningConflict as error:
        return JSONResponse({"status": "error", "message": str(error)}, status_code=409)
    except ValueError as error:
        return JSONResponse({"status": "error", "message": str(error)}, status_code=422)
    except Exception:
        return JSONResponse({"status": "error", "message": "learning_provider_failed"}, status_code=503)
