from aws_cdk import (
    aws_s3 as s3,
    aws_lambda as lambda_,
    aws_apigateway as apigw,
    aws_dynamodb as dynamodb,
    aws_sns as sns,
    aws_iam as iam,
    aws_stepfunctions as sfn,
    aws_stepfunctions_tasks as sfn_tasks,
    aws_sns_subscriptions as subscriptions,
    Stack,
    RemovalPolicy,
    CfnOutput,
    Duration
)
from constructs import Construct
import json

class ModerationSystemStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs):
        super().__init__(scope, construct_id, **kwargs)

        region = "eu-west-1"
        admin_email = "amitvg1997@gmail.com"  

        # ============================================================================
        # PART 1: S3 BUCKETS
        # ============================================================================
        
        # Frontend bucket (user submission UI)
        frontend_bucket = s3.Bucket(
            self, "FrontendBucket",
            bucket_name=f"amit-moderation-frontend",
            block_public_access=s3.BlockPublicAccess(
                block_public_acls=False,
                block_public_policy=False,
                ignore_public_acls=False,
                restrict_public_buckets=False
            ),
            versioned=True,
            encryption=s3.BucketEncryption.S3_MANAGED,
            removal_policy=RemovalPolicy.RETAIN,
            website_index_document="index.html"
        )

        # Allow public read
        frontend_bucket.add_to_resource_policy(
            iam.PolicyStatement(
                actions=["s3:GetObject"],
                resources=[frontend_bucket.arn_for_objects("*")],
                principals=[iam.AnyPrincipal()]
            )
        )

        # Admin bucket (admin review UI)
        admin_bucket = s3.Bucket(
            self, "AdminBucket",
            bucket_name=f"amit-moderation-admin-frontend",
            block_public_access=s3.BlockPublicAccess(
                block_public_acls=False,
                block_public_policy=False,
                ignore_public_acls=False,
                restrict_public_buckets=False
            ),
            versioned=True,
            encryption=s3.BucketEncryption.S3_MANAGED,
            removal_policy=RemovalPolicy.RETAIN,
            website_index_document="admin.html"
        )
        

        admin_bucket.add_to_resource_policy(
            iam.PolicyStatement(
                actions=["s3:GetObject"],
                resources=[admin_bucket.arn_for_objects("*")],
                principals=[iam.AnyPrincipal()]
            )
        )

        # Frontend bucket policy (explicitly allow public read)
        frontend_policy = iam.PolicyStatement(
            actions=["s3:GetObject"],
            resources=[frontend_bucket.arn_for_objects("*")],
            principals=[iam.AnyPrincipal()]
        )
        frontend_bucket.add_to_resource_policy(frontend_policy)

        # Admin bucket policy
        admin_policy = iam.PolicyStatement(
            actions=["s3:GetObject"],
            resources=[admin_bucket.arn_for_objects("*")],
            principals=[iam.AnyPrincipal()]
        )
        admin_bucket.add_to_resource_policy(admin_policy)


        # Image uploads bucket (private, CORS enabled)
        uploads_bucket = s3.Bucket(
            self, "UploadsBucket",
            bucket_name=f"amit-moderation-uploads",
            block_public_access=s3.BlockPublicAccess(
                block_public_acls=True,
                block_public_policy=True,
                ignore_public_acls=True,
                restrict_public_buckets=True
            ),
            encryption=s3.BucketEncryption.S3_MANAGED,
            removal_policy=RemovalPolicy.RETAIN
        )

        uploads_bucket.add_cors_rule(
            allowed_methods=[s3.HttpMethods.PUT, s3.HttpMethods.POST],
            allowed_origins=["*"],
            allowed_headers=["*"]
        )

        # ============================================================================
        # PART 2: DYNAMODB TABLES
        # ============================================================================
        
        # Approved submissions
        approved_table = dynamodb.Table(
            self, "ApprovedTable",
            table_name="amit-moderation-approved",
            partition_key=dynamodb.Attribute(
                name="submission_id",
                type=dynamodb.AttributeType.STRING
            ),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            removal_policy=RemovalPolicy.RETAIN,
            stream=dynamodb.StreamViewType.NEW_IMAGE
        )

        # Review queue (admin intervention needed)
        review_table = dynamodb.Table(
            self, "ReviewTable",
            table_name="amit-moderation-review",
            partition_key=dynamodb.Attribute(
                name="submission_id",
                type=dynamodb.AttributeType.STRING
            ),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            removal_policy=RemovalPolicy.RETAIN,
            stream=dynamodb.StreamViewType.NEW_IMAGE
        )

        # GSI for listing pending reviews by status
        review_table.add_global_secondary_index(
            index_name="status-index",
            partition_key=dynamodb.Attribute(
                name="status",
                type=dynamodb.AttributeType.STRING
            ),
            sort_key=dynamodb.Attribute(
                name="created_at",
                type=dynamodb.AttributeType.STRING
            ),
            projection_type=dynamodb.ProjectionType.ALL
        )

        # ============================================================================
        # PART 3: SNS TOPICS
        # ============================================================================
        
        # Admin notification topic
        admin_notification_topic = sns.Topic(
            self, "AdminNotificationTopic",
            topic_name="amit-moderation-admin-notification"
        )

        # Subscribe admin email
        admin_notification_topic.add_subscription(
            subscriptions.EmailSubscription(admin_email)
        )

        # ============================================================================
        # PART 4: IAM ROLE FOR LAMBDAS
        # ============================================================================
        
        lambda_role = iam.Role(
            self, "LambdaExecutionRole",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com")
        )

        lambda_role.add_managed_policy(
            iam.ManagedPolicy.from_aws_managed_policy_name("service-role/AWSLambdaBasicExecutionRole")
        )

        # S3 permissions
        uploads_bucket.grant_read_write(lambda_role)
        frontend_bucket.grant_read(lambda_role)
        admin_bucket.grant_read(lambda_role)

        # DynamoDB permissions
        approved_table.grant_read_write_data(lambda_role)
        review_table.grant_read_write_data(lambda_role)

        # SNS permissions
        admin_notification_topic.grant_publish(lambda_role)

        # Rekognition & Comprehend permissions
        lambda_role.add_to_policy(iam.PolicyStatement(
            actions=[
                "rekognition:DetectModerationLabels",
                "comprehend:DetectSentiment"
            ],
            resources=["*"]
        ))

        # Step Functions permissions
        lambda_role.add_to_policy(iam.PolicyStatement(
            actions=[
                "states:StartExecution"
            ],
            resources=["*"]
        ))

        # ============================================================================
        # PART 5: LAMBDA FUNCTIONS
        # ============================================================================
        
        # Text Moderator
        text_moderator = lambda_.Function(
            self, "TextModerator",
            function_name="amit-moderation-text-moderator",
            runtime=lambda_.Runtime.PYTHON_3_11,
            handler="index.lambda_handler",
            code=lambda_.Code.from_asset("../lambda/text_moderator"),
            timeout=Duration.seconds(30),
            role=lambda_role
        )

        # Image Moderator
        image_moderator = lambda_.Function(
            self, "ImageModerator",
            function_name="amit-moderation-image-moderator",
            runtime=lambda_.Runtime.PYTHON_3_11,
            handler="index.lambda_handler",
            code=lambda_.Code.from_asset("../lambda/image_moderator"),
            timeout=Duration.seconds(30),
            environment={
                "UPLOADS_BUCKET": uploads_bucket.bucket_name
            },
            role=lambda_role
        )

        # Decision Handler
        decision_handler = lambda_.Function(
            self, "DecisionHandler",
            function_name="amit-moderation-decision-handler",
            runtime=lambda_.Runtime.PYTHON_3_11,
            handler="index.lambda_handler",
            code=lambda_.Code.from_asset("../lambda/decision_handler"),
            timeout=Duration.seconds(30),
            environment={
                "APPROVED_TABLE": approved_table.table_name,
                "REVIEW_TABLE": review_table.table_name,
                "ADMIN_NOTIFICATION_TOPIC": admin_notification_topic.topic_arn
            },
            role=lambda_role
        )

        # Submit Handler
        submit_handler = lambda_.Function(
            self, "SubmitHandler",
            function_name="amit-moderation-submit-handler",
            runtime=lambda_.Runtime.PYTHON_3_11,
            handler="index.lambda_handler",
            code=lambda_.Code.from_asset("../lambda/submit_handler"),
            timeout=Duration.seconds(30),
            environment={
                "STATE_MACHINE_ARN": "WILL_BE_SET_AFTER",  # Set after state machine creation
                "UPLOADS_BUCKET": uploads_bucket.bucket_name
            },
            role=lambda_role
        )

        # Get Status Handler
        get_status_handler = lambda_.Function(
            self, "GetStatusHandler",
            function_name="amit-moderation-getStatus-handler",
            runtime=lambda_.Runtime.PYTHON_3_11,
            handler="index.lambda_handler",
            code=lambda_.Code.from_asset("../lambda/get_status"),
            timeout=Duration.seconds(10),
            environment={
                "APPROVED_TABLE": approved_table.table_name,
                "REVIEW_TABLE": review_table.table_name
            },
            role=lambda_role
        )

        # Admin List Handler
        admin_list_handler = lambda_.Function(
            self, "AdminListHandler",
            function_name="amit-moderation-adminList-handler",
            runtime=lambda_.Runtime.PYTHON_3_11,
            handler="index.lambda_handler",
            code=lambda_.Code.from_asset("../lambda/admin_list"),
            timeout=Duration.seconds(10),
            environment={
                "REVIEW_TABLE": review_table.table_name
            },
            role=lambda_role
        )

        # Admin Decision Handler
        admin_decision_handler = lambda_.Function(
            self, "AdminDecisionHandler",
            function_name="amit-moderation-admin-decision-handler",
            runtime=lambda_.Runtime.PYTHON_3_11,
            handler="index.lambda_handler",
            code=lambda_.Code.from_asset("../lambda/admin_decision"),
            timeout=Duration.seconds(30),
            environment={
                "REVIEW_TABLE": review_table.table_name,
                "APPROVED_TABLE": approved_table.table_name
            },
            role=lambda_role
        )

        # ============================================================================
        # PART 6: STEP FUNCTIONS STATE MACHINE
        # ============================================================================
        
        # Create parallel tasks
        text_task = sfn_tasks.LambdaInvoke(
            self, "TextModerationTask",
            lambda_function=text_moderator,
            output_path="$.Payload"
        )

        image_task = sfn_tasks.LambdaInvoke(
            self, "ImageModerationTask",
            lambda_function=image_moderator,
            output_path="$.Payload"
        )

        # Parallel state
        parallel_state = sfn.Parallel(
            self, "ModerationParallel"
        )
        parallel_state.branch(text_task)
        parallel_state.branch(image_task)

        # Decision task
        decision_task = sfn_tasks.LambdaInvoke(
            self, "DecisionTask",
            lambda_function=decision_handler,
            payload=sfn.TaskInput.from_object({
                "moderation_results.$": "$",
                "submission_id.$": "$.submission_id",
                "text.$": "$.text",
                "image_key.$": "$.image_key"
            }),
            output_path="$.Payload"
        )

        # Build state machine
        definition = parallel_state.next(decision_task)

        state_machine = sfn.StateMachine(
            self, "ModerationStateMachine",
            definition=definition,
            timeout=Duration.minutes(5),
            state_machine_name="amit-moderation-state-machine"
        )

        # Update submit handler with state machine ARN
        submit_handler.add_environment("STATE_MACHINE_ARN", state_machine.state_machine_arn)

        # ============================================================================
        # PART 7: API GATEWAY
        # ============================================================================
        
        api = apigw.RestApi(
            self, "ModerationAPI",
            rest_api_name="amit-moderation-api",
            default_cors_preflight_options=apigw.CorsOptions(
                allow_origins=apigw.Cors.ALL_ORIGINS,
                allow_methods=apigw.Cors.ALL_METHODS,
                allow_headers=["Content-Type"]
            )
        )

        # CORS for 4XX/5XX errors
        api.add_gateway_response(
            "default-4XX",
            type=apigw.ResponseType.DEFAULT_4_XX,
            response_headers={
                "Access-Control-Allow-Origin": "'*'",
                "Access-Control-Allow-Headers": "'Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token'",
                "Access-Control-Allow-Methods": "'POST,OPTIONS'"
            })
        
        api.add_gateway_response(
            "default-5XX",
            type=apigw.ResponseType.DEFAULT_5_XX,
            response_headers={
                "Access-Control-Allow-Origin": "'*'",
                "Access-Control-Allow-Headers": "'Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token'",
                "Access-Control-Allow-Methods": "'POST,OPTIONS'"
            })


        # POST /submit
        submit_resource = api.root.add_resource("submit")
        submit_resource.add_method(
            "POST",
            apigw.LambdaIntegration(submit_handler)
        )

        # GET /status/{submissionId}
        status_resource = api.root.add_resource("status")
        status_id_resource = status_resource.add_resource("{submissionId}")
        status_id_resource.add_method(
            "GET",
            apigw.LambdaIntegration(get_status_handler)
        )

        # GET /admin/pending
        admin_resource = api.root.add_resource("admin")
        admin_pending_resource = admin_resource.add_resource("pending")
        admin_pending_resource.add_method(
            "GET",
            apigw.LambdaIntegration(admin_list_handler)
        )

        # POST /admin/decision
        admin_decision_resource = admin_resource.add_resource("decision")
        admin_decision_resource.add_method(
            "POST",
            apigw.LambdaIntegration(admin_decision_handler)
        )

        # ============================================================================
        # PART 8: OUTPUTS
        # ============================================================================
        
        CfnOutput(
            self, "FrontendBucketName",
            value=frontend_bucket.bucket_name,
            description="S3 bucket for user frontend"
        )

        CfnOutput(
            self, "AdminBucketName",
            value=admin_bucket.bucket_name,
            description="S3 bucket for admin frontend"
        )

        CfnOutput(
            self, "APIEndpoint",
            value=api.url,
            description="API Gateway endpoint"
        )

        CfnOutput(
            self, "ApprovedTableName",
            value=approved_table.table_name,
            description="DynamoDB approved submissions table"
        )

        CfnOutput(
            self, "ReviewTableName",
            value=review_table.table_name,
            description="DynamoDB review queue table"
        )

        CfnOutput(
            self, "StateMachineArn",
            value=state_machine.state_machine_arn,
            description="Step Functions state machine ARN"
        )
