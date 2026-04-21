from __future__ import annotations

from ...tools.tool_registry import ToolDescriptor
from .schemas import CLOUD_S3_PUT_OBJECT, CLOUD_SNS_PUBLISH


def descriptors(handler_factory):
    return [
        ToolDescriptor(
            name=CLOUD_S3_PUT_OBJECT,
            description="Put an object into S3",
            handler=handler_factory("aws", "s3_put_object"),
            capabilities=("cloud.aws.s3.write",),
            input_schema={"bucket": str, "key": str, "body": str},
            max_output_chars=4096,
        ),
        ToolDescriptor(
            name=CLOUD_SNS_PUBLISH,
            description="Publish to SNS",
            handler=handler_factory("aws", "sns_publish"),
            capabilities=("cloud.aws.sns.publish",),
            input_schema={"topic_arn": str, "message": str},
            max_output_chars=4096,
        ),
    ]

