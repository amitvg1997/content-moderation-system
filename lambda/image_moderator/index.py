import json
import boto3
import os
from datetime import datetime

rekognition = boto3.client('rekognition')
s3_client = boto3.client('s3')
sns_client = boto3.client('sns')

def lambda_handler(event, context):
    """
    Analyzes image for explicit content using AWS Rekognition.
    Input: SNS message with submission event
    Output: Results published to results SNS topic
    """
    
    try:
        # Parse SNS message
        message = json.loads(event['Records'][0]['Sns']['Message'])
        submission_id = message['submission_id']
        image_key = message.get('image_key')
        
        # If no image, skip
        if not image_key:
            print(f"No image for {submission_id}, skipping image moderation")
            return {'statusCode': 200}
        
        bucket = os.getenv('UPLOADS_BUCKET')
        
        # Call Rekognition
        response = rekognition.detect_moderation_labels(
            Image={
                'S3Object': {
                    'Bucket': bucket,
                    'Name': image_key
                }
            }
        )
        
        # Analyze results
        explicit_labels = [
            label for label in response['ModerationLabels']
            if label['Confidence'] > 80  # Confidence threshold
        ]
        
        # Decision: image approved if no explicit content detected
        image_approved = len(explicit_labels) == 0
        
        # Create result event
        result = {
            'submission_id': submission_id,
            'moderation_type': 'image',
            'approved': image_approved,
            'confidence': max([l['Confidence'] for l in response['ModerationLabels']], 0),
            'labels': [l['Name'] for l in explicit_labels],
            'timestamp': datetime.utcnow().isoformat()
        }
        
        # Publish to results topic
        sns_client.publish(
            TopicArn=os.getenv('RESULTS_TOPIC_ARN'),
            Message=json.dumps(result)
        )
        
        print(f"Image moderation complete: {submission_id} - Approved: {image_approved}")
        return {'statusCode': 200}
        
    except Exception as e:
        print(f"Image moderation error: {str(e)}")
        # Return error result to decision handler
        return {'statusCode': 500}
