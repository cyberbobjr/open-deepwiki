from datetime import datetime
from typing import List, Optional

from sqlmodel import Field, Relationship, SQLModel


class UserGroupLink(SQLModel, table=True):
    user_id: Optional[int] = Field(default=None, foreign_key="user.id", primary_key=True)
    group_id: Optional[int] = Field(default=None, foreign_key="group.id", primary_key=True)

class User(SQLModel, table=True):
    model_config = {"arbitrary_types_allowed": True}
    id: Optional[int] = Field(default=None, primary_key=True)
    email: str = Field(index=True, unique=True)
    firstname: str
    lastname: str
    hashed_password: str
    role: str = Field(default="user")  # user, maintainer, admin
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    groups: List["Group"] = Relationship(back_populates="users", link_model=UserGroupLink)

class Group(SQLModel, table=True):
    model_config = {"arbitrary_types_allowed": True}
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(unique=True, index=True)

    users: List[User] = Relationship(back_populates="groups", link_model=UserGroupLink)
    projects: List["Project"] = Relationship(back_populates="group")

class Project(SQLModel, table=True):
    model_config = {"arbitrary_types_allowed": True}
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(unique=True, index=True)
    group_id: Optional[int] = Field(default=None, foreign_key="group.id")

    group: Optional[Group] = Relationship(back_populates="projects")

# --- Schemas ---

class UserBase(SQLModel):
    email: str = Field(index=True, unique=True)
    firstname: str
    lastname: str
    role: str = Field(default="user")

class UserCreate(UserBase):
    password: str

class UserUpdate(SQLModel):
    email: Optional[str] = None
    firstname: Optional[str] = None
    lastname: Optional[str] = None
    password: Optional[str] = None
    role: Optional[str] = None

class UserRead(UserBase):
    id: int
    created_at: datetime
    updated_at: datetime

class ProjectBase(SQLModel):
    name: str

class ProjectCreate(ProjectBase):
    pass

class ProjectRead(ProjectBase):
    id: int
    group_id: Optional[int]

class GroupBase(SQLModel):
    name: str

class GroupCreate(GroupBase):
    pass

class GroupRead(GroupBase):
    id: int
    name: str
    users: List[UserRead] = []
    projects: List[ProjectRead] = []

class GroupUpdate(SQLModel):
    name: Optional[str] = None
    user_ids: Optional[List[int]] = None # For updating members
    project_names: Optional[List[str]] = None # For updating projects
