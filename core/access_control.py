from fastapi import HTTPException, status
from sqlmodel import Session, select

from core.models.user import Project, User


def validate_project_access(session: Session, user: User, project_name: str) -> None:
    """Validate if the user has access to the given project.
    
    Access rules:
    1. Admin users have access to all projects.
    2. If a project is defined in the database:
       - User must belong to the project's group.
    3. If a project is not in the database:
       - Considered 'public' and accessible to all authenticated users.
       
    Args:
        session: Database session.
        user: The user requesting access.
        project_name: Name of the project to access.
        
    Raises:
        HTTPException: If the user doesn't have access to the project.
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
