import json
import boto3
import requests
from datetime import datetime
from botocore.exceptions import ClientError

# AWS Secrets Manager
REGION_NAME = "eu-west-1"
SECRET_NAME = "amit-AWS-incident-creation-token"
GITHUB_REPO = "amitvg1997/content-moderation-system"  
GITHUB_API_URL = f'https://api.github.com/repos/{GITHUB_REPO}/issues'

def get_github_token():
    """Fetch GitHub token from AWS Secrets Manager"""
    session = boto3.session.Session()
    client = session.client(
        service_name='secretsmanager',
        region_name=REGION_NAME
    )
    
    response = client.get_secret_value(SecretId=SECRET_NAME)
    secret = response['SecretString']
    return json.loads(secret)['amit-AWS-incident-creation-token']

def lambda_handler(event, context):
    
    try:
        github_token = get_github_token()
        
        # Extract basic error info
        detail = event.get('detail', {})
        function_name = detail.get('functionName', 'Unknown')
        error_message = detail.get('errorMessage', 'Unknown error')
        
        # Simple issue format
        title = f"🚨 Error: {function_name}"
        body = f"Function: {function_name}\n\nError: {error_message}\n\nTime: {datetime.utcnow().isoformat()}"
        
        payload = {
            'title': title,
            'body': body,
            'labels': ['incident']
        }
        
        headers = {
            'Authorization': f'token {github_token}',
            'Accept': 'application/vnd.github.v3+json'
        }
        
        response = requests.post(GITHUB_API_URL, json=payload, headers=headers)
        
        if response.status_code == 201:
            issue = response.json()
            print(f"✅ Issue created: {issue['html_url']}")
            return {'statusCode': 201, 'issue_url': issue['html_url']}
        else:
            print(f"❌ Error: {response.status_code}")
            return {'statusCode': response.status_code, 'error': response.text}
    
    except Exception as e:
        print(f"❌ Exception: {str(e)}")
        return {'statusCode': 500, 'error': str(e)}