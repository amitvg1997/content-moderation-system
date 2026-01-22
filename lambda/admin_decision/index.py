import json
import boto3
import os
from datetime import datetime

dynamodb = boto3.resource('dynamodb')

def lambda_handler(event, context):
    """
    POST /admin/decision
    Body: { submissionId, decision }
    decision = APPROVED | REJECTED
    Moves from review table to approved table or marks rejected
    """
    try:
        body = json.loads(event.get('body', '{}'))
        submission_id = body.get('submission_id')
        decision = body.get('decision')  # APPROVE or REJECT
        
        if not submission_id or not decision:
            return {
                'statusCode': 400,
                'headers': {
                    'Access-Control-Allow-Origin': '*',
                    'Access-Control-Allow-Methods': '*',
                    'Access-Control-Allow-Headers': '*'
                },
                'body': json.dumps({'error': 'Missing submissionId or decision'})
            }
        
        if decision not in ['APPROVE', 'REJECT']:
            return {
                'statusCode': 400,
                'headers': {
                    'Access-Control-Allow-Origin': '*',
                    'Access-Control-Allow-Methods': '*',
                    'Access-Control-Allow-Headers': '*'
                },
                'body': json.dumps({'error': 'Decision must be APPROVE or REJECT'})
            }
        
        review_table = dynamodb.Table(os.getenv('REVIEW_TABLE'))
        approved_table = dynamodb.Table(os.getenv('APPROVED_TABLE'))
        rejected_table = dynamodb.Table(os.getenv('REJECTED_TABLE'))
        
        # Get item from review table
        response = review_table.get_item(Key={'submission_id': submission_id})
        
        if 'Item' not in response:
            return {
                'statusCode': 404,
                'headers': {
                    'Access-Control-Allow-Origin': '*',
                    'Access-Control-Allow-Methods': '*',
                    'Access-Control-Allow-Headers': '*'
                },
                'body': json.dumps({'error': 'Submission not found'})
            }
        
        item = response['Item']
        timestamp = datetime.now().isoformat()

        if decision == 'APPROVE':
            status = 'APPROVED'
        else:  # REJECT
            status = 'REJECTED'
        
        if decision == 'APPROVE':
            # Move to approved table
            approved_table.put_item(
                Item={
                    'submission_id': submission_id,
                    'status': status,
                    'text': item.get('text', ''),
                    'image_key': item.get('image_key', ''),
                    'approved_at': timestamp,
                    'approved_by': 'admin',
                    'initially_ambiguous': True,
                    'ttl': int(datetime.now().timestamp()) + (86400 * 30 * 12)
                }
            )
        else:
            rejected_table.put_item(
                Item={
                    'submission_id': submission_id,
                    'status': status,
                    'rejected_at': timestamp,
                    'rejected_by': 'admin',
                    'initially_ambiguous': True,
                    'ttl': int(datetime.now().timestamp()) + (86400 * 7)
                }
            )
        
        # Update review table with final decision and resolution time
        review_table.update_item(
            Key={'submission_id': submission_id},
            UpdateExpression='SET #status = :status, resolved_at = :resolved_at',
            ExpressionAttributeNames={'#status': 'status'},
            ExpressionAttributeValues={
                ':status': status,
                ':resolved_at': timestamp
            }
        )
        
        return {
            'statusCode': 200,
            'headers': {
                    'Access-Control-Allow-Origin': '*',
                    'Access-Control-Allow-Methods': '*',
                    'Access-Control-Allow-Headers': '*'
                },
            'body': json.dumps({
                'submission_id': submission_id,
                'admin_decision': status,
                'resolved_at': timestamp
            })
        }
    
    except Exception as e:
        print(f"Admin decision error: {str(e)}")
        return {
            'statusCode': 500,
            'headers': {
                    'Access-Control-Allow-Origin': '*',
                    'Access-Control-Allow-Methods': '*',
                    'Access-Control-Allow-Headers': '*'
                },
            'body': json.dumps({'error': 'Internal server error'})
        }
