from aws_cdk import (
    aws_s3 as s3,
    aws_lambda as lambda_,
    aws_apigateway as apigw,
    aws_dynamodb as dynamodb,
    aws_sns as sns,
    aws_iam as iam,
    App,
    RemovalPolicy,
    Stack,
    Duration,
    CfnOutput
)
from constructs import Construct
import os

class ModerationSystemStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs):
        super().__init__(scope, construct_id, **kwargs)

        # Configuration
        region = "eu-west-1"  # Ireland
        
        # ============================================================================
        # PART 1: S3 BUCKET FOR FRONTEND & IMAGE UPLOADS
        # ============================================================================
        
        # Frontend bucket (static website)
        frontend_bucket = s3.Bucket(
            self, "FrontendBucket",
            bucket_name="amit-content-moderation-frontend",
            block_public_access=s3.BlockPublicAccess(
                block_public_acls=False,
                block_public_policy=False,
                ignore_public_acls=False,
                restrict_public_buckets=False
            ),
            versioned=True,
            encryption=s3.BucketEncryption.S3_MANAGED,
            removal_policy=RemovalPolicy.RETAIN  
        )

        # Enable static website hosting
        frontend_bucket.add_to_resource_policy(
            iam.PolicyStatement(
                actions=["s3:GetObject"],
                resources=[frontend_bucket.arn_for_objects("*")],
                principals=[iam.AnyPrincipal()]
            )
        )

        # Image uploads bucket (CORS enabled for browser uploads)
        uploads_bucket = s3.Bucket(
            self, "UploadsBucket",
            bucket_name="amit-content-moderation-uploads",
            block_public_access=s3.BlockPublicAccess(
                block_public_acls=True,
                block_public_policy=True,
                ignore_public_acls=True,
                restrict_public_buckets=True
            ),
            encryption=s3.BucketEncryption.S3_MANAGED,
            removal_policy=RemovalPolicy.RETAIN
        )

        # CORS policy for uploads (allow browser to upload)
        uploads_bucket.add_cors_rule(
            allowed_methods=[s3.HttpMethods.PUT, s3.HttpMethods.POST],
            allowed_origins=["*"],
            allowed_headers=["*"]
        )

        # ============================================================================
        # PART 2: DYNAMODB TABLE
        # ============================================================================
        
        moderation_table = dynamodb.Table(
            self, "ModerationTable",
            table_name="amit-content-moderation-results",
            partition_key=dynamodb.Attribute(
                name="submission_id",
                type=dynamodb.AttributeType.STRING
            ),
            sort_key=dynamodb.Attribute(
                name="timestamp",
                type=dynamodb.AttributeType.STRING
            ),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,  
            removal_policy=RemovalPolicy.RETAIN,
            stream=dynamodb.StreamViewType.NEW_IMAGE
        )

        # ============================================================================
        # PART 3: SNS TOPICS (Event pub/sub)
        # ============================================================================
        
        # Topic 1: Submit event (image + text)
        submission_topic = sns.Topic(
            self, "SubmissionTopic",
            topic_name="amit-content-moderation-submission"
        )

        # Topic 2: Results (after moderation)
        results_topic = sns.Topic(
            self, "ResultsTopic",
            topic_name="amit-content-moderation-results"
        )

        # ============================================================================
        # PART 4: LAMBDA FUNCTIONS
        # ============================================================================
        
        # Create Lambda execution role with specific permissions
        lambda_role = iam.Role(
            self, "LambdaExecutionRole",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com")
        )

        # Add permissions
        lambda_role.add_managed_policy(
            iam.ManagedPolicy.from_aws_managed_policy_name("service-role/AWSLambdaBasicExecutionRole")
        )
        uploads_bucket.grant_read_write(lambda_role)
        moderation_table.grant_read_write_data(lambda_role)
        submission_topic.grant_publish(lambda_role)
        results_topic.grant_publish(lambda_role)

        # Add explicit permissions for Rekognition & Comprehend
        lambda_role.add_to_policy(iam.PolicyStatement(
            actions=[
                "rekognition:DetectModerationLabels",
                "comprehend:DetectSentiment",
                "comprehend:DetectToxicity"
            ],
            resources=["*"]  # These services don't support resource-based policies
        ))

        # Lambda 1: Main Handler (receives submission, coordinates)
        main_handler = lambda_.Function(
            self, "MainHandler",
            runtime=lambda_.Runtime.PYTHON_3_11,
            function_name="amit-content-moderation-main-handler",
            handler="index.lambda_handler",
            code=lambda_.Code.from_asset("lambda/main_handler"),
            timeout=Duration.seconds(30),
            environment={
                "SUBMISSION_TOPIC_ARN": submission_topic.topic_arn,
                "RESULTS_TOPIC_ARN": results_topic.topic_arn,
                "UPLOADS_BUCKET": uploads_bucket.bucket_name
            },
            role=lambda_role
        )

        # Lambda 2: Image Moderation (Rekognition)
        image_moderator = lambda_.Function(
            self, "ImageModerator",
            runtime=lambda_.Runtime.PYTHON_3_11,
            function_name="amit-content-moderation-image-moderator",
            handler="index.lambda_handler",
            code=lambda_.Code.from_asset("lambda/image_moderator"),
            timeout=Duration.seconds(30),
            environment={
                "UPLOADS_BUCKET": uploads_bucket.bucket_name,
                "RESULTS_TOPIC_ARN": results_topic.topic_arn
            },
            role=lambda_role
        )

        # Lambda 3: Text Moderation (Comprehend)
        text_moderator = lambda_.Function(
            self, "TextModerator",
            runtime=lambda_.Runtime.PYTHON_3_11,
            function_name="amit-content-moderation-text-moderator",
            handler="index.lambda_handler",
            code=lambda_.Code.from_asset("lambda/text_moderator"),
            timeout=Duration.seconds(30),
            environment={
                "RESULTS_TOPIC_ARN": results_topic.topic_arn
            },
            role=lambda_role
        )

        # Lambda 4: Decision (decides if save to DB)
        decision_handler = lambda_.Function(
            self, "DecisionHandler",
            runtime=lambda_.Runtime.PYTHON_3_11,
            function_name="amit-content-moderation-decision-handler",
            handler="index.lambda_handler",
            code=lambda_.Code.from_asset("lambda/decision_handler"),
            timeout=Duration.seconds(30),
            environment={
                "TABLE_NAME": moderation_table.table_name
            },
            role=lambda_role
        )

        # ============================================================================
        # PART 5: SNS SUBSCRIPTIONS (Wire them up)
        # ============================================================================
        
        # submission_topic → triggers image_moderator AND text_moderator (fan-out)
        submission_topic.add_subscription(
            sns.LambdaSubscription(image_moderator)
        )
        submission_topic.add_subscription(
            sns.LambdaSubscription(text_moderator)
        )

        # results_topic → triggers decision_handler
        results_topic.add_subscription(
            sns.LambdaSubscription(decision_handler)
        )

        # ============================================================================
        # PART 6: API GATEWAY (HTTP endpoint)
        # ============================================================================
        
        api = apigw.RestApi(
            self, "ModerationAPI",
            rest_api_name="amit-content-moderation-api",
            description="Content Media Moderation API"
        )

        # POST /moderate endpoint
        moderate_resource = api.root.add_resource("moderate")
        moderate_resource.add_method(
            "POST",
            apigw.LambdaIntegration(main_handler),
            request_parameters={
                "method.request.header.Content-Type": True
            }
        )

        # ============================================================================
        # PART 7: OUTPUTS
        # ============================================================================
        
        CfnOutput(
            self, "FrontendBucketName",
            value=frontend_bucket.bucket_name,
            description="S3 bucket for static frontend hosting"
        )

        CfnOutput(
            self, "UploadsBucketName",
            value=uploads_bucket.bucket_name,
            description="S3 bucket for image uploads"
        )

        CfnOutput(
            self, "APIEndpoint",
            value=api.url,
            description="API Gateway endpoint for submissions"
        )

        CfnOutput(
            self, "DynamoDBTableName",
            value=moderation_table.table_name,
            description="DynamoDB table for results"
        )
