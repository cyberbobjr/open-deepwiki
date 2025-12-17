from abc import ABC, abstractmethod
from typing import List, Optional
import requests
from pydantic import BaseModel

class ProjectInfo(BaseModel):
    name: str
    url: str  # Clone URL or Web URL
    description: Optional[str] = None
    default_branch: str = "main"

class RepositoryClient(ABC):
    @abstractmethod
    def list_projects(self) -> List[ProjectInfo]:
        """List available projects/repositories."""
        pass

    @abstractmethod
    def list_branches(self, project_name: str) -> List[str]:
        """List branches for a given project."""
        pass
