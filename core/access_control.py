from fastapi import HTTPException, status
from sqlmodel import Session, select

from core.models.user import Project, User


def validate_project_access(session: Session, user: User, project_name: str):
    """
    Validates if the user has access to the given project.
    
    Rules:
    1. Admin has access to everything.
    2. If check_project_access is strict (default):
       - If Project defined in DB: User must belong to the Project's Group.
       - If Project NOT in DB: It is considered 'Public' (or we can fallback to Admin-only).
         Current decision: Public (accessible to all) to support legacy/unclaimed projects.
    """
    if user.role == "admin":
        return

    # Check if project exists in DB
    db_project = session.exec(select(Project).where(Project.name == project_name)).first()
    
    if not db_project:
        # Project is not claimed by any group.
        # Allow access (Public)
        return

    # Project is claimed. Check user membership.
    # Ensure user.groups is loaded.
    # We should query the link table or assume relationships are loaded.
    # Safest is to query the link.
    
    for group in user.groups:
        if group.id == db_project.group_id:
            return

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail=f"You do not have access to project '{project_name}'"
    )
