from typing import Annotated, Dict, List

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
):
    return current_user

@router.get("/has-users", response_model=Dict[str, bool])
async def check_users_exist(session: Session = Depends(get_session)):
    """Check if any users exist in the database."""
    user = session.exec(select(User)).first()
    return {"exists": user is not None}

@router.post("/setup", response_model=UserRead)
async def setup_first_admin(
    user: UserCreate,
    session: Session = Depends(get_session),
):
    """
    Create the first admin user. 
    Only allowed if the database has no users.
    """
    existing_user = session.exec(select(User)).first()
    if existing_user:
        raise HTTPException(status_code=403, detail="Setup already completed. Users exist.")

    # Validate email uniqueness strictly (redundant with DB constraint but good for error msg)
    if session.exec(select(User).where(User.email == user.email)).first():
         raise HTTPException(status_code=400, detail="Email already registered")

    # Force role to admin
    user_data = user.model_dump()
    user_data["role"] = "admin"
    user_data["hashed_password"] = get_password_hash(user_data.pop("password"))
    
    db_user = User.model_validate(user_data)
    session.add(db_user)
    session.commit()
    session.refresh(db_user)
    return db_user

@router.get("/", response_model=List[UserRead])
async def read_users(
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_admin_user),
    offset: int = 0,
    limit: int = Query(default=100, le=100),
):
    users = session.exec(select(User).offset(offset).limit(limit)).all()
    return users

@router.post("/", response_model=UserRead)
async def create_user(
    user: UserCreate,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_admin_user),
):
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
):
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
):
    db_user = session.get(User, user_id)
    if not db_user:
        raise HTTPException(status_code=404, detail="User not found")
    return db_user


@router.delete("/{user_id}")
async def delete_user(
    user_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_admin_user),
):
    db_user = session.get(User, user_id)
    if not db_user:
        raise HTTPException(status_code=404, detail="User not found")
    session.delete(db_user)
    session.commit()
    return {"ok": True}

