import os

class EnvironmentConfig:
    
    @staticmethod
    def get_config_value(key, fallback_key=None):
        """Get configuration value with fallback logic"""
        # First try to get from environment variables (Jenkins parameters)
        value = os.environ.get(key)
        if value and value.strip():
            return value.strip()
        
        # Try fallback key if provided
        if fallback_key:
            value = os.environ.get(fallback_key)
            if value and value.strip():
                return value.strip()
        
        # Get default values based on environment
        defaults = EnvironmentConfig.get_default_values()
        default_value = defaults.get(key)
        if default_value:
            return default_value
        
        # Final fallback - return empty string
        return ''
    
    @staticmethod
    def get_default_values():
        """Get default configuration values based on environment"""
        profile = os.environ.get('PROFILE', os.environ.get('CXONE_ENV', 'test'))
        
        # Handle different environment naming conventions
        if profile in ['test', 'test-illum']:
            env_suffix = 'test.niceincontact.com'
            internal_suffix = 'test-illum.internal'
            dq_env = 'test'
        elif profile in ['dev', 'dev-illum']:
            env_suffix = 'dev.niceincontact.com'
            internal_suffix = 'dev-illum.internal'
            dq_env = 'dev'
        elif profile in ['staging', 'staging-illum']:
            env_suffix = 'staging.niceincontact.com'
            internal_suffix = 'staging-illum.internal'
            dq_env = 'staging'
        elif profile in ['prod', 'production']:
            env_suffix = 'niceincontact.com'
            internal_suffix = 'prod-illum.internal'
            dq_env = 'prod'
        else:
            env_suffix = 'test.niceincontact.com'
            internal_suffix = 'test-illum.internal'
            dq_env = 'test'

        return {
            'DQ_BASE_URL': f"http://sem-querydata-alb.illuminate.service.nicecxone-{dq_env}.com/eai-data-query",
            'FDL_BASE_URL': f"http://fdl-svc-alb.{internal_suffix}:9007",
            'LOGIN_ENDPOINT': f"https://api-na1.{env_suffix}/public/authentication/v1/login",
            'FACADE_BASE_URL': f"https://api-na1.{env_suffix}",
            'CXONE_USER_NAME': 'vaishnavi.darandaletest@nice.com',
            'CXONE_PASSWORD': 'Niceadmin@12345',
            'INPUT_FILE_NAME': 'InputTestfile.xlsx',
            'MODEL': 'default_model',
            'PARTS': 'default_parts'
        }
    
    @staticmethod
    def validate_required_params():
        """Validate that all required parameters are available"""
        required_params = ['CXONE_USER_NAME', 'CXONE_PASSWORD']
        missing_params = []
        
        for param in required_params:
            value = os.environ.get(param)
            if not value or not value.strip():
                missing_params.append(param)
        
        if missing_params:
            raise ValueError(f"Missing required parameters: {', '.join(missing_params)}")
        
        return True
    
    @staticmethod
    def print_configuration():
        """Print current configuration for debugging"""
        print("\n" + "="*80)
        print("ENVIRONMENT CONFIGURATION")
        print("="*80)
        print(f"Environment: {os.environ.get('CXONE_ENV', os.environ.get('ENV_NAME', 'test'))}")
        print(f"DQ Base URL: {EnvironmentConfig.get_config_value('DQ_BASE_URL')}")
        print(f"FDL Base URL: {EnvironmentConfig.get_config_value('FDL_BASE_URL')}")
        print(f"Login Endpoint: {EnvironmentConfig.get_config_value('LOGIN_ENDPOINT')}")
        print(f"Username: {EnvironmentConfig.get_config_value('CXONE_USER_NAME')}")
        print(f"Input File: {EnvironmentConfig.get_config_value('INPUT_FILE_NAME')}")
        print(f"Model: {EnvironmentConfig.get_config_value('MODEL')}")
        print(f"Parts: {EnvironmentConfig.get_config_value('PARTS')}")
        print("="*80)
