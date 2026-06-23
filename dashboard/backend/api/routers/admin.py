"""Admin/debug routes (Phase 3D4A).

Moved verbatim from ``dashboard/backend/app.py``. External paths
``/admin/clear`` and ``/admin/runs/{run_id}`` and their behavior are unchanged;
registered directly on the app.
"""

from fastapi import APIRouter, HTTPException, Request

from dashboard.backend.database import db

router = APIRouter()


@router.delete("/admin/clear")
async def admin_clear_all():
    """⚠️ Clear all data. Use with caution!"""
    db.clear_all()
    return {"status": "cleared"}


@router.delete("/admin/runs/{run_id}")
async def admin_delete_run(run_id: str, request: Request):
    """⚠️ Delete a specific run (must be owned by session)."""
    session_id = request.state.session_id
    
    # Verify ownership before deleting
    run = db.get_run_with_session(run_id, session_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found or not yours")
    
    db.delete_run(run_id)
    return {"status": "deleted", "run_id": run_id}
