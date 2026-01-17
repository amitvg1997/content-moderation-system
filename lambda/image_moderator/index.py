import json
import boto3
import os
from datetime import datetime

rekognition = boto3.client('rekognition')

def lambda_handler(event, context):
    """
    Analyzes image for explicit content using Rekognition
    Returns: { type, decision, labels, max_confidence }
    decision = APPROVE | REJECT | AMBIGUOUS
    rule:
      - If ANY moderation label has confidence > 75 → REJECT
      - Else if ANY label has confidence between 40 and 75 → AMBIGUOUS
      - Else (no labels or all < 40) → APPROVE
    """
    try:
        submission_id = event.get('submission_id')
        image_key = event.get('image_key')
        
        if not image_key:
            return {
                'type': 'image',
                'submission_id': submission_id,
                'skipped': True
            }
        
        bucket = os.getenv('UPLOADS_BUCKET')
        
        # Call Rekognition
        response = rekognition.detect_moderation_labels(
            Image={'S3Object': {'Bucket': bucket, 'Name': image_key}}
        )
        
        labels = response.get('ModerationLabels', [])
        
        max_confidence = max([l['Confidence'] for l in labels], default=0.0)
        
        # Default decision
        decision = 'APPROVE'
        
        # Apply your rule
        for label in labels:
            conf = label['Confidence']
            if conf > 75:
                decision = 'REJECT'
                break
            elif 40 <= conf <= 75 and decision != 'REJECT':
                decision = 'AMBIGUOUS'
        
        result = {
            'type': 'image',
            'submission_id': submission_id,
            'decision': decision,
            'labels': [l['Name'] for l in labels],
            'max_confidence': round(max_confidence, 2),
            'label_details': [
                {'name': l['Name'], 'confidence': round(l['Confidence'], 2)}
                for l in labels
            ],
            'timestamp': datetime.now().isoformat()
        }
        
        print(f"Image moderation: {submission_id} - Decision: {decision}")
        return result
    
    except Exception as e:
        print(f"Image moderation error: {str(e)}")
        return {
            'type': 'image',
            'submission_id': event.get('submission_id'),
            'decision': 'AMBIGUOUS',
            'error': str(e)
        }
