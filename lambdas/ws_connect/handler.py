"""
Phase 2: WebSocket $connect handler.
Saves connectionId + job_id to the connections DynamoDB table.
"""
import json
import os
import time
import boto3

CONNECTIONS_TABLE = os.environ.get("CONNECTIONS_TABLE", "cobol-mig-dev-connections")
CONNECTION_TTL_SECONDS = 7200  # 2 hours


def handler(event, context):
    connection_id = event["requestContext"]["connectionId"]
    job_id = (event.get("queryStringParameters") or {}).get("job_id", "")

    ddb = boto3.resource("dynamodb")
    table = ddb.Table(CONNECTIONS_TABLE)

    table.put_item(
        Item={
            "connection_id": connection_id,
            "job_id": job_id,
            "expires_at": int(time.time()) + CONNECTION_TTL_SECONDS,
        }
    )

    return {"statusCode": 200, "body": "Connected"}
