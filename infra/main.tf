terraform {
  required_version = ">= 1.10"
  required_providers {
    aws = { source = "hashicorp/aws", version = "~> 6.69" }
  }
  backend "s3" {
    bucket       = "sdlc-lab-tfstate-992382408037"
    key          = "apps/dogs-app/dev/terraform.tfstate"
    region       = "eu-north-1"
    use_lockfile = true
  }
}

provider "aws" {
  region              = "eu-north-1"
  allowed_account_ids = ["992382408037"]
  default_tags {
    tags = { project = "sdlc-lab" }
  }
}

locals {
  env      = "dev"
  name     = "sdlc-lab-app-dogs-api-${local.env}"
  bucket   = "sdlc-lab-app-dogs-${local.env}-992382408037"
  boundary = "arn:aws:iam::992382408037:policy/sdlc-lab-boundary"
}

# --- Images: private bucket, served via short-lived presigned URLs -----------

resource "aws_s3_bucket" "images" {
  bucket        = local.bucket
  force_destroy = true # images are reseeded by `make seed`
}

resource "aws_s3_bucket_public_access_block" "images" {
  bucket                  = aws_s3_bucket.images.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "images" {
  bucket = aws_s3_bucket.images.id
  rule {
    apply_server_side_encryption_by_default { sse_algorithm = "AES256" }
  }
}

resource "aws_s3_bucket_policy" "images" {
  bucket = aws_s3_bucket.images.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid       = "DenyInsecureTransport"
      Effect    = "Deny"
      Principal = "*"
      Action    = "s3:*"
      Resource  = [aws_s3_bucket.images.arn, "${aws_s3_bucket.images.arn}/*"]
      Condition = { Bool = { "aws:SecureTransport" = "false" } }
    }]
  })
  depends_on = [aws_s3_bucket_public_access_block.images]
}

# --- API + web on Lambda --------------------------------------------------------

resource "aws_cloudwatch_log_group" "api" {
  name              = "/aws/lambda/${local.name}"
  retention_in_days = 7
}

resource "aws_iam_role" "api" {
  name                 = local.name
  permissions_boundary = local.boundary
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Action    = "sts:AssumeRole"
      Principal = { Service = "lambda.amazonaws.com" }
    }]
  })
}

resource "aws_iam_role_policy" "api" {
  role = aws_iam_role.api.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = ["logs:CreateLogStream", "logs:PutLogEvents"]
        Resource = "${aws_cloudwatch_log_group.api.arn}:*"
      },
      {
        Effect    = "Allow"
        Action    = "s3:ListBucket"
        Resource  = aws_s3_bucket.images.arn
        Condition = { StringLike = { "s3:prefix" = "dogs/*" } }
      },
      {
        Effect   = "Allow"
        Action   = "s3:GetObject"
        Resource = "${aws_s3_bucket.images.arn}/dogs/*"
      },
    ]
  })
}

resource "aws_lambda_function" "api" {
  function_name    = local.name
  role             = aws_iam_role.api.arn
  runtime          = "python3.14"
  architectures    = ["arm64"]
  handler          = "app.main.handler"
  filename         = "${path.module}/../build/lambda.zip"
  source_code_hash = filebase64sha256("${path.module}/../build/lambda.zip")
  memory_size      = 128
  timeout          = 10
  environment {
    variables = { DOGS_BUCKET = aws_s3_bucket.images.bucket }
  }
  depends_on = [aws_cloudwatch_log_group.api, aws_iam_role_policy.api]
}

# Public, unauthenticated, read-only (Phase 3 fallback: no CloudFront, see lab-admin BASELINE).
resource "aws_lambda_function_url" "api" {
  function_name      = aws_lambda_function.api.function_name
  authorization_type = "NONE"
}

# Since Oct 2025 a NONE function URL needs both permissions (Lambda docs: urls-auth).
resource "aws_lambda_permission" "url" {
  statement_id           = "FunctionURLAllowPublicAccess"
  function_name          = aws_lambda_function.api.function_name
  action                 = "lambda:InvokeFunctionUrl"
  principal              = "*"
  function_url_auth_type = "NONE"
}

resource "aws_lambda_permission" "invoke_via_url" {
  statement_id             = "FunctionURLInvokeAllowPublicAccess"
  function_name            = aws_lambda_function.api.function_name
  action                   = "lambda:InvokeFunction"
  principal                = "*"
  invoked_via_function_url = true
}

output "url" {
  value = aws_lambda_function_url.api.function_url
}

output "bucket" {
  value = aws_s3_bucket.images.bucket
}
