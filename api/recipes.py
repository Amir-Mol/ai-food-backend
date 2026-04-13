"""
recipes.py – legacy endpoint file.

The /generate-recommendations endpoint that was previously here has been
removed.  Recommendation generation is now handled asynchronously by
background tasks in tasks/recommendation_generator.py, triggered after
onboarding completion and after every 5th feedback submission via
api/recommendations.py.

The router is kept (empty) so main.py does not need to change.
"""
from fastapi import APIRouter

router = APIRouter()

