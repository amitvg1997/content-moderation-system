#!/usr/bin/env python3

from aws_cdk import App, Environment
from infrastructure.infrastructure_stack import ModerationSystemStack

app = App()

ModerationSystemStack(
    app, "ModerationSystem",
    env=Environment(
        account=app.node.try_get_context("account"),
        region="eu-west-1"  # Ireland
    )
)

app.synth()
