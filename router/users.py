from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session, select

from core.database import get_session
from core.models.user import User, UserCreate, UserRead, UserUpdate
from core.security import (get_current_admin_user, get_current_user,
                           get_password_hash)

router = APIRouter()

@router.get("/me", response_model=UserRead)
async def read_users_me(
    current_user: Annotated[User, Depends(get_current_user)],
) -> User:
    """Get the current authenticated user's information.
    
    Args:
        current_user: The currently authenticated user.
        
    Returns:
        The user's information.
    """
    return current_user

@router.get("/has-users", response_model=dict[str, bool])
async def check_users_exist(session: Session = Depends(get_session)) -> dict[str, bool]:
    """Check if any users exist in the database.
    
    Args:
        session: Database session.
        
    Returns:
        Dictionary with 'exists' key indicating whether users exist.
    """
    user = session.exec(select(User)).first()
    return {"exists": user is not None}

@router.post("/setup", response_model=UserRead)
async def setup_first_admin(
    user: UserCreate,
    session: Session = Depends(get_session),
) -> User:
    """Create the first admin user during initial setup.
    
    This endpoint is only available when no users exist in the database.
    The created user is automatically assigned the admin role.
    
    Args:
        user: User creation data including email, name, and password.
        session: Database session.
        
    Returns:
        The created admin user.
        
    Raises:
        HTTPException: If users already exist (setup completed).
    """
    existing_user = session.exec(select(User)).first()
    if existing_user:
        raise HTTPException(status_code=403, detail="Setup already completed. Users exist.")

    # Force role to admin
    user_data = user.model_dump()
    user_data["role"] = "admin"
    user_data["hashed_password"] = get_password_hash(user_data.pop("password"))
    
    db_user = User.model_validate(user_data)
    session.add(db_user)
    session.commit()
    session.refresh(db_user)
    return db_user

@router.get("/", response_model=list[UserRead])
async def read_users(
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_admin_user),
    offset: int = 0,
    limit: int = Query(default=100, le=100),
) -> list[User]:
    """List all users (admin only).
    
    Args:
        session: Database session.
        current_user: The current admin user.
        offset: Number of records to skip.
        limit: Maximum number of records to return.
        
    Returns:
        List of users.
    """
    users = session.exec(select(User).offset(offset).limit(limit)).all()
    return users

@router.post("/", response_model=UserRead)
async def create_user(
    user: UserCreate,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_admin_user),
) -> User:
    """Create a new user (admin only).
    
    Args:
        user: User creation data.
        session: Database session.
        current_user: The current admin user.
        
    Returns:
        The created user.
        
    Raises:
        HTTPException: If a user with the email already exists.
    """
    if session.exec(select(User).where(User.email == user.email)).first():
        raise HTTPException(status_code=400, detail="Email already registered")
    
    db_user = User.model_validate(user, update={"hashed_password": get_password_hash(user.password)})
    session.add(db_user)
    session.commit()
    session.refresh(db_user)
    return db_user

@router.put("/{user_id}", response_model=UserRead)
async def update_user(
    user_id: int,
    user: UserUpdate,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_admin_user),
) -> User:
    """Update an existing user (admin only).
    
    Args:
        user_id: ID of the user to update.
        user: User update data.
        session: Database session.
        current_user: The current admin user.
        
    Returns:
        The updated user.
        
    Raises:
        HTTPException: If the user is not found.
    """
    db_user = session.get(User, user_id)
    if not db_user:
        raise HTTPException(status_code=404, detail="User not found")
    
    user_data = user.model_dump(exclude_unset=True)
    if user.password:
        user_data["hashed_password"] = get_password_hash(user.password)
        del user_data["password"]
        
    db_user.sqlmodel_update(user_data)
    session.add(db_user)
    session.commit()
    session.refresh(db_user)
    return db_user


@router.get("/{user_id}", response_model=UserRead)
async def read_user(
    user_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_admin_user),
) -> User:
    """Get a specific user by ID (admin only).
    
    Args:
        user_id: ID of the user to retrieve.
        session: Database session.
        current_user: The current admin user.
        
    Returns:
        The requested user.
        
    Raises:
        HTTPException: If the user is not found.
    """
    db_user = session.get(User, user_id)
    if not db_user:
        raise HTTPException(status_code=404, detail="User not found")
    return db_user


@router.delete("/{user_id}")
async def delete_user(
    user_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_admin_user),
) -> dict[str, bool]:
    """Delete a user (admin only).
    
    Args:
        user_id: ID of the user to delete.
        session: Database session.
        current_user: The current admin user.
        
    Returns:
        Success confirmation.
        
    Raises:
        HTTPException: If the user is not found.
    """
    db_user = session.get(User, user_id)
    if not db_user:
        raise HTTPException(status_code=404, detail="User not found")
    session.delete(db_user)
    session.commit()
    return {"ok": True}

