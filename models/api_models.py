from dataclasses import dataclass
from typing import Dict, Any

@dataclass
class FDLPayload:
    """Data class for FDL API payload"""
    sql_query: str
    schema_name: str
    params: Dict[str, str] = None

    def __post_init__(self):
        if self.params is None:
            self.params = {
                "timeZone": "Europe/Helsinki",
                "maxLimit": "100",
                "defaultLimit": "10"
            }

    def to_dict(self) -> Dict[str, Any]:
        return {
            "sqlQuery": self.sql_query,
            "schemaName": self.schema_name,
            "params": self.params
        }

@dataclass
class DQPayload:
    """Data class for DQ API payload"""
    question: str
    sourceApp: str = "Actions"
    topicId: str = ""
    context: list = None
    configuration: Dict[str, str] = None
    
    def __post_init__(self):
        if self.context is None:
            self.context = [""]
        if self.configuration is None:
            self.configuration = {
                "DEFAULT_TIME_PERIOD": "365",
                "DEFAULT_NUMBER_OF_ROWS": "10",
                "MAX_NUMBER_OF_ROWS": "100",
                "USER_LOCALE": "en-us"
            }
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "question": self.question,
            "sourceApp": self.sourceApp,
            "topicId": self.topicId,
            "context": self.context,
            "configuration": self.configuration
        }

@dataclass
class LoginPayload:
    """Data class for login payload"""
    username: str
    password: str
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "userName": self.username,  # Note: API expects 'userName' not 'username'
            "password": self.password
        }
