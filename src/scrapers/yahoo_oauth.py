"""Yahoo OAuth authentication helper"""
import json
import os
from pathlib import Path
from typing import Optional, Dict
import logging
import webbrowser
from urllib.parse import urlencode
import time

import requests
from requests.auth import HTTPBasicAuth

from config import DATA_DIR


logger = logging.getLogger(__name__)


class YahooOAuth:
    """Handle Yahoo OAuth 2.0 authentication"""
    
    OAUTH_BASE_URL = "https://api.login.yahoo.com/oauth2"
    
    def __init__(self, client_id: str, client_secret: str):
        self.client_id = client_id
        self.client_secret = client_secret
        self.redirect_uri = "oob"  # Out-of-band for CLI apps
        
        # Token storage
        self.token_file = DATA_DIR / "yahoo_auth" / "tokens.json"
        self.token_file.parent.mkdir(parents=True, exist_ok=True)
        
        self.access_token = None
        self.refresh_token = None
        self.token_expiry = None
        
        # Load existing tokens
        self._load_tokens()
    
    def _load_tokens(self):
        """Load tokens from file"""
        if self.token_file.exists():
            try:
                with open(self.token_file, 'r') as f:
                    data = json.load(f)
                    self.access_token = data.get('access_token')
                    self.refresh_token = data.get('refresh_token')
                    self.token_expiry = data.get('token_expiry')
                    logger.info("Loaded existing Yahoo tokens")
            except Exception as e:
                logger.error(f"Error loading tokens: {e}")
    
    def _save_tokens(self):
        """Save tokens to file"""
        try:
            data = {
                'access_token': self.access_token,
                'refresh_token': self.refresh_token,
                'token_expiry': self.token_expiry
            }
            with open(self.token_file, 'w') as f:
                json.dump(data, f, indent=2)
            logger.info("Saved Yahoo tokens")
        except Exception as e:
            logger.error(f"Error saving tokens: {e}")
    
    def get_authorization_url(self) -> str:
        """Get the authorization URL for user consent"""
        params = {
            'client_id': self.client_id,
            'redirect_uri': self.redirect_uri,
            'response_type': 'code',
            'language': 'en-us'
        }
        return f"{self.OAUTH_BASE_URL}/request_auth?{urlencode(params)}"
    
    def authenticate(self) -> bool:
        """Perform OAuth authentication flow"""
        # Check if we have valid tokens
        if self.is_authenticated():
            return True
        
        # Try to refresh if we have a refresh token
        if self.refresh_token and self._refresh_access_token():
            return True
        
        # Otherwise, do full auth flow
        return self._do_auth_flow()
    
    def _do_auth_flow(self) -> bool:
        """Perform full OAuth flow"""
        try:
            # Get authorization URL
            auth_url = self.get_authorization_url()
            
            print("\n" + "="*60)
            print("Yahoo Fantasy API Authentication Required")
            print("="*60)
            print("\n1. Open this URL in your browser:")
            print(f"\n   {auth_url}\n")
            print("2. Authorize the application")
            print("3. Copy the authorization code shown")
            print("="*60 + "\n")
            
            # Try to open browser
            try:
                webbrowser.open(auth_url)
                print("(Browser should have opened automatically)")
            except:
                pass
            
            # Get authorization code from user
            auth_code = input("\nEnter the authorization code: ").strip()
            
            if not auth_code:
                logger.error("No authorization code provided")
                return False
            
            # Exchange code for tokens
            return self._exchange_code_for_tokens(auth_code)
            
        except Exception as e:
            logger.error(f"Error in auth flow: {e}")
            return False
    
    def _exchange_code_for_tokens(self, auth_code: str) -> bool:
        """Exchange authorization code for access tokens"""
        try:
            url = f"{self.OAUTH_BASE_URL}/get_token"
            
            data = {
                'client_id': self.client_id,
                'client_secret': self.client_secret,
                'redirect_uri': self.redirect_uri,
                'code': auth_code,
                'grant_type': 'authorization_code'
            }
            
            response = requests.post(
                url,
                data=data,
                auth=HTTPBasicAuth(self.client_id, self.client_secret)
            )
            
            if response.status_code == 200:
                token_data = response.json()
                self.access_token = token_data.get('access_token')
                self.refresh_token = token_data.get('refresh_token')
                self.token_expiry = time.time() + token_data.get('expires_in', 3600)
                
                self._save_tokens()
                logger.info("Successfully obtained Yahoo access tokens")
                return True
            else:
                logger.error(f"Token exchange failed: {response.status_code} - {response.text}")
                return False
                
        except Exception as e:
            logger.error(f"Error exchanging code for tokens: {e}")
            return False
    
    def _refresh_access_token(self) -> bool:
        """Refresh the access token using refresh token"""
        if not self.refresh_token:
            return False
        
        try:
            url = f"{self.OAUTH_BASE_URL}/get_token"
            
            data = {
                'client_id': self.client_id,
                'client_secret': self.client_secret,
                'redirect_uri': self.redirect_uri,
                'refresh_token': self.refresh_token,
                'grant_type': 'refresh_token'
            }
            
            response = requests.post(
                url,
                data=data,
                auth=HTTPBasicAuth(self.client_id, self.client_secret)
            )
            
            if response.status_code == 200:
                token_data = response.json()
                self.access_token = token_data.get('access_token')
                # Yahoo doesn't always return a new refresh token
                if token_data.get('refresh_token'):
                    self.refresh_token = token_data.get('refresh_token')
                self.token_expiry = time.time() + token_data.get('expires_in', 3600)
                
                self._save_tokens()
                logger.info("Successfully refreshed Yahoo access token")
                return True
            else:
                logger.error(f"Token refresh failed: {response.status_code}")
                return False
                
        except Exception as e:
            logger.error(f"Error refreshing token: {e}")
            return False
    
    def is_authenticated(self) -> bool:
        """Check if we have valid authentication"""
        if not self.access_token:
            return False
        
        # Check if token is expired
        if self.token_expiry and time.time() >= self.token_expiry:
            logger.info("Access token expired")
            return False
        
        return True
    
    def get_auth_header(self) -> Dict[str, str]:
        """Get authorization header for API requests"""
        if not self.is_authenticated() and not self.authenticate():
            raise RuntimeError("Yahoo authentication failed")
        
        return {
            'Authorization': f'Bearer {self.access_token}'
        }