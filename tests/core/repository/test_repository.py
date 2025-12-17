import unittest
from unittest.mock import MagicMock, patch
from core.repository.github_client import GitHubClient
from core.repository.gitlab_client import GitLabClient
from core.repository.factory import get_repository_client
from config import RepositoryConfig

class TestRepositoryClients(unittest.TestCase):

    @patch('core.repository.github_client.requests.get')
    def test_github_list_projects_user(self, mock_get):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = [
            {
                "full_name": "user/repo1",
                "clone_url": "https://github.com/user/repo1.git",
                "description": "Test Repo 1",
                "default_branch": "main"
            }
        ]
        mock_get.return_value = mock_response

        client = GitHubClient(token="fake_token")
        projects = client.list_projects()

        self.assertEqual(len(projects), 1)
        self.assertEqual(projects[0].name, "user/repo1")
        self.assertEqual(projects[0].url, "https://github.com/user/repo1.git")

    @patch('core.repository.github_client.requests.get')
    def test_github_list_branches(self, mock_get):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = [
            {"name": "main"},
            {"name": "dev"}
        ]
        mock_get.return_value = mock_response

        client = GitHubClient(token="fake_token")
        branches = client.list_branches("user/repo1")

        self.assertEqual(len(branches), 2)
        self.assertIn("main", branches)
        self.assertIn("dev", branches)

    @patch('core.repository.gitlab_client.requests.get')
    def test_gitlab_list_projects(self, mock_get):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = [
            {
                "path_with_namespace": "group/project1",
                "http_url_to_repo": "https://gitlab.com/group/project1.git",
                "description": "Test Project 1",
                "default_branch": "master"
            }
        ]
        mock_get.return_value = mock_response

        client = GitLabClient(token="fake_token")
        projects = client.list_projects()

        self.assertEqual(len(projects), 1)
        self.assertEqual(projects[0].name, "group/project1")

    def test_factory(self):
        config_github = RepositoryConfig(name="gh", type="github", token="123")
        client_gh = get_repository_client(config_github)
        self.assertIsInstance(client_gh, GitHubClient)

        config_gitlab = RepositoryConfig(name="gl", type="gitlab", token="456")
        client_gl = get_repository_client(config_gitlab)
        self.assertIsInstance(client_gl, GitLabClient)

        config_unknown = RepositoryConfig(name="uk", type="bitbucket", token="789")
        client_uk = get_repository_client(config_unknown)
        self.assertIsNone(client_uk)

if __name__ == '__main__':
    unittest.main()
