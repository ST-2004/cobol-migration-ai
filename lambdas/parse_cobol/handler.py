"""
Phase 1: COBOL Parser Lambda
Accepts multipart/form-data .cob/.cbl upload, parses paragraph graph,
stores to S3 and DynamoDB, returns graph JSON.
"""
import json
import re
import base64
import uuid
import os
from datetime import datetime, timezone, timedelta

import boto3

JOBS_TABLE = os.environ.get("JOBS_TABLE", "cobol-mig-dev-jobs")
FILES_BUCKET = os.environ.get("FILES_BUCKET", "cobol-mig-dev-files")

CORS_HEADERS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Headers": "Content-Type,Authorization",
    "Access-Control-Allow-Methods": "POST,OPTIONS",
    "Content-Type": "application/json",
}

PARAGRAPH_RE = re.compile(r"^[ ]{0,7}([A-Z0-9][A-Z0-9\-]{0,29})\.\s*$", re.MULTILINE)
PIC_RE = re.compile(
    r"^\s+(\d{2})\s+([A-Z0-9\-]+)\s+PIC\s+([^\s.]+)",
    re.MULTILINE | re.IGNORECASE,
)
PERFORM_RE = re.compile(
    r"^\s+PERFORM\s+([A-Z0-9\-]+)",
    re.MULTILINE | re.IGNORECASE,
)

RESERVED = {
    "IDENTIFICATION", "DIVISION", "PROGRAM-ID", "DATA", "WORKING-STORAGE",
    "SECTION", "PROCEDURE", "STOP", "RUN", "DISPLAY", "COMPUTE", "MOVE",
    "ADD", "SUBTRACT", "MULTIPLY", "DIVIDE", "IF", "ELSE", "END-IF",
    "EVALUATE", "WHEN", "OTHER", "END-EVALUATE", "PERFORM", "VARYING",
    "FROM", "BY", "UNTIL", "END-PERFORM", "CALL", "USING", "GOBACK",
    "EXIT", "CONTINUE", "INITIALIZE", "INSPECT", "STRING", "UNSTRING",
    "ACCEPT", "WRITE", "READ", "OPEN", "CLOSE", "REWRITE", "DELETE",
    "START", "RETURN", "SEARCH", "SET", "SORT", "MERGE", "RELEASE",
}


def parse_cobol(source: str) -> dict:
    paragraphs = []
    seen = set()
    for m in PARAGRAPH_RE.finditer(source):
        name = m.group(1).upper()
        if name not in RESERVED and name not in seen:
            paragraphs.append(name)
            seen.add(name)

    variables = []
    for m in PIC_RE.finditer(source):
        variables.append({
            "level": m.group(1),
            "name": m.group(2).upper(),
            "pic": m.group(3).upper(),
        })

    calls = []
    for m in PERFORM_RE.finditer(source):
        target = m.group(1).upper()
        if target not in RESERVED and target in seen:
            calls.append({"to": target})

    return {
        "paragraphs": paragraphs,
        "variables": variables,
        "calls": calls,
    }


def handler(event, context):
    if event.get("httpMethod") == "OPTIONS" or event.get("requestContext", {}).get("http", {}).get("method") == "OPTIONS":
        return {"statusCode": 200, "headers": CORS_HEADERS, "body": ""}

    try:
        body = event.get("body", "")
        if event.get("isBase64Encoded"):
            body = base64.b64decode(body)
        elif isinstance(body, str):
            body = body.encode()

        # Extract raw COBOL from multipart body
        cobol_source = _extract_file_from_multipart(body, event.get("headers", {}))

        graph = parse_cobol(cobol_source.decode("utf-8", errors="replace"))

        job_id = str(uuid.uuid4())
        created_at = datetime.now(timezone.utc).isoformat()
        expires_at = int((datetime.now(timezone.utc) + timedelta(days=30)).timestamp())

        s3 = boto3.client("s3")
        s3.put_object(
            Bucket=FILES_BUCKET,
            Key=f"{job_id}/source.cbl",
            Body=cobol_source,
            ContentType="text/plain",
        )

        ddb = boto3.resource("dynamodb")
        table = ddb.Table(JOBS_TABLE)
        table.put_item(Item={
            "job_id": job_id,
            "created_at": created_at,
            "status": "parsed",
            "graph": graph,
            "expires_at": expires_at,
        })

        return {
            "statusCode": 200,
            "headers": CORS_HEADERS,
            "body": json.dumps({"job_id": job_id, "created_at": created_at, "graph": graph}),
        }

    except Exception as exc:
        return {
            "statusCode": 500,
            "headers": CORS_HEADERS,
            "body": json.dumps({"error": str(exc)}),
        }


def _extract_file_from_multipart(body: bytes, headers: dict) -> bytes:
    content_type = headers.get("content-type", headers.get("Content-Type", ""))
    if "boundary=" not in content_type:
        return body

    boundary = content_type.split("boundary=")[-1].strip().encode()
    parts = body.split(b"--" + boundary)
    for part in parts[1:]:
        if b"filename=" in part:
            _, _, file_body = part.partition(b"\r\n\r\n")
            return file_body.rstrip(b"\r\n--")

    return body
