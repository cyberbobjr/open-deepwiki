from typing import List, Optional
import requests
from .base import RepositoryClient, ProjectInfo

class GitHubClient(RepositoryClient):
    def __init__(self, token: Optional[str] = None, base_url: Optional[str] = None, namespace: Optional[str] = None):
        self.token = token
        self.base_url = base_url.rstrip("/") if base_url else "https://api.github.com"
        self.namespace = namespace
        self.headers = {"Accept": "application/vnd.github.v3+json"}
        if token:
            self.headers["Authorization"] = f"token {token}"

    def list_projects(self) -> List[ProjectInfo]:
        projects = []
        page = 1
        per_page = 100

        while True:
            # If namespace is provided, list repos for that user/org
            if self.namespace:
                # Try org first, if fails try user? Or assume namespace is just user/org path
                # https://api.github.com/orgs/{org}/repos
                # https://api.github.com/users/{user}/repos
                # For simplicity, let's assume if it fails for org, we might try user, or just use search?
                # A safer bet is searching or using the 'user' endpoint if authenticated user matches namespace.
                # Let's try listing for user if authenticated, or general search?

                # Let's try: GET /users/{username}/repos (works for orgs too often? No, orgs have /orgs/{org}/repos)

                # Simplification: Try /orgs first, fall back to /users?
                # Or just assume the user knows what they are doing.
                # Let's try /users/{namespace}/repos as it often redirects or works? No.

                # Let's try to detect if it is an org or user?
                # Or we can just use search: `q=user:namespace`

                url = f"{self.base_url}/users/{self.namespace}/repos"
                params = {"page": page, "per_page": per_page}
                try:
                    resp = requests.get(url, headers=self.headers, params=params)
                    if resp.status_code == 404:
                         # Try org
                         url = f"{self.base_url}/orgs/{self.namespace}/repos"
                         resp = requests.get(url, headers=self.headers, params=params)
                except requests.RequestException:
                    break

            else:
                # List authenticated user's repos
                url = f"{self.base_url}/user/repos"
                params = {"page": page, "per_page": per_page}
                resp = requests.get(url, headers=self.headers, params=params)

            if resp.status_code != 200:
                # logging.error(f"Failed to fetch projects: {resp.status_code} {resp.text}")
                break

            data = resp.json()
            if not data:
                break

            for repo in data:
                projects.append(ProjectInfo(
                    name=repo["full_name"],
                    url=repo["clone_url"],
                    description=repo.get("description"),
                    default_branch=repo.get("default_branch", "main")
                ))

            page += 1
            if len(data) < per_page:
                break

        return projects

    def list_branches(self, project_name: str) -> List[str]:
        # project_name should be "owner/repo" for GitHub
        branches = []
        page = 1
        per_page = 100

        while True:
            url = f"{self.base_url}/repos/{project_name}/branches"
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
