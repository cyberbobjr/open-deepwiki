from typing import Optional
from .base import RepositoryClient
from .github_client import GitHubClient
from .gitlab_client import GitLabClient
from config import RepositoryConfig

def get_repository_client(config: RepositoryConfig) -> Optional[RepositoryClient]:
    if config.type.lower() == "github":
        return GitHubClient(token=config.token, base_url=config.url, namespace=config.namespace)
    elif config.type.lower() == "gitlab":
        return GitLabClient(token=config.token, base_url=config.url, namespace=config.namespace)
    else:
        return None
