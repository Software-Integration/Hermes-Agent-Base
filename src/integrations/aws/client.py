from __future__ import annotations

from ...config import TenantConfig
from ..base import ProviderBase, ProviderError
from .auth import build_aws_secret
from .tools import descriptors

try:
    import boto3
except Exception:  # pragma: no cover
    boto3 = None


class AWSProvider(ProviderBase):
    name = "aws"

    def tool_descriptors(self, handler_factory):
        return descriptors(handler_factory)

    def execute(self, action: str, tenant: TenantConfig, arguments: dict) -> dict:
        if boto3 is None:
            return {"ok": False, "error_code": "aws_sdk_not_installed", "reason": "boto3 missing"}
        secret = build_aws_secret(tenant, self)
        region = self.get_config(tenant).region or secret.get("region") or "us-east-1"
        session = boto3.Session(
            aws_access_key_id=secret["aws_access_key_id"],
            aws_secret_access_key=secret["aws_secret_access_key"],
            aws_session_token=secret.get("aws_session_token"),
            region_name=region,
        )
        if action == "s3_put_object":
            client = session.client("s3")
            response = client.put_object(Bucket=arguments["bucket"], Key=arguments["key"], Body=arguments["body"].encode("utf-8"))
            return {"ok": True, "provider": self.name, "response": {"etag": response.get("ETag", "")}}
        if action == "sns_publish":
            client = session.client("sns")
            response = client.publish(TopicArn=arguments["topic_arn"], Message=arguments["message"])
            return {"ok": True, "provider": self.name, "response": {"message_id": response.get("MessageId", "")}}
        raise ProviderError(f"unknown action {action}")
