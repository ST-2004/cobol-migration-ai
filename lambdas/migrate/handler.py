"""
Phase 2: migrate Lambda — chunked migration for industry-scale COBOL files.

Strategy:
  1. Split COBOL into DATA DIVISION + paragraph chunks (5 paragraphs each).
  2. Translate DATA DIVISION → Python classes/globals (Bedrock call 1).
  3. Translate each paragraph chunk → Python functions, with data classes as
     context so cross-references resolve correctly (Bedrock calls 2..N).
  4. Append entry-point guard and stream every token to the WebSocket as it
     arrives so the frontend terminal updates in real time.
"""
import json
import os
import re
import time
import boto3
from boto3.dynamodb.conditions import Key

JOBS_TABLE      = os.environ.get("JOBS_TABLE", "cobol-mig-dev-jobs")
FILES_BUCKET    = os.environ.get("FILES_BUCKET", "cobol-mig-dev-files")
WS_ENDPOINT     = os.environ.get("WS_ENDPOINT", "")
BEDROCK_MODEL_ID = os.environ.get("BEDROCK_MODEL_ID", "anthropic.claude-sonnet-4-5")

PARAGRAPHS_PER_CHUNK = 5  # tune: more = fewer calls but risks token limit
MAX_TOKENS = 8000          # safe headroom below the 10 000 hard cap


# ---------------------------------------------------------------------------
# COBOL splitting helpers
# ---------------------------------------------------------------------------

def _split_cobol(cobol_source: str):
    """
    Returns (data_section: str, para_chunks: list[str]).
    data_section  — everything up to and including 'PROCEDURE DIVISION.'
    para_chunks   — list of paragraph groups ready for translation
    """
    proc_match = re.search(
        r'(?im)^\s*PROCEDURE\s+DIVISION.*?$', cobol_source
    )
    if not proc_match:
        return cobol_source, []

    data_section  = cobol_source[:proc_match.end()]
    proc_body     = cobol_source[proc_match.end():]

    # Each COBOL paragraph header: identifier starting in area A (cols 8-11)
    # Pattern: line that starts with optional spaces then CAPS-WITH-HYPHENS.
    para_re = re.compile(
        r'(?m)^[ \t]{0,7}([A-Z][A-Z0-9\-]+)\.\s*$'
    )
    boundaries = [m.start() for m in para_re.finditer(proc_body)]

    if not boundaries:
        return data_section, [proc_body]

    paragraphs = []
    for i, start in enumerate(boundaries):
        end = boundaries[i + 1] if i + 1 < len(boundaries) else len(proc_body)
        paragraphs.append(proc_body[start:end].strip())

    chunks = [
        "\n\n".join(paragraphs[i: i + PARAGRAPHS_PER_CHUNK])
        for i in range(0, len(paragraphs), PARAGRAPHS_PER_CHUNK)
    ]
    return data_section, chunks


# ---------------------------------------------------------------------------
# Bedrock streaming helper
# ---------------------------------------------------------------------------

def _stream_bedrock(bedrock, system_prompt: str, user_msg: str,
                    ws_client, connection_id: str) -> str:
    """
    Calls converse_stream, pushes each token to WebSocket, returns full text.
    Retries up to 3x on throttling with exponential back-off.
    """
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
        except bedrock.exceptions.ThrottlingException as exc:
            last_exc = exc
            if attempt < 2:
                time.sleep(2 ** attempt * 2)
        except Exception as exc:
            last_exc = exc
            break
    raise last_exc


# ---------------------------------------------------------------------------
# Per-section system prompts
# ---------------------------------------------------------------------------

DATA_SYSTEM = """\
You are an expert COBOL-to-Python migration engine.
Translate ONLY the DATA DIVISION (WORKING-STORAGE and FILE SECTION records) to
idiomatic Python 3.12. Follow these rules exactly:

1. IMPORTS: Always emit these two lines at the very top, before anything else:
      from datetime import date
      from decimal import Decimal

2. FILE SECTION records (FD entries) → Python dataclasses.
   Use: from dataclasses import dataclass, field
   Name the class after the record name in PascalCase (e.g. LoanMasterRecord).
   After ALL dataclass definitions, emit one module-level instance per record:
      loan_master_record = LoanMasterRecord()
      payment_history_record = PaymentHistoryRecord()
   These instance names MUST be the snake_case version of the class name.
   PROCEDURE DIVISION code will access fields as: loan_master_record.lm_loan_id
   Never use flat globals like ws_loan_master_lm_loan_id for record fields.

3. WORKING-STORAGE 01-level groups:
   - If the group has only elementary items (no nested groups), emit each
     elementary item as a module-level scalar variable using the full
     qualified name with underscores: ws_group_name_field_name = <value>.
   - If the group has nested groups, use a dataclass for the inner group OR
     flatten to scalars consistently — do NOT mix access styles for the same
     record within a single 01-level group.
   - CRITICAL: Every variable used by PROCEDURE DIVISION must be defined here
     as a module-level name. Do not omit any field.

4. NAMING CONVENTION (critical — PROCEDURE DIVISION must use the same names):
   - WORKING-STORAGE scalars: ws_<group>_<field> all lowercase with underscores.
     Example: WS-SWITCHES/WS-END-OF-FILE → ws_switches_ws_end_of_file = ' '
     Example: WS-WORK-FIELDS/WS-ERROR-MSG → ws_work_fields_ws_error_msg = ''
     Example: WS-COUNTERS/WS-RECORDS-WRITTEN → ws_counters_ws_records_written = 0
   - File record fields: accessed via instance, e.g. loan_master_record.lm_loan_id
   - Never invent alternative names. Use only the derived names above.

5. 88-LEVEL CONDITIONS: Do NOT create variables for 88-level names.
   Add a comment mapping each 88-level name to its test:
      # END_OF_FILE:  ws_switches_ws_end_of_file == 'Y'
      # ERRORS_FOUND: ws_switches_ws_errors_found == 'Y'
      # RC_SUCCESS:   ws_work_fields_ws_return_code < 8

6. COMP-3 / COMP fields → Decimal or int as appropriate.
   PIC 9(n)V99 currency → Decimal.   PIC 9(n) integer → int.
   PIC X / PIC A → str.

7. Do NOT emit any function definitions.
8. Do NOT emit an if __name__ block.
9. Output ONLY valid Python — no explanations, no markdown fences.\
"""

PROC_SYSTEM = """\
You are an expert COBOL-to-Python migration engine.
You will be given (a) the already-translated Python data structures and
(b) a group of COBOL paragraphs to translate.
Translate ONLY the provided paragraphs to Python functions.
Follow these rules exactly — they prevent the most common migration bugs:

1. GLOBAL STATE: All WORKING-STORAGE variables are module-level globals.
   Every function that reads OR writes a module-level variable must declare it
   with `global` at the top of the function body. Only declare globals that
   the function actually reads or writes — do not over-declare.

2. RECORD ACCESS: FILE SECTION records are accessed via their module-level
   instance variable (e.g. loan_master_record.lm_loan_id).
   NEVER invent flat globals like ws_loan_master_lm_loan_id for record fields.
   The instance names are in the data structures given to you — use them exactly.

3. 88-LEVEL CONDITIONS: Never use the 88-level name as a Python identifier.
   Use the EXACT module-level variable names from the data structures. Examples:
     COBOL: IF END-OF-FILE          → Python: if ws_switches_ws_end_of_file == 'Y':
     COBOL: IF ERRORS-FOUND         → Python: if ws_switches_ws_errors_found == 'Y':
     COBOL: IF RC-SUCCESS           → Python: if ws_work_fields_ws_return_code < 8:
     COBOL: PERFORM X UNTIL END-OF-FILE → Python: while ws_switches_ws_end_of_file != 'Y': x()
   The 88-level comments in the data structures show the exact variable names to use.

4. RETURN CODES: rc=0 success, rc=4 warning (keep processing), rc=8 error (stop),
   rc=12 fatal. IF RC-SUCCESS or similar success check → `if ws_work_fields_ws_return_code < 8:`
   Never translate a success check as `== 0`.

5. EXIT PARAGRAPH: Translate `EXIT PARAGRAPH` as an early `return` statement only.
   Never use break, pass, or continue in place of EXIT PARAGRAPH.

6. CONSISTENT ACCESS: Access each variable the same way throughout all functions.
   If it's a WORKING-STORAGE scalar (module-level global), use it as a global
   in every function. If it's a FILE SECTION record field, use the instance
   attribute in every function. Never mix the two for the same underlying data item.

7. GL/ACCOUNTING FIELDS: When translating GL posting paragraphs, map each
   COBOL MOVE precisely:
     MOVE LM-LOAN-ID TO GL-JOURNAL-ID → ws_gl_work_gl_work_journal_id = loan_master_record.lm_loan_id
     MOVE LM-OUTSTANDING-BAL TO GL-DEBIT-AMOUNT → ws_gl_work_gl_work_debit_amount = loan_master_record.lm_outstanding_bal
   Never assign a balance field to a journal ID field or vice versa.

8. REPORT PARAGRAPHS: WRITE-REPORT-HEADER (or equivalent) must ONLY format and
   write the header line. It must NOT reset any accumulator variables
   (rpt_total_*, rpt_loans_processed, etc.). Accumulators are reset only in an
   initialisation paragraph (INITIALISE or OPEN-FILES equivalent).

9. CONDITIONAL TRIGGERS: Translate each IF condition using the exact COBOL variable
   it checks. Examples:
     IF LM-DAYS-PAST-DUE > 0 PERFORM POST-LATE-FEE → if loan_master_record.lm_days_past_due > 0: post_late_fee_gl()
   Never substitute a different variable (e.g. remaining balance) for the COBOL condition.

10. DUPLICATE FUNCTIONS: Never define the same function name twice in any chunk.
    If a paragraph appears in multiple chunks (due to splitting), translate it
    only in the chunk where it first appears.

11. Variable names must match the data structures EXACTLY. Do not invent names.
    Do NOT redefine any classes or module-level variables already in the data section.
12. Do NOT emit an if __name__ block.
13. Output ONLY the function definitions — no explanations, no markdown fences.\
"""

ENTRYPOINT_SYSTEM = """\
You are an expert COBOL-to-Python migration engine.
Given the complete translated Python module below (classes + functions),
output ONLY the 'if __name__ == "__main__":' block that calls the main
entry-point function (equivalent to MAIN-PROCESS or MAIN-PARA in the COBOL).
Output ONLY that block — nothing else.\
"""


# ---------------------------------------------------------------------------
# DynamoDB / WebSocket helpers
# ---------------------------------------------------------------------------

def _get_job(ddb, job_id, created_at):
    jobs_table = ddb.Table(JOBS_TABLE)
    if created_at:
        resp = jobs_table.get_item(Key={"job_id": job_id, "created_at": created_at})
        return resp.get("Item", {})
    resp = jobs_table.query(
        KeyConditionExpression=Key("job_id").eq(job_id),
        Limit=1,
    )
    items = resp.get("Items", [])
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


# ---------------------------------------------------------------------------
# Lambda entry point
# ---------------------------------------------------------------------------

def handler(event, _context):
    job_id       = event.get("job_id", "")
    created_at   = event.get("created_at", "")
    connection_id = event.get("connection_id", "")

    ddb = boto3.resource("dynamodb")
    job = _get_job(ddb, job_id, created_at)
    if not job:
        raise ValueError(f"Job not found: {job_id}")
    created_at = job.get("created_at", created_at)

    s3 = boto3.client("s3")
    cobol_obj    = s3.get_object(Bucket=FILES_BUCKET, Key=f"{job_id}/source.cbl")
    cobol_source = cobol_obj["Body"].read().decode("utf-8")

    ws_client = None
    if connection_id and WS_ENDPOINT:
        ws_client = boto3.client(
            "apigatewaymanagementapi",
            endpoint_url=WS_ENDPOINT,
        )

    bedrock = boto3.client(
        "bedrock-runtime",
        region_name=os.environ.get("AWS_REGION", "us-east-1"),
    )

    data_section, para_chunks = _split_cobol(cobol_source)
    total_chunks = 1 + len(para_chunks) + 1  # data + paragraphs + entrypoint

    # --- Chunk 1: DATA DIVISION → Python classes/globals ---
    _push_ws(ws_client, connection_id, {
        "progress": f"Translating data structures (1/{total_chunks})…"
    })
    python_classes = _stream_bedrock(
        bedrock, DATA_SYSTEM, data_section, ws_client, connection_id
    )
    python_code = python_classes.strip() + "\n\n"

    # --- Chunks 2..N: PROCEDURE DIVISION paragraph groups ---
    for idx, chunk in enumerate(para_chunks, start=2):
        _push_ws(ws_client, connection_id, {
            "progress": f"Translating paragraphs ({idx}/{total_chunks})…"
        })
        user_msg = (
            f"### Existing Python data structures ###\n{python_classes}\n\n"
            f"### COBOL paragraphs to translate ###\n{chunk}"
        )
        functions = _stream_bedrock(
            bedrock, PROC_SYSTEM, user_msg, ws_client, connection_id
        )
        python_code += functions.strip() + "\n\n"

    # --- Final chunk: entry-point guard ---
    _push_ws(ws_client, connection_id, {
        "progress": f"Generating entry point ({total_chunks}/{total_chunks})…"
    })
    entrypoint = _stream_bedrock(
        bedrock, ENTRYPOINT_SYSTEM, python_code, ws_client, connection_id
    )
    python_code += entrypoint.strip() + "\n"

    # --- Persist ---
    s3.put_object(
        Bucket=FILES_BUCKET,
        Key=f"{job_id}/output.py",
        Body=python_code.encode("utf-8"),
        ContentType="text/x-python",
    )

    ddb.Table(JOBS_TABLE).update_item(
        Key={"job_id": job_id, "created_at": created_at},
        UpdateExpression="SET #s = :s",
        ExpressionAttributeNames={"#s": "status"},
        ExpressionAttributeValues={":s": "migrated"},
    )

    _push_ws(ws_client, connection_id, {"done": True, "job_id": job_id})
    return {"job_id": job_id, "created_at": created_at, "status": "migrated"}
