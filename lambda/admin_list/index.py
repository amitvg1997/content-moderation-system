import json
import boto3
import os
from decimal import Decimal

dynamodb = boto3.resource('dynamodb')
s3 = boto3.client('s3')

UPLOADS_BUCKET = os.getenv('UPLOADS_BUCKET')

def generate_presigned_url(image_key):
    """
    Generate a temporary pre-signed URL for the given S3 object
    """
    if not image_key:
        return None
    try:
        url = s3.generate_presigned_url(
            'get_object',
            Params={'Bucket': UPLOADS_BUCKET, 'Key': image_key},
            ExpiresIn=3600  # 1 hour expiry
        )
        return url
    except Exception as e:
        print(f"Error generating presigned URL for {image_key}: {str(e)}")
        return None

def lambda_handler(event, context):
    """
    GET /admin/pending
    Lists all content awaiting admin review, returning pre-signed image URLs
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
        
        # Replace image_key with presigned URL
        for item in items:
            if 'image_key' in item and item['image_key']:
                item['image_url'] = generate_presigned_url(item['image_key'])
            else:
                item['image_url'] = None

        return {
            'statusCode': 200,
            'headers': {
                'Access-Control-Allow-Origin': '*',
                'Access-Control-Allow-Methods': '*',
                'Access-Control-Allow-Headers': '*'
            },
            'body': json.dumps({
                'count': len(items),
                'items': items
            })
        }
    
    except Exception as e:
        print(f"Admin list error: {str(e)}")
        return {
            'statusCode': 500,
            'headers': {
                'Access-Control-Allow-Origin': '*',
                'Access-Control-Allow-Methods': '*',
                'Access-Control-Allow-Headers': '*'
            },
            'body': json.dumps({'error': 'Internal server error'})
        }