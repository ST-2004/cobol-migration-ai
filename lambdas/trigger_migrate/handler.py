"""
Phase 2: trigger_migrate Lambda.
Called by POST /migrate HTTP API.
Looks up the WebSocket connectionId for this job, then starts a Step Functions
Express Workflow execution with { job_id, connection_id, created_at }.
Returns { execution_arn, job_id }.
"""
import json
import os
import boto3
from boto3.dynamodb.conditions import Key

JOBS_TABLE = os.environ.get("JOBS_TABLE", "cobol-mig-dev-jobs")
CONNECTIONS_TABLE = os.environ.get("CONNECTIONS_TABLE", "cobol-mig-dev-connections")
STATE_MACHINE_ARN = os.environ.get("STATE_MACHINE_ARN", "")

CORS_HEADERS = {
    "Content-Type": "application/json",
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Headers": "Content-Type,Authorization",
}


def _parse_body(event):
    body = event.get("body", "{}")
    if event.get("isBase64Encoded"):
        import base64
        body = base64.b64decode(body).decode("utf-8")
    if isinstance(body, str):
        body = json.loads(body or "{}")
    return body


def handler(event, context):
    try:
        body = _parse_body(event)
        job_id = body.get("job_id", "")
        created_at = body.get("created_at", "")

        if not job_id:
            return {
                "statusCode": 400,
                "headers": CORS_HEADERS,
                "body": json.dumps({"error": "job_id is required"}),
            }

        ddb = boto3.resource("dynamodb")

        # If created_at not provided, fetch it from the jobs table
        if not created_at:
            jobs_table = ddb.Table(JOBS_TABLE)
            response = jobs_table.query(
                KeyConditionExpression=Key("job_id").eq(job_id),
                Limit=1,
            )
            items = response.get("Items", [])
            if items:
                created_at = items[0].get("created_at", "")

        # Find the WebSocket connectionId for this job using GSI
        conn_table = ddb.Table(CONNECTIONS_TABLE)
        resp = conn_table.query(
            IndexName="job_id-index",
            KeyConditionExpression=Key("job_id").eq(job_id),
            Limit=1,
        )
        connection_id = ""
        items = resp.get("Items", [])
        if items:
            connection_id = items[0].get("connection_id", "")

        # Start Step Functions execution
        sfn = boto3.client("stepfunctions")
        execution_input = json.dumps({
            "job_id": job_id,
            "created_at": created_at,
            "connection_id": connection_id,
        })

        result = sfn.start_execution(
            stateMachineArn=STATE_MACHINE_ARN,
            input=execution_input,
        )

        return {
            "statusCode": 200,
            "headers": CORS_HEADERS,
            "body": json.dumps({
                "job_id": job_id,
                "execution_arn": result["executionArn"],
            }),
        }

    except Exception as e:
        return {
            "statusCode": 500,
            "headers": CORS_HEADERS,
            "body": json.dumps({"error": str(e)}),
        }
