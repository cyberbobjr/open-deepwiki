from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session, select

from core.database import get_session
from core.models.user import (Group, GroupCreate, GroupRead, GroupUpdate,
                              Project, User)
from core.security import get_current_admin_user

router = APIRouter()

@router.get("/", response_model=list[GroupRead])
async def read_groups(
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_admin_user),
    offset: int = 0,
    limit: int = Query(default=100, le=100),
) -> list[Group]:
    """List all groups (admin only).
    
    Args:
        session: Database session.
        current_user: The current admin user.
        offset: Number of records to skip.
        limit: Maximum number of records to return.
        
    Returns:
        List of groups with their users and projects.
    """
    groups = session.exec(select(Group).offset(offset).limit(limit)).all()
    # SQLModel doesn't auto-fetch relationships for some reason in response unless accessed?
    # Actually Pydantic v2 traversal should handle it if relationship is loaded.
    # To be safe we might need to eager load or let lazy loading work if session is open.
    return groups

@router.get("/{group_id}", response_model=GroupRead)
async def read_group(
    group_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_admin_user),
) -> Group:
    """Get a specific group by ID (admin only).
    
    Args:
        group_id: ID of the group to retrieve.
        session: Database session.
        current_user: The current admin user.
        
    Returns:
        The requested group with its users and projects.
        
    Raises:
        HTTPException: If the group is not found.
    """
    db_group = session.get(Group, group_id)
    if not db_group:
        raise HTTPException(status_code=404, detail="Group not found")
    return db_group


@router.post("/", response_model=GroupRead)
async def create_group(
    group: GroupCreate,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_admin_user),
) -> Group:
    """Create a new group (admin only).
    
    Args:
        group: Group creation data.
        session: Database session.
        current_user: The current admin user.
        
    Returns:
        The created group.
        
    Raises:
        HTTPException: If a group with the name already exists.
    """
    if session.exec(select(Group).where(Group.name == group.name)).first():
        raise HTTPException(status_code=400, detail="Group already exists")
    
    db_group = Group.model_validate(group)
    session.add(db_group)
    session.commit()
    session.refresh(db_group)
    return db_group

@router.put("/{group_id}", response_model=GroupRead)
async def update_group(
    group_id: int,
    group_update: GroupUpdate,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_admin_user),
) -> Group:
    """Update an existing group (admin only).
    
    Args:
        group_id: ID of the group to update.
        group_update: Group update data including optional name, user_ids, and project_names.
        session: Database session.
        current_user: The current admin user.
        
    Returns:
        The updated group.
        
    Raises:
        HTTPException: If the group is not found or a project is already assigned to another group.
    """
    db_group = session.get(Group, group_id)
    if not db_group:
        raise HTTPException(status_code=404, detail="Group not found")
    
    if group_update.name:
        db_group.name = group_update.name

    if group_update.user_ids is not None:
        # Clear existing links and add new ones
        # This is a full update of users.
        
        # Remove old links
        for existing_user in db_group.users:
            db_group.users.remove(existing_user)
        
        # Add new
        for uid in group_update.user_ids:
            user = session.get(User, uid)
            if not user:
                raise HTTPException(status_code=404, detail=f"User with id {uid} not found")
            db_group.users.append(user)

    if group_update.project_names is not None:
        # Update projects
        # Remove projects from group (set group_id to null or delete?)
        # Projects belong to a group. If we remove a project from a group, does it delete the project record?
        # The project record IS the assignment.
        
        # We need to handle this carefully.
        # "Projects" in SQL are basically claims.
        # If we "remove" a project, we probably delete the Project record in SQL.
        
        # Clear current projects
        for p in db_group.projects:
            session.delete(p)
            
        # Add new projects
        for pname in group_update.project_names:
            # Check if project claimed by another group?
            existing_p = session.exec(select(Project).where(Project.name == pname)).first()
            if existing_p and existing_p.group_id != group_id:
                raise HTTPException(
                    status_code=400,
                    detail=f"Project {pname} is already assigned to another group",
                )
            
            if existing_p:
                existing_p.group_id = group_id
                session.add(existing_p)
            else:
                new_p = Project(name=pname, group_id=group_id)
                session.add(new_p)
    
    session.add(db_group)
    session.commit()
    session.refresh(db_group)
    return db_group

@router.delete("/{group_id}")
async def delete_group(
    group_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_admin_user),
) -> dict[str, bool]:
    """Delete a group (admin only).
    
    Args:
        group_id: ID of the group to delete.
        session: Database session.
        current_user: The current admin user.
        
    Returns:
        Success confirmation.
        
    Raises:
        HTTPException: If the group is not found.
    """
    db_group = session.get(Group, group_id)
    if not db_group:
        raise HTTPException(status_code=404, detail="Group not found")
    session.delete(db_group)
    session.commit()
    return {"ok": True}
