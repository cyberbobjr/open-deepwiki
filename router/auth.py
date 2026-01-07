from datetime import timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel
from sqlmodel import Session, select

from core.database import get_session
from core.models.user import User
from core.security import (ACCESS_TOKEN_EXPIRE_MINUTES, create_access_token,
                           verify_password)

router = APIRouter()


class TokenResponse(BaseModel):
    """Response model for authentication token endpoint.
    
    Attributes:
        access_token: JWT access token.
        token_type: Token type (always "bearer").
        role: User's role.
        name: User's full name.
    """
    
    access_token: str
    token_type: str
    role: str
    name: str

@router.post("/token", response_model=TokenResponse)
async def login_for_access_token(
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    session: Session = Depends(get_session)
) -> TokenResponse:
    """Authenticate a user and return an access token.
    
    Args:
        form_data: OAuth2 form data containing username (email) and password.
        session: Database session.
        
    Returns:
        TokenResponse containing the JWT access token and user information.
        
    Raises:
        HTTPException: If authentication fails due to incorrect credentials.
    """
    # form_data.username is the email
    statement = select(User).where(User.email == form_data.username)
    user = session.exec(statement).first()
    
    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user.email, "role": user.role}, expires_delta=access_token_expires
    )
    
    return TokenResponse(
        access_token=access_token, 
        token_type="bearer", 
        role=user.role, 
        name=f"{user.firstname} {user.lastname}"
    )
