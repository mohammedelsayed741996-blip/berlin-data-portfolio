# Glue catalog for the gold layer and an Athena workgroup the semantic layer queries through.

resource "aws_glue_catalog_database" "gold" {
  name = replace("${local.name}_gold", "-", "_")
}

locals {
  gold_tables = {
    account_ar = [
      ["account_id", "string"], ["name", "string"], ["region", "string"], ["segment", "string"], ["owner", "string"],
      ["payment_terms_days", "int"], ["credit_limit_eur", "double"], ["open_eur", "double"], ["overdue_eur", "double"],
      ["oldest_days_past_due", "int"], ["open_invoices", "double"], ["credit_used_pct", "double"], ["contact_email", "string"],
    ]
    open_invoices = [
      ["invoice_id", "string"], ["account_id", "string"], ["owner", "string"], ["region", "string"], ["issued", "string"],
      ["due", "string"], ["amount_eur", "double"], ["open_eur", "double"], ["days_past_due", "int"], ["bucket", "string"],
    ]
    revenue_monthly = [
      ["month", "string"], ["account_id", "string"], ["owner", "string"], ["region", "string"], ["category", "string"],
      ["revenue_eur", "double"],
    ]
  }
}

resource "aws_glue_catalog_table" "gold" {
  for_each      = local.gold_tables
  name          = each.key
  database_name = aws_glue_catalog_database.gold.name
  table_type    = "EXTERNAL_TABLE"

  parameters = {
    "classification"         = "csv"
    "skip.header.line.count" = "1"
  }

  storage_descriptor {
    location      = "s3://${aws_s3_bucket.lake.bucket}/gold/${each.key}/"
    input_format  = "org.apache.hadoop.mapred.TextInputFormat"
    output_format = "org.apache.hadoop.hive.ql.io.HiveIgnoreKeyTextOutputFormat"

    ser_de_info {
      serialization_library = "org.apache.hadoop.hive.serde2.lazy.LazySimpleSerDe"
      parameters = {
        "field.delim" = ","
      }
    }

    dynamic "columns" {
      for_each = each.value
      content {
        name = columns.value[0]
        type = columns.value[1]
      }
    }
  }
}

resource "aws_athena_workgroup" "agent" {
  name          = "${local.name}-agent"
  force_destroy = var.environment != "prod"

  configuration {
    enforce_workgroup_configuration    = true
    publish_cloudwatch_metrics_enabled = true
    bytes_scanned_cutoff_per_query     = 1073741824 # 1 GB: a runaway query fails instead of costing money

    result_configuration {
      output_location = "s3://${aws_s3_bucket.lake.bucket}/athena-results/"
      encryption_configuration {
        encryption_option = "SSE_KMS"
        kms_key_arn       = aws_kms_key.lake.arn
      }
    }
  }
}
