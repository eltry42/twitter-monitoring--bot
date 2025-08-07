import json
import logging
import os
import random
import time
from typing import List, Union

import requests

from graphql_api import GraphqlAPI  # You must define this module
from utils import find_one          # You must define this utility


def _get_auth_headers(headers, cookies: dict) -> dict:
    """Merge default headers with auth-related headers extracted from cookies"""
    authed_headers = headers | {
        'cookie': '; '.join(f'{k}={v}' for k, v in cookies.items()),
        'referer': 'https://twitter.com/',
        'x-csrf-token': cookies.get('ct0', ''),
        'x-guest-token': cookies.get('guest_token', ''),
        'x-twitter-auth-type': 'OAuth2Session' if cookies.get('auth_token') else '',
        'x-twitter-active-user': 'yes',
        'x-twitter-client-language': 'en',
    }
    return dict(sorted({k.lower(): v for k, v in authed_headers.items()}.items()))


def _build_params(params: dict) -> dict:
    """JSON stringify all params (Twitter GraphQL expects this)"""
    return {k: json.dumps(v) for k, v in params.items()}


def convert_playwright_cookie_list_to_dict(cookie_list: list) -> dict:
    """Convert Playwright-style cookies (list of dicts) into a simple dict"""
    return {cookie["name"]: cookie["value"] for cookie in cookie_list}


class TwitterWatcher:

    def __init__(self, auth_username_list: List[str], cookies_dir: str):
        assert auth_username_list, "Username list can't be empty"

        self.token_number = len(auth_username_list)
        self.auth_cookie_list = []
        self.logger = logging.getLogger('api')

        for username in auth_username_list:
            cookie_path = os.path.join(cookies_dir, f"{username}.json")
            with open(cookie_path, 'r') as f:
                cookie_data = json.load(f)

                # Convert if needed
                if isinstance(cookie_data, list):
                    cookie_data = convert_playwright_cookie_list_to_dict(cookie_data)

                cookie_data['username'] = username
                self.auth_cookie_list.append(cookie_data)

        self.current_token_index = random.randrange(self.token_number)

    def query(self, api_name: str, params: dict) -> Union[dict, list, None]:
        """Send authenticated Twitter GraphQL request using rotating tokens"""
        url, method, headers, features = GraphqlAPI.get_api_data(api_name)
        params = _build_params({"variables": params, "features": features})

        for _ in range(self.token_number):
            self.current_token_index = (self.current_token_index + 1) % self.token_number
            auth_headers = _get_auth_headers(headers, self.auth_cookie_list[self.current_token_index])

            try:
                response = requests.request(method=method, url=url, headers=auth_headers, params=params, timeout=30)
            except requests.exceptions.ConnectionError as e:
                self.logger.error(f"{url} connection error: {e}, trying next token...")
                continue

            if response.status_code in [200, 403, 404]:
                if not response.text:
                    self.logger.warning(f"{url} returned empty response {response.status_code}, skipping...")
                    continue

                json_response = response.json()
                if "errors" in json_response:
                    self.logger.warning(f"{url} returned errors: {json_response['errors']}")
                    continue

                return json_response

            if response.status_code != 429:
                self.logger.warning(f"{url} HTTP {response.status_code}: {response.text}")
                continue

        self.logger.error("All tokens failed. Final request:\n" +
                          json.dumps(auth_headers, indent=2) + "\n" +
                          json.dumps(params, indent=2))
        return None

    def get_user_by_username(self, username: str, params: dict = {}) -> dict:
        api_name = 'UserByScreenName'
        params['screen_name'] = username
        json_response = self.query(api_name, params)

        while json_response is None:
            time.sleep(60)
            json_response = self.query(api_name, params)

        return json_response

    def get_user_by_id(self, user_id: int, params: dict = {}) -> dict:
        api_name = 'UserByRestId'
        params['userId'] = user_id
        json_response = self.query(api_name, params)

        while json_response is None:
            time.sleep(60)
            json_response = self.query(api_name, params)

        return json_response

    def get_id_by_username(self, username: str):
        user = self.get_user_by_username(username)
        return find_one(user, 'rest_id')

    def check_tokens(self, test_username: str = 'X', output_response: bool = False):
        result = dict()
        for auth_cookie in self.auth_cookie_list:
            try:
                url, method, headers, features = GraphqlAPI.get_api_data('UserByScreenName')
                params = _build_params({"variables": {'screen_name': test_username}, "features": features})
                auth_headers = _get_auth_headers(headers, auth_cookie)
                response = requests.request(method=method, url=url, headers=auth_headers, params=params, timeout=30)
            except requests.exceptions.RequestException as e:
                result[auth_cookie['username']] = False
                print(f"Token {auth_cookie['username']} failed with exception: {e}")
                continue

            result[auth_cookie['username']] = (response.status_code == 200)

            if output_response:
                print(json.dumps(response.json(), indent=2))

        return result
