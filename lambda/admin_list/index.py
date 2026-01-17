import json
import boto3
import os
from decimal import Decimal

dynamodb = boto3.resource('dynamodb')

def lambda_handler(event, context):
    """
    GET /admin/pending
    Lists all content awaiting admin review
    """
    try:
        review_table = dynamodb.Table(os.getenv('REVIEW_TABLE'))
        
        # Query using GSI for pending reviews
        response = review_table.query(
            IndexName='status-index',
            KeyConditionExpression='#status = :status',
            ExpressionAttributeNames={'#status': 'status'},
            ExpressionAttributeValues={':status': 'PENDING_REVIEW'},
            ScanIndexForward=False  # Most recent first
        )
        
        items = response.get('Items', [])
        
        # Convert Decimal to float for JSON serialization
        def convert_decimals(obj):
            if isinstance(obj, Decimal):
                return float(obj)
            elif isinstance(obj, dict):
                return {k: convert_decimals(v) for k, v in obj.items()}
            elif isinstance(obj, list):
                return [convert_decimals(v) for v in obj]
            return obj
        
        items = convert_decimals(items)
        
        return {
            'statusCode': 200,
            'body': json.dumps({
                'count': len(items),
                'items': items
            })
        }
    
    except Exception as e:
        print(f"Admin list error: {str(e)}")
        return {
            'statusCode': 500,
            'body': json.dumps({'error': 'Internal server error'})
        }
