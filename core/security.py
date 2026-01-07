from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlmodel import Session, select

from core.database import get_session
from core.models.user import User

# Load secret key from environment variable
# SECURITY: In production, set OPEN_DEEPWIKI_SECRET_KEY environment variable
import os
SECRET_KEY = os.getenv("OPEN_DEEPWIKI_SECRET_KEY", "CHANGE_ME_IN_PRODUCTION_SECRET_KEY")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30 * 24 * 60  # 30 days

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/token")

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plain password against a hashed password.
    
    Args:
        plain_password: The plain text password to verify.
        hashed_password: The hashed password to compare against.
        
    Returns:
        True if the password matches, False otherwise.
    """
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password: str) -> str:
    """Generate a bcrypt hash of the given password.
    
    Args:
        password: The plain text password to hash.
        
    Returns:
        The hashed password.
    """
    return pwd_context.hash(password)

def create_access_token(data: dict, expires_delta: timedelta | None = None) -> str:
    """Create a JWT access token.
    
    Args:
        data: Dictionary of claims to encode in the token.
        expires_delta: Optional expiration time delta. Defaults to 15 minutes.
        
    Returns:
        The encoded JWT token string.
    """
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

async def get_current_user(token: Annotated[str, Depends(oauth2_scheme)], session: Session = Depends(get_session)) -> User:
    """Extract and validate the current user from a JWT token.
    
    Args:
        token: JWT access token from the Authorization header.
        session: Database session.
        
    Returns:
        The authenticated User object.
        
    Raises:
        HTTPException: If the token is invalid or the user is not found.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email: str = payload.get("sub")
        if email is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception
    
    statement = select(User).where(User.email == email)
    user = session.exec(statement).first()
    if user is None:
        raise credentials_exception
    return user

async def get_current_active_user(current_user: Annotated[User, Depends(get_current_user)]) -> User:
    """Get the current active user.
    
    Args:
        current_user: The current authenticated user.
        
    Returns:
        The active user.
    """
    # We can add is_active check here later
    return current_user

async def get_current_maintainer(current_user: Annotated[User, Depends(get_current_user)]) -> User:
    """Get the current user if they are a maintainer or admin.
    
    Args:
        current_user: The current authenticated user.
        
    Returns:
        The user if they have maintainer or admin role.
        
    Raises:
        HTTPException: If the user doesn't have sufficient privileges.
    """
    if current_user.role not in ["admin", "maintainer"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="The user doesn't have enough privileges",
        )
    return current_user

async def get_current_admin_user(current_user: Annotated[User, Depends(get_current_user)]) -> User:
    """Get the current user if they are an admin.
    
    Args:
        current_user: The current authenticated user.
        
    Returns:
        The user if they have admin role.
        
    Raises:
        HTTPException: If the user doesn't have admin privileges.
    """
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="The user doesn't have enough privileges",
        )
    return current_user
