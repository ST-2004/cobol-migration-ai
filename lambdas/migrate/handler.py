"""
Phase 2: Migration Lambda
Reads COBOL from S3, calls Bedrock (Claude Sonnet) streaming,
pushes tokens over WebSocket, saves Python output.
"""
import json
import os
import time
import boto3

JOBS_TABLE = os.environ.get("JOBS_TABLE", "cobol-mig-dev-jobs")
FILES_BUCKET = os.environ.get("FILES_BUCKET", "cobol-mig-dev-files")
WS_ENDPOINT = os.environ.get("WS_ENDPOINT", "")
BEDROCK_MODEL_ID = os.environ.get("BEDROCK_MODEL_ID", "anthropic.claude-sonnet-4-5")
CONNECTIONS_TABLE = os.environ.get("CONNECTIONS_TABLE", "cobol-mig-dev-connections")


def handler(event, context):
    job_id = event.get("job_id")
    connection_id = event.get("connection_id", "")

    ddb = boto3.resource("dynamodb")
    jobs_table = ddb.Table(JOBS_TABLE)

    item = jobs_table.get_item(Key={"job_id": job_id, "created_at": event.get("created_at", "")})
    job = item.get("Item", {})

    s3 = boto3.client("s3")
    cobol_obj = s3.get_object(Bucket=FILES_BUCKET, Key=f"{job_id}/source.cbl")
    cobol_source = cobol_obj["Body"].read().decode("utf-8")

    bedrock = boto3.client("bedrock-runtime", region_name=os.environ.get("AWS_REGION", "us-east-1"))

    system_prompt = (
        "You are an expert COBOL-to-Python migration engine. "
        "Convert the provided COBOL program to idiomatic Python 3.12. "
        "Preserve all business logic exactly. Map each COBOL paragraph to a Python function. "
        "Map WORKING-STORAGE variables to Python variables or dataclasses. "
        "Output ONLY valid Python code — no explanations, no markdown fences."
    )

    python_code = ""
    for attempt in range(3):
        try:
            response = bedrock.converse_stream(
                modelId=BEDROCK_MODEL_ID,
                system=[{"text": system_prompt}],
                messages=[{"role": "user", "content": [{"text": cobol_source}]}],
                inferenceConfig={"maxTokens": 4096, "temperature": 0.1},
            )

            ws_client = None
            if connection_id and WS_ENDPOINT:
                ws_client = boto3.client(
                    "apigatewaymanagementapi",
                    endpoint_url=WS_ENDPOINT,
                )

            for chunk in response["stream"]:
                if "contentBlockDelta" in chunk:
                    token = chunk["contentBlockDelta"]["delta"].get("text", "")
                    python_code += token
                    if ws_client and token:
                        try:
                            ws_client.post_to_connection(
                                ConnectionId=connection_id,
                                Data=json.dumps({"token": token}).encode(),
                            )
                        except Exception:
                            pass
            break
        except bedrock.exceptions.ThrottlingException:
            if attempt == 2:
                raise
            time.sleep(2 ** attempt)

    s3.put_object(
        Bucket=FILES_BUCKET,
        Key=f"{job_id}/output.py",
        Body=python_code.encode("utf-8"),
        ContentType="text/x-python",
    )

    jobs_table.update_item(
        Key={"job_id": job_id, "created_at": job.get("created_at", "")},
        UpdateExpression="SET #s = :s, python_code = :c",
        ExpressionAttributeNames={"#s": "status"},
        ExpressionAttributeValues={":s": "migrated", ":c": python_code},
    )

    if connection_id and WS_ENDPOINT:
        try:
            ws_client.post_to_connection(
                ConnectionId=connection_id,
                Data=json.dumps({"done": True, "job_id": job_id}).encode(),
            )
        except Exception:
            pass

    return {"job_id": job_id, "status": "migrated"}
