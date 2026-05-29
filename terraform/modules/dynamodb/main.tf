resource "aws_dynamodb_table" "jobs" {
  name         = "${var.prefix}-jobs"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "job_id"
  range_key    = "created_at"

  attribute {
    name = "job_id"
    type = "S"
  }

  attribute {
    name = "created_at"
    type = "S"
  }

  ttl {
    attribute_name = "expires_at"
    enabled        = true
  }

  point_in_time_recovery {
    enabled = true
  }

  # KMS encryption added in Phase 6; SSE managed by AWS for now
  server_side_encryption {
    enabled = false
  }
}
