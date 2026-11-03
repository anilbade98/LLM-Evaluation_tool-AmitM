import requests
import json
from requests.exceptions import RequestException

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from config.api_endpoint import get_login_endpoint,get_topicId_api_endpoint
from config.environment_config import EnvironmentConfig
from models.api_models import LoginPayload
from auth.base_auth import APIHeaders


# Global variables to store auth token and topic id
AUTH_TOKEN = ""
TOPIC_ID = None

def get_env_config():
    """
    Get configuration from environment variables for Jenkins parameterization
    
    Returns:
        dict: Configuration dictionary with environment variables
    """
    return {
        'input_file': EnvironmentConfig.get_config_value('INPUT_FILE_NAME'),
        'login_user': EnvironmentConfig.get_config_value('CXONE_USER_NAME'),
        'model_name': EnvironmentConfig.get_config_value('MODEL'),
        'environment': os.environ.get('CXONE_ENV', os.environ.get('ENV_NAME', 'test')),
        'parts': EnvironmentConfig.get_config_value('PARTS')
    }

def log_in(username: str, password: str) -> str:
    """
    Log in and get authentication token
    
    Args:
        username (str): Username for login
        password (str): Password for login
        
    Returns:
        str: Authentication token
    """
    global AUTH_TOKEN

    print(f"Sending log in request to {get_login_endpoint()}")

    # Create payload using data class
    payload = LoginPayload(username=username, password=password)
    
    # Get headers
    headers = APIHeaders().to_dict()
    
    try:
        response = requests.post(
            get_login_endpoint(), 
            headers=headers, 
            data=json.dumps(payload.to_dict())
        )
        
        # Check if request was successful
        response.raise_for_status()
        
        # Parse response
        response_json = response.json()
        
        # Validate response structure
        if 'token' not in response_json:
            raise ValueError("Invalid response structure: missing 'token'")
        else:
            print("Log in successful")

        # Store the auth token
        AUTH_TOKEN = 'Bearer ' + response_json['token']
        return AUTH_TOKEN
        
    except RequestException as e:
        print(f"API request failed: {str(e)}")
        raise
    except Exception as e:
        print(f"Unexpected error during login: {str(e)}")
        raise

def get_topic_id(token):
    global TOPIC_ID
    if TOPIC_ID is not None:
        print(f"Using cached TopicId: {TOPIC_ID}")
        return TOPIC_ID
    print("Starting Topic API process")
    # Ensure token is correctly formatted
    if not token.startswith("Bearer "):
        token = "Bearer " + token
    headers = {
        'Content-Type': 'application/json',
        'Authorization': token
    }
    response = requests.get(get_topicId_api_endpoint(), headers=headers)
    if not response.ok:
        print(f"Failed to login: {response.status_code} {response.text}")
        raise Exception(f"Failed to login: {response.reason}")
    data = response.json()
    topic_id = data['topics'][0]['topicId']
    TOPIC_ID = topic_id
    print(f"TopicId successful, topicId: {topic_id}")
    return topic_id