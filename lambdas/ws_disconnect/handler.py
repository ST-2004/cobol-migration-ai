"""
Phase 2: WebSocket $disconnect handler.
Removes connectionId from the connections DynamoDB table.
"""
import os
import boto3

CONNECTIONS_TABLE = os.environ.get("CONNECTIONS_TABLE", "cobol-mig-dev-connections")


def handler(event, context):
    connection_id = event["requestContext"]["connectionId"]

    ddb = boto3.resource("dynamodb")
    table = ddb.Table(CONNECTIONS_TABLE)
    table.delete_item(Key={"connection_id": connection_id})

    return {"statusCode": 200, "body": "Disconnected"}
