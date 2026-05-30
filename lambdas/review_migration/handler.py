"""
review_migration Lambda — Phase 2 (post-migrate).

Makes a single Bedrock call that sees BOTH the original COBOL and the
generated Python side-by-side, then fixes a targeted set of known
COBOL→Python translation bugs that chunked generation cannot catch:

  1. Missing `global` declarations for module-level assignments
  2. 88-level condition names used as Python identifiers
  3. Duplicate function definitions
  4. Missing imports (datetime, decimal)
  5. Wrong rc_success threshold (== 0 should be < 8)
  6. EXIT PARAGRAPH translated incorrectly
  7. Inconsistent use of globals vs parameters for the same variable

Input (from Step Functions):
  { job_id, created_at, connection_id }

Output:
  { job_id, created_at, status: "reviewed" }

Side effects:
  - Overwrites <job_id>/output.py in S3 with the reviewed version
  - Updates DynamoDB status to "reviewed"
  - Streams progress tokens to WebSocket if connection_id is present
"""

import json
import os
import time
import boto3
from boto3.dynamodb.conditions import Key

JOBS_TABLE       = os.environ.get("JOBS_TABLE", "cobol-mig-dev-jobs")
FILES_BUCKET     = os.environ.get("FILES_BUCKET", "cobol-mig-dev-files")
WS_ENDPOINT      = os.environ.get("WS_ENDPOINT", "")
BEDROCK_MODEL_ID = os.environ.get("BEDROCK_MODEL_ID", "anthropic.claude-sonnet-4-5")

MAX_TOKENS = 8000

REVIEW_SYSTEM = """\
You are a COBOL-to-Python migration auditor and bug-fixer.
You will be given the original COBOL source and the generated Python code.

Find and fix ONLY the following bug categories — do not refactor anything else:

1. MISSING GLOBAL DECLARATIONS
   Any function that assigns to a module-level variable must have `global <name>`
   at the top. Scan every assignment statement. If the variable exists at module
   level and there is no `global` declaration in that function, add it.
   ALSO: Remove spurious `global` declarations for variables a function never
   reads or writes (over-declared globals pollute scope).

2. 88-LEVEL CONDITIONS USED AS IDENTIFIERS
   88-level condition names (e.g. END_OF_FILE, RC_SUCCESS, ERRORS_FOUND) are not
   valid Python variables. Replace every use with the correct test on the underlying
   module-level variable. Rules:
     - Flag that checks 'Y' → test flag_variable == 'Y'
     - Return-code success → if ws_work_fields_ws_return_code < 8:  (NOT == 0)
     - String comparison → test the underlying str variable directly

3. DUPLICATE FUNCTION DEFINITIONS
   Keep only the LAST (most complete) definition of any function defined more than
   once. Remove all earlier placeholder definitions entirely.

4. MISSING IMPORTS
   Ensure `from datetime import date`, `from decimal import Decimal`, and
   `from dataclasses import dataclass, field` are present at the top.

5. WRONG RETURN CODE THRESHOLD
   `if <rc_var> == 0:` as a success/continue test must become `if <rc_var> < 8:`
   because COBOL rc=4 is a warning that must not stop processing.

6. RECORD FIELD ACCESS INCONSISTENCY
   FILE SECTION record fields must always be accessed as instance attributes:
   loan_master_record.lm_loan_id — NEVER as flat globals like ws_loan_master_lm_loan_id.
   If flat globals were invented for record fields, replace all uses with the
   correct instance.field access and remove the invented globals.

7. UNDEFINED VARIABLE REFERENCES
   Scan every function for variables that are used but not defined at module level
   and not declared as `global`. Cross-reference against the COBOL DATA DIVISION
   to find the correct module-level name and substitute it.
   Common pattern: a function uses bare `lm_loan_id` but the correct name is
   `loan_master_record.lm_loan_id` — fix all such cases.

8. GL / ACCOUNTING FIELD MAPPING ERRORS
   In GL posting functions, verify each MOVE translates correctly:
     MOVE LM-LOAN-ID TO GL-JOURNAL-ID → journal_id variable = loan_master_record.lm_loan_id
     MOVE LM-OUTSTANDING-BAL TO GL-DEBIT-AMOUNT → debit_amount variable = outstanding_bal field
   Fix any assignment where a balance/amount value was assigned to an ID field or
   vice versa.

9. REPORT HEADER RESETS ACCUMULATORS (WRONG)
   write_report_header (or equivalent) must ONLY format/write the header line.
   It must NOT zero out any rpt_total_*, rpt_loans_processed, or other accumulator
   variables. If it does, remove those reset assignments.

10. CONDITIONAL TRIGGER VARIABLES
    Verify that each if-condition uses the correct COBOL variable as specified in
    the COBOL source. For example:
      - Late fee trigger: IF LM-DAYS-PAST-DUE > 0 → if loan_master_record.lm_days_past_due > 0:
      - Do NOT substitute a balance or other field for a days-past-due condition.

11. PARAMETER / GLOBAL INCONSISTENCY
    If a variable is accessed as a global in some functions but passed as a
    parameter in others for the same WORKING-STORAGE item, standardise to global
    access and remove the redundant parameters.

12. BROKEN VARIABLE NAME LINES
    Fix any line where two variable names were merged into one assignment statement
    (e.g. `ws_foo =_bar = ''`). Split into two correct assignments.

Output ONLY the corrected Python code. No explanations, no markdown fences.\
"""


def _get_job(ddb, job_id, created_at):
    table = ddb.Table(JOBS_TABLE)
    if created_at:
        return table.get_item(Key={"job_id": job_id, "created_at": created_at}).get("Item", {})
    items = table.query(
        KeyConditionExpression=Key("job_id").eq(job_id), Limit=1
    ).get("Items", [])
    return items[0] if items else {}


def _push_ws(ws_client, connection_id, data: dict):
    if not ws_client or not connection_id:
        return
    try:
        ws_client.post_to_connection(
            ConnectionId=connection_id,
            Data=json.dumps(data).encode("utf-8"),
        )
    except Exception:
        pass


def _stream_bedrock(bedrock, system_prompt: str, user_msg: str,
                    ws_client, connection_id: str) -> str:
    last_exc = None
    for attempt in range(3):
        try:
            result = ""
            response = bedrock.converse_stream(
                modelId=BEDROCK_MODEL_ID,
                system=[{"text": system_prompt}],
                messages=[{"role": "user", "content": [{"text": user_msg}]}],
                inferenceConfig={"maxTokens": MAX_TOKENS, "temperature": 0.1},
            )
            for chunk in response["stream"]:
                if "contentBlockDelta" in chunk:
                    token = chunk["contentBlockDelta"]["delta"].get("text", "")
                    if token:
                        result += token
                        _push_ws(ws_client, connection_id, {"token": token})
            return result
        except Exception as exc:
            last_exc = exc
            if attempt < 2:
                time.sleep(2 ** attempt * 2)
    raise last_exc


def handler(event, _context):
    job_id        = event.get("job_id", "")
    created_at    = event.get("created_at", "")
    connection_id = event.get("connection_id", "")

    ddb = boto3.resource("dynamodb")
    job = _get_job(ddb, job_id, created_at)
    if not job:
        raise ValueError(f"Job not found: {job_id}")
    created_at = job.get("created_at", created_at)

    s3 = boto3.client("s3")

    cobol_source = s3.get_object(
        Bucket=FILES_BUCKET, Key=f"{job_id}/source.cbl"
    )["Body"].read().decode("utf-8")

    python_code = s3.get_object(
        Bucket=FILES_BUCKET, Key=f"{job_id}/output.py"
    )["Body"].read().decode("utf-8")

    ws_client = None
    if connection_id and WS_ENDPOINT:
        ws_client = boto3.client(
            "apigatewaymanagementapi", endpoint_url=WS_ENDPOINT
        )

    bedrock = boto3.client(
        "bedrock-runtime",
        region_name=os.environ.get("AWS_REGION", "us-east-1"),
    )

    _push_ws(ws_client, connection_id, {"progress": "Reviewing and fixing migration…"})

    user_msg = (
        "### ORIGINAL COBOL SOURCE ###\n"
        f"{cobol_source}\n\n"
        "### GENERATED PYTHON CODE (needs review) ###\n"
        f"{python_code}"
    )

    reviewed_code = _stream_bedrock(
        bedrock, REVIEW_SYSTEM, user_msg, ws_client, connection_id
    )

    # Strip markdown fences if the model wrapped the output anyway
    reviewed_code = _strip_fences(reviewed_code)

    s3.put_object(
        Bucket=FILES_BUCKET,
        Key=f"{job_id}/output.py",
        Body=reviewed_code.encode("utf-8"),
        ContentType="text/x-python",
    )

    ddb.Table(JOBS_TABLE).update_item(
        Key={"job_id": job_id, "created_at": created_at},
        UpdateExpression="SET #s = :s",
        ExpressionAttributeNames={"#s": "status"},
        ExpressionAttributeValues={":s": "reviewed"},
    )

    _push_ws(ws_client, connection_id, {"progress": "Review complete — code fixed"})
    return {"job_id": job_id, "created_at": created_at, "status": "reviewed"}


def _strip_fences(code: str) -> str:
    """Remove ```python ... ``` or ``` ... ``` wrappers if present."""
    lines = code.strip().splitlines()
    if lines and lines[0].startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].strip() == "```":
        lines = lines[:-1]
    return "\n".join(lines) + "\n"
