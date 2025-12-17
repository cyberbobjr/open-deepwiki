from typing import List, Optional
import requests
from .base import RepositoryClient, ProjectInfo

class GitLabClient(RepositoryClient):
    def __init__(self, token: Optional[str] = None, base_url: Optional[str] = None, namespace: Optional[str] = None):
        self.token = token
        self.base_url = base_url.rstrip("/") if base_url else "https://gitlab.com/api/v4"
        self.namespace = namespace
        self.headers = {}
        if token:
            self.headers["Private-Token"] = token

    def list_projects(self) -> List[ProjectInfo]:
        projects = []
        page = 1
        per_page = 100

        while True:
            url = f"{self.base_url}/projects"
            params = {"page": page, "per_page": per_page, "simple": "true"}

            # If namespace is provided, unfortunately GitLab doesn't allow listing projects by namespace easily in one go
            # without search or iterating groups.
            # But we can use membership=true if no namespace.

            # If namespace provided, we might search groups?
            # Or use `GET /groups/:id/projects`

            # Let's simplify:
            if self.namespace:
                 # Assume namespace is a group ID or path? Path needs URL encoding
                 # But resolving path to ID requires another call.
                 # Let's try searching by attribute?
                 # Actually, usually users want to scan a group.
                 # Let's try /groups/{id}/projects if namespace is given (assuming it's a group path/id)
                 # Note: If namespace has slashes, it must be URL-encoded.

                 # NOTE: This is a simplistic implementation.
                 # Handling encoded slashes in python:
                 import urllib.parse
                 encoded_ns = urllib.parse.quote(self.namespace, safe='')
                 url = f"{self.base_url}/groups/{encoded_ns}/projects"
            else:
                params["membership"] = "true"

            resp = requests.get(url, headers=self.headers, params=params)

            if resp.status_code != 200:
                break

            data = resp.json()
            if not data:
                break

            for repo in data:
                projects.append(ProjectInfo(
                    name=repo["path_with_namespace"],
                    url=repo["http_url_to_repo"],
                    description=repo.get("description"),
                    default_branch=repo.get("default_branch", "main")
                ))

            page += 1
            # GitLab uses X-Total-Pages header usually, or just empty list check
            if len(data) < per_page:
                break

        return projects

    def list_branches(self, project_name: str) -> List[str]:
        # project_name is path_with_namespace or ID.
        # Needs to be URL encoded
        import urllib.parse
        encoded_id = urllib.parse.quote(project_name, safe='')

        branches = []
        page = 1
        per_page = 100

        while True:
            url = f"{self.base_url}/projects/{encoded_id}/repository/branches"
            params = {"page": page, "per_page": per_page}
            resp = requests.get(url, headers=self.headers, params=params)

            if resp.status_code != 200:
                break

            data = resp.json()
            if not data:
                break

            for branch in data:
                branches.append(branch["name"])

            page += 1
            if len(data) < per_page:
                break

        return branches
