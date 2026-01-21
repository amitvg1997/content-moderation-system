import json
import boto3
import os

dynamodb = boto3.resource('dynamodb')

def lambda_handler(event, context):
    """
    GET /status/{submissionId}
    Returns current status: pending | approved | rejected | error
    """
    try:
        submission_id = event.get('pathParameters', {}).get('submissionId')
        
        if not submission_id:
            return {
                'statusCode': 400,
                'headers': {
                    'Access-Control-Allow-Origin': '*',
                    'Access-Control-Allow-Methods': '*',
                    'Access-Control-Allow-Headers': '*'
                },
                'body': json.dumps({'error': 'Missing submissionId'})
            }
        
        approved_table = dynamodb.Table(os.getenv('APPROVED_TABLE'))
        review_table = dynamodb.Table(os.getenv('REVIEW_TABLE'))
        rejected_table = dynamodb.Table(os.getenv('REJECTED_TABLE'))
        
        # Check approved table
        approved_response = approved_table.get_item(Key={'submission_id': submission_id})
        if 'Item' in approved_response:
            return {
                'statusCode': 200,
                'headers': {
                    'Access-Control-Allow-Origin': '*',
                    'Access-Control-Allow-Methods': '*',
                    'Access-Control-Allow-Headers': '*'
                },
                'body': json.dumps({
                    'submission_id': submission_id,
                    'status': 'approved',
                    'approved_at': approved_response['Item'].get('approved_at')
                })
            }
        
        # Check review table
        review_response = review_table.get_item(Key={'submission_id': submission_id})
        if 'Item' in review_response:
            item = review_response['Item']
            status = item.get('status', 'PENDING_REVIEW')
            
            if status == 'APPROVED':
                return {
                    'statusCode': 200,
                    'headers': {
                        'Access-Control-Allow-Origin': '*',
                        'Access-Control-Allow-Methods': '*',
                        'Access-Control-Allow-Headers': '*'
                    },
                    'body': json.dumps({
                        'submission_id': submission_id,
                        'status': 'approved',
                        'approved_at': item.get('created_at'),
                        'reviewed_by': 'admin'
                    })
                }
            elif status == 'REJECTED':
                return {
                    'statusCode': 200,
                    'headers': {
                        'Access-Control-Allow-Origin': '*',
                        'Access-Control-Allow-Methods': '*',
                        'Access-Control-Allow-Headers': '*'
                    },
                    'body': json.dumps({
                        'submission_id': submission_id,
                        'status': 'rejected',
                        'rejected_at': item.get('resolved_at')
                    })
                }
            else:  # PENDING_REVIEW
                return {
                    'statusCode': 200,
                    'headers': {
                        'Access-Control-Allow-Origin': '*',
                        'Access-Control-Allow-Methods': '*',
                        'Access-Control-Allow-Headers': '*'
                    },
                    'body': json.dumps({
                        'submission_id': submission_id,
                        'status': 'pending',
                        'created_at': item.get('created_at')
                    })
                }

        # Check rejected table
        rejected_response = rejected_table.get_item(Key={'submission_id': submission_id})
        if 'Item' in rejected_response:
            return {
                'statusCode': 200,
                'headers': {
                    'Access-Control-Allow-Origin': '*',
                    'Access-Control-Allow-Methods': '*',
                    'Access-Control-Allow-Headers': '*'
                },
                'body': json.dumps({
                    'submission_id': submission_id,
                    'status': 'rejected',
                    'rejected_at': rejected_response['Item'].get('rejected_at')
                    
                })
            }
            
        
        # Not found 
        return {
            'statusCode': 404,
            'headers': {
                    'Access-Control-Allow-Origin': '*',
                    'Access-Control-Allow-Methods': '*',
                    'Access-Control-Allow-Headers': '*'
                },
            'body': json.dumps({
                'submission_id': submission_id,
                'status': 'Not Found',
                'message': 'Please enter a valid submission id.'
            })
        }
    
    except Exception as e:
        print(f"Get status error: {str(e)}")
        return {
            'statusCode': 500,
            'headers': {
                    'Access-Control-Allow-Origin': '*',
                    'Access-Control-Allow-Methods': '*',
                    'Access-Control-Allow-Headers': '*'
                },
            'body': json.dumps({'error': 'Internal server error'})
        }
