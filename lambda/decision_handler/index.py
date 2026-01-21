import json
import boto3
import os
from datetime import datetime
import logging

dynamodb = boto3.resource('dynamodb')
sns_client = boto3.client('sns')

logger = logging.getLogger(__name__)  
logger.setLevel(logging.INFO)

def lambda_handler(event, context):
    """
    Receives array of [text_result, image_result] from parallel tasks
    Determines final decision: APPROVE | REJECT | REVIEW
    APPROVE → save to approved table
    REJECT → save to rejected table
    REVIEW → save to review table and email admin
    """
    try:
        moderation_results = event.get('moderation_results', [])
        logger.info("Moderation Results: %s", moderation_results)
        submission_id = event.get('submission_id')
        text = event.get('text')
        image_key = event.get('image_key')
        logger.info("Moderation Results: %s", moderation_results)
        logger.info(
            "text: %s image_key: %s submissionId: %s",
            text,
            image_key,
            submission_id
        )       
        approved_table = dynamodb.Table(os.getenv('APPROVED_TABLE'))
        review_table = dynamodb.Table(os.getenv('REVIEW_TABLE'))
        rejected_table = dynamodb.Table(os.getenv('REJECTED_TABLE'))
        notification_topic = os.getenv('ADMIN_NOTIFICATION_TOPIC')
        
        # Parse results
        text_result = None
        image_result = None
        
        for result in moderation_results:
            if result.get('type') == 'text':
                text_result = result
            elif result.get('type') == 'image':
                image_result = result
        
        # Determine overall decision
        has_reject = False
        has_ambiguous = False
        
        if text_result and not text_result.get('skipped'):
            if text_result.get('decision') == 'REJECT':
                has_reject = True
            elif text_result.get('decision') == 'AMBIGUOUS':
                has_ambiguous = True
        
        if image_result and not image_result.get('skipped'):
            if image_result.get('decision') == 'REJECT':
                has_reject = True
            elif image_result.get('decision') == 'AMBIGUOUS':
                has_ambiguous = True
        
        timestamp = datetime.now().isoformat()
        
        if has_reject:
            final_decision = 'REJECT'
        elif has_ambiguous:
            final_decision = 'REVIEW'
        else:
            final_decision = 'APPROVE'
        
        # Save based on decision
        if final_decision == 'APPROVE':
            approved_table.put_item(
                Item={
                    'submission_id': submission_id,
                    'status': 'APPROVED',
                    'text': text or '',
                    'image_key': image_key or '',
                    'approved_at': timestamp,
                    'ttl': int(datetime.now().timestamp()) + (86400 * 30)
                }
            )
        
        elif final_decision == 'REVIEW':
            review_table.put_item(
                Item={
                    'submission_id': submission_id,
                    'status': 'PENDING_REVIEW',
                    'text': text or '',
                    'image_key': image_key or '',
                    'created_at': timestamp,
                    'moderation_details': json.dumps({
                        'text_decision': text_result.get('decision') if text_result else None,
                        'text_sentiment': text_result.get('sentiment') if text_result else None,
                        'image_decision': image_result.get('decision') if image_result else None,
                        'image_labels': image_result.get('labels') if image_result else []
                    }),
                    'ttl': int(datetime.now().timestamp()) + (86400 * 30)
                }
            )
            
            # Send admin notification
            message = f"""
New content requires admin review:

Submission ID: {submission_id}

Text: {(text[:100] + '...') if text and len(text) > 100 else text or '(none)'}
Image: {image_key or '(none)'}

Text Decision: {text_result.get('decision') if text_result else 'N/A'} ({text_result.get('sentiment') if text_result else 'N/A'})
Image Decision: {image_result.get('decision') if image_result else 'N/A'}

Please review on Admin Dashboard!

Admin Dashboard Link: http://amit-moderation-admin-frontend.s3-website-eu-west-1.amazonaws.com/
            """
            
            sns_client.publish(
                TopicArn=notification_topic,
                Subject='Content Requires Review',
                Message=message
            )
        elif final_decision == 'REJECT':
            rejected_table.put_item(
                Item={
                    'submission_id': submission_id,
                    'status': 'REJECTED',
                    'rejected_at': timestamp,
                    'moderation_details': json.dumps({
                        'text_decision': text_result.get('decision') if text_result else None,
                        'text_sentiment': text_result.get('sentiment') if text_result else None,
                        'image_decision': image_result.get('decision') if image_result else None,
                        'image_labels': image_result.get('labels') if image_result else []
                    }),
                    'ttl': int(datetime.now().timestamp()) + (86400 * 30)
                }
            )
        
        # Return result to caller (via Step Functions)
        return {
            'submission_id': submission_id,
            'final_decision': final_decision,
            'timestamp': timestamp,
            'text_result': text_result,
            'image_result': image_result
        }
    
    except Exception as e:
        print(f"Decision handler error: {str(e)}")
        return {
            'submission_id': event.get('submission_id'),
            'final_decision': 'ERROR',
            'error': str(e)
        }
