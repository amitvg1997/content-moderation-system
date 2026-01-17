import json
import boto3
import uuid
from datetime import datetime

s3_client = boto3.client('s3')
sns_client = boto3.client('sns')

import os

def lambda_handler(event, context):
    """
    Entry point for moderation submissions.
    Receives: image_key (S3) + text
    Publishes: submission event to SNS topic
    """
    
    try:
        # Parse request
        body = json.loads(event.get('body', '{}'))
        text = body.get('text', '').strip()
        image_key = body.get('image_key')  # S3 key from frontend upload
        
        # Validation
        if not text and not image_key:
            return {
                'statusCode': 400,
                'headers': {
                    'Access-Control-Allow-Origin': '*',
                    'Access-Control-Allow-Methods': '*',
                    'Access-Control-Allow-Headers': '*'
                },
                'body': json.dumps({'error': 'Provide either text or image'})
            }
        
        # Generate submission ID
        submission_id = str(uuid.uuid4())
        timestamp = datetime.now().isoformat()
        
        # Create submission event
        submission_event = {
            'submission_id': submission_id,
            'timestamp': timestamp,
            'text': text,
            'image_key': image_key,
            'status': 'pending'
        }
        
        # Publish to SNS (triggers both image_moderator and text_moderator)
        sns_client.publish(
            TopicArn=os.getenv('SUBMISSION_TOPIC_ARN'),
            Message=json.dumps(submission_event)
        )
        
        # Immediate response to UI
        return {
            'statusCode': 202,  # Accepted (processing)
            'headers': {
                    'Access-Control-Allow-Origin': '*',
                    'Access-Control-Allow-Methods': '*',
                    'Access-Control-Allow-Headers': '*'
                },
            'body': json.dumps({
                'submission_id': submission_id,
                'message': 'Content submitted for moderation',
                'timestamp': timestamp
            })
        }
        
    except Exception as e:
        print(f"Error: {str(e)}")
        return {
            'statusCode': 500,
            'headers': {
                    'Access-Control-Allow-Origin': '*',
                    'Access-Control-Allow-Methods': '*',
                    'Access-Control-Allow-Headers': '*'
                },
            'body': json.dumps({'error': 'Internal server error'})
        }


