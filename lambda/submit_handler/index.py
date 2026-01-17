import json
import boto3
import uuid
import os
from datetime import datetime

sfn_client = boto3.client('stepfunctions')
s3_client = boto3.client('s3')

def lambda_handler(event, context):
    """
    POST /submit
    - If image_file provided: generates pre-signed URL
    - Frontend uploads image, then calls again with image_key
    - Starts Step Functions execution
    """
    try:
        body = json.loads(event.get('body', '{}'))
        text = body.get('text', '').strip()
        image_key = body.get('image_key')
        filename = body.get('filename')
        content_type = body.get('content_type')
        
        bucket = os.getenv('UPLOADS_BUCKET')
        submission_id = str(uuid.uuid4())
        state_machine_arn = os.getenv('STATE_MACHINE_ARN')
        
        # Case 1: First call - generate pre-signed URL for image
        if filename and content_type and not image_key:
            key = f"uploads/{datetime.utcnow().strftime('%Y%m%d-%H%M%S')}-{filename}"
            presigned_url = s3_client.generate_presigned_url(
                'put_object',
                Params={
                    'Bucket': bucket,
                    'Key': key,
                    'ContentType': content_type
                },
                ExpiresIn=300
            )
            
            return {
                'statusCode': 200,
                'headers': {
                    'Access-Control-Allow-Origin': '*',
                    'Access-Control-Allow-Methods': 'POST, OPTIONS',
                    'Access-Control-Allow-Headers': 'Content-Type'
                },
                'body': json.dumps({
                    'submission_id': submission_id,
                    'presigned_url': presigned_url,
                    'image_key': key,
                    'next_step': 'upload_image_then_submit'
                })
            }
        
        # Case 2: Second call - image uploaded, start moderation
        elif image_key:
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
                'headers': {
                    'Access-Control-Allow-Origin': '*',
                    'Access-Control-Allow-Methods': 'POST, OPTIONS',
                    'Access-Control-Allow-Headers': 'Content-Type'
                },
                'body': json.dumps({
                    'submission_id': submission_id,
                    'status': 'pending',
                    'message': 'Content submitted for moderation'
                })
            }
        
        else:
            # Text only submission
            sfn_client.start_execution(
                stateMachineArn=state_machine_arn,
                name=submission_id,
                input=json.dumps({
                    'submission_id': submission_id,
                    'text': text,
                    'image_key': None,
                    'created_at': datetime.now().isoformat()
                })
            )
            
            return {
                'statusCode': 202,
                'headers': {
                    'Access-Control-Allow-Origin': '*',
                    'Access-Control-Allow-Methods': 'POST, OPTIONS',
                    'Access-Control-Allow-Headers': 'Content-Type'
                },
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
