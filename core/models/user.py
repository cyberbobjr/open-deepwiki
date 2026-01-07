from datetime import datetime, timezone

from sqlmodel import Field, Relationship, SQLModel


class UserGroupLink(SQLModel, table=True):
    """Link table for many-to-many relationship between users and groups."""
    
    user_id: int | None = Field(default=None, foreign_key="user.id", primary_key=True)
    group_id: int | None = Field(default=None, foreign_key="group.id", primary_key=True)

class User(SQLModel, table=True):
    """User model representing authenticated users in the system.
    
    Attributes:
        id: Primary key.
        email: Unique email address used for authentication.
        firstname: User's first name.
        lastname: User's last name.
        hashed_password: Bcrypt hashed password.
        role: User role (user, maintainer, or admin).
        created_at: Timestamp of user creation.
        updated_at: Timestamp of last update.
        groups: Groups this user belongs to.
    """
    
    model_config = {"arbitrary_types_allowed": True}
    id: int | None = Field(default=None, primary_key=True)
    email: str = Field(index=True, unique=True)
    firstname: str
    lastname: str
    hashed_password: str
    role: str = Field(default="user")  # user, maintainer, admin
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    groups: list["Group"] = Relationship(back_populates="users", link_model=UserGroupLink)

class Group(SQLModel, table=True):
    """Group model for organizing users and managing project access.
    
    Attributes:
        id: Primary key.
        name: Unique group name.
        users: Users who are members of this group.
        projects: Projects assigned to this group.
    """
    
    model_config = {"arbitrary_types_allowed": True}
    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(unique=True, index=True)

    users: list[User] = Relationship(back_populates="groups", link_model=UserGroupLink)
    projects: list["Project"] = Relationship(back_populates="group")

class Project(SQLModel, table=True):
    """Project model representing project-to-group assignments.
    
    Attributes:
        id: Primary key.
        name: Unique project name.
        group_id: ID of the group this project is assigned to.
        group: The group this project belongs to.
    """
    
    model_config = {"arbitrary_types_allowed": True}
    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(unique=True, index=True)
    group_id: int | None = Field(default=None, foreign_key="group.id")

    group: Group | None = Relationship(back_populates="projects")

# --- Schemas ---

class UserBase(SQLModel):
    """Base schema for user data."""
    
    email: str = Field(index=True, unique=True)
    firstname: str
    lastname: str
    role: str = Field(default="user")

class UserCreate(UserBase):
    """Schema for creating a new user."""
    
    password: str

class UserUpdate(SQLModel):
    """Schema for updating an existing user."""
    
    email: str | None = None
    firstname: str | None = None
    lastname: str | None = None
    password: str | None = None
    role: str | None = None

class UserRead(UserBase):
    """Schema for reading user data."""
    
    id: int
    created_at: datetime
    updated_at: datetime

class ProjectBase(SQLModel):
    """Base schema for project data."""
    
    name: str

class ProjectCreate(ProjectBase):
    """Schema for creating a new project."""
    
    pass

class ProjectRead(ProjectBase):
    """Schema for reading project data."""
    
    id: int
    group_id: int | None

class GroupBase(SQLModel):
    """Base schema for group data."""
    
    name: str

class GroupCreate(GroupBase):
    """Schema for creating a new group."""
    
    pass

class GroupRead(GroupBase):
    """Schema for reading group data with relationships."""
    
    id: int
    name: str
    users: list[UserRead] = []
    projects: list[ProjectRead] = []

class GroupUpdate(SQLModel):
    """Schema for updating an existing group."""
    
    name: str | None = None
    user_ids: list[int] | None = None  # For updating members
    project_names: list[str] | None = None  # For updating projects
