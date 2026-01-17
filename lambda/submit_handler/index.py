import json
import boto3
import uuid
import os
from datetime import datetime

sfn_client = boto3.client('stepfunctions')

def lambda_handler(event, context):
    """
    Entry point: receives text and/or image_key
    Starts Step Functions execution
    Returns submission_id immediately (status = pending)
    """
    try:
        body = json.loads(event.get('body', '{}'))
        text = body.get('text', '').strip()
        image_key = body.get('image_key')
        
        if not text and not image_key:
            return {
                'statusCode': 400,
                'body': json.dumps({'error': 'Provide either text or image'})
            }
        
        submission_id = str(uuid.uuid4())
        state_machine_arn = os.getenv('STATE_MACHINE_ARN')
        
        # Start Step Functions execution
        sfn_client.start_execution(
            stateMachineArn=state_machine_arn,
            name=submission_id,
            input=json.dumps({
                'submission_id': submission_id,
                'text': text,
                'image_key': image_key,
                'created_at': datetime.now().isoformat()
            })
        )
        
        return {
            'statusCode': 202,
            'body': json.dumps({
                'submission_id': submission_id,
                'status': 'pending',
                'message': 'Content submitted for moderation'
            })
        }
    
    except Exception as e:
        print(f"Error: {str(e)}")
        return {
            'statusCode': 500,
            'body': json.dumps({'error': 'Internal server error'})
        }
