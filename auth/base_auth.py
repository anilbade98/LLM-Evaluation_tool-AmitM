from abc import ABC, abstractmethod
from typing import Dict

class APIHeaders:
    """Class for API headers"""
    def __init__(self, content_type: str = 'application/json', authorization: str = ''):
        self.content_type = content_type
        self.authorization = authorization

    def to_dict(self) -> Dict[str, str]:
        return {
            'Content-Type': self.content_type,
            'Authorization': self.authorization
        }

class BaseAuth(ABC):
    """Base authentication class"""
    
    @abstractmethod
    def get_auth_token(self) -> str:
        """Get authentication token"""
        pass

    def get_headers(self) -> APIHeaders:
        """Get headers with authentication"""
        return APIHeaders(authorization=self.get_auth_token())

class TokenAuth(BaseAuth):
    """Token-based authentication implementation"""
    
    def __init__(self, token: str):
        self._token = token

    def get_auth_token(self) -> str:
        return self._token
    
