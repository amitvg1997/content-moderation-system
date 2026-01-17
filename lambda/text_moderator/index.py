import json
import boto3
from datetime import datetime

comprehend = boto3.client('comprehend')

def lambda_handler(event, context):
    """
    Analyzes text sentiment using AWS Comprehend
    Returns: { type, decision, sentiment, confidence }
    decision = APPROVE | REJECT | AMBIGUOUS
    """
    try:
        # Extract from Step Functions input
        submission_id = event.get('submission_id')
        text = event.get('text', '').strip()
        
        if not text:
            return {
                'type': 'text',
                'submission_id': submission_id,
                'skipped': True
            }
        
        # Call Comprehend
        response = comprehend.detect_sentiment(
            Text=text,
            LanguageCode='en'
        )
        
        sentiment = response['Sentiment']
        confidence = response['SentimentScore']
        
        # Decision logic
        # APPROVE: Only POSITIVE sentiment with high confidence
        # REJECT: NEGATIVE with high confidence
        # AMBIGUOUS: NEUTRAL, MIXED, or low confidence
        
        if sentiment == 'POSITIVE' and confidence['Positive'] > 0.85:
            decision = 'APPROVE'
        elif sentiment == 'NEGATIVE' and confidence['Negative'] > 0.85:
            decision = 'REJECT'
        else:
            decision = 'AMBIGUOUS'
        
        result = {
            'type': 'text',
            'submission_id': submission_id,
            'decision': decision,
            'sentiment': sentiment,
            'confidence_scores': {
                'Positive': round(confidence['Positive'], 4),
                'Negative': round(confidence['Negative'], 4),
                'Neutral': round(confidence['Neutral'], 4),
                'Mixed': round(confidence['Mixed'], 4)
            },
            'max_confidence': round(max([confidence['Positive'], confidence['Negative'], confidence['Neutral'], confidence['Mixed']]), 4),
            'timestamp': datetime.now().isoformat()
        }
        
        print(f"Text moderation: {submission_id} - Decision: {decision}")
        return result
    
    except Exception as e:
        print(f"Text moderation error: {str(e)}")
        return {
            'type': 'text',
            'submission_id': event.get('submission_id'),
            'decision': 'AMBIGUOUS',
            'error': str(e)
        }
