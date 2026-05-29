output "files_bucket_name" {
  value = aws_s3_bucket.files.bucket
}

output "files_bucket_arn" {
  value = aws_s3_bucket.files.arn
}
