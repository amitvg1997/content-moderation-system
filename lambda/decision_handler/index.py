import json
import boto3
import os
from datetime import datetime

dynamodb = boto3.resource('dynamodb')

def lambda_handler(event, context):
    """
    Makes final decision: if ALL checks pass, save to DynamoDB.
    Tracks moderation results and decides approval.
    """
    
    try:
        # Parse SNS message (moderation result)
        message = json.loads(event['Records'][0]['Sns']['Message'])
        submission_id = message['submission_id']
        
        table = dynamodb.Table(os.getenv('TABLE_NAME'))
        
        # Store individual moderation result in DynamoDB
        timestamp = datetime.utcnow().isoformat()
        
        # table.put_item(
        #     Item={
        #         'submission_id': submission_id,
        #         'timestamp': timestamp,
        #         'moderation_type': message.get('moderation_type'),
        #         'approved': message.get('approved'),
        #         'details': json.dumps({
        #             'sentiment': message.get('sentiment'),
        #             'confidence_scores': message.get('confidence_scores'),
        #             'labels': message.get('labels')
        #         }),
        #         'ttl': int(datetime.utcnow().timestamp()) + (86400 * 30)  # 30 days
        #     }
        # )
        
        # Query all results for this submission
        response = table.query(
            KeyConditionExpression='submission_id = :id',
            ExpressionAttributeValues={':id': submission_id}
        )
        
        results = response['Items']
        
        # Check if we have all results (image + text, or just one if not provided)
        image_result = next((r for r in results if r.get('moderation_type') == 'image'), None)
        text_result = next((r for r in results if r.get('moderation_type') == 'text'), None)
        
        # Determine final approval
        all_checks_pass = True
        
        if image_result:
            all_checks_pass = all_checks_pass and image_result['approved']
        
        if text_result:
            all_checks_pass = all_checks_pass and text_result['approved']
        
        print(f"Submission {submission_id}: Final decision = {all_checks_pass}")
        print(f"  Image result: {image_result}")
        print(f"  Text result: {text_result}")
        
        # Store final decision
        table.put_item(
            Item={
                'submission_id': submission_id,
                'timestamp': f"{timestamp}#final",
                'moderation_type': 'final_decision',
                'approved': all_checks_pass,
                'details': json.dumps({
                    'image_approved': image_result['approved'] if image_result else None,
                    'text_approved': text_result['approved'] if text_result else None
                }),
                'ttl': int(datetime.utcnow().timestamp()) + (86400 * 30)
            }
        )
        
        return {
            'statusCode': 200,
            'body': json.dumps({
                'submission_id': submission_id,
                'final_decision': 'approved' if all_checks_pass else 'rejected'
            })
        }
        
    except Exception as e:
        print(f"Decision handler error: {str(e)}")
        return {'statusCode': 500}
