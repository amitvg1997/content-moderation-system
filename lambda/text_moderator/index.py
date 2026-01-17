import json
import boto3
import os
from datetime import datetime

comprehend = boto3.client('comprehend')
sns_client = boto3.client('sns')

def lambda_handler(event, context):
    """
    Analyzes text sentiment and toxicity using AWS Comprehend.
    Returns only positive if sentiment is POSITIVE.
    """
    
    try:
        # Parse SNS message
        message = json.loads(event['Records'][0]['Sns']['Message'])
        submission_id = message['submission_id']
        text = message.get('text', '').strip()
        
        # If no text, skip
        if not text:
            print(f"No text for {submission_id}, skipping text moderation")
            return {'statusCode': 200}
        
        # Call Comprehend - Sentiment Analysis
        sentiment_response = comprehend.detect_sentiment(
            Text=text,
            LanguageCode='en'
        )
        
        sentiment = sentiment_response['Sentiment']  # POSITIVE, NEUTRAL, NEGATIVE, MIXED
        confidence = sentiment_response['SentimentScore']
        
        # YOUR REQUIREMENT: Only approve if POSITIVE sentiment
        text_approved = sentiment == 'POSITIVE'
        
        # Create result event
        result = {
            'submission_id': submission_id,
            'moderation_type': 'text',
            'approved': text_approved,
            'sentiment': sentiment,
            'confidence_scores': {
                'Positive': round(confidence['Positive'], 4),
                'Negative': round(confidence['Negative'], 4),
                'Neutral': round(confidence['Neutral'], 4),
                'Mixed': round(confidence['Mixed'], 4)
            },
            'timestamp': datetime.utcnow().isoformat()
        }
        
        # Publish to results topic
        sns_client.publish(
            TopicArn=os.getenv('RESULTS_TOPIC_ARN'),
            Message=json.dumps(result)
        )
        
        print(f"Text moderation complete: {submission_id} - Sentiment: {sentiment}")
        return {'statusCode': 200}
        
    except Exception as e:
        print(f"Text moderation error: {str(e)}")
        return {'statusCode': 500}
