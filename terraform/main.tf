data "archive_file" "function_zip" {
  type        = "zip"
  source_dir  = "${path.module}/../src"
  output_path = "${path.module}/function.zip"
}

resource "random_id" "suffix" {
  byte_length = 4
}

locals {
  # Storage account names: 3-24 chars, lowercase alphanumeric only
  name = substr(lower(replace("${var.project}${random_id.suffix.hex}", "-", "")), 0, 24)
}

# ---------------------------------------------------------------------------
# Resource group
# ---------------------------------------------------------------------------
resource "azurerm_resource_group" "this" {
  name     = "${var.project}-rg"
  location = var.location
}

# ---------------------------------------------------------------------------
# Storage account — private, encrypted at rest (default), LRS
# ---------------------------------------------------------------------------
resource "azurerm_storage_account" "this" {
  name                            = local.name
  resource_group_name             = azurerm_resource_group.this.name
  location                        = azurerm_resource_group.this.location
  account_tier                    = "Standard"
  account_replication_type        = "LRS"
  allow_nested_items_to_be_public = false
  https_traffic_only_enabled      = true
  min_tls_version                 = "TLS1_2"

  blob_properties {
    delete_retention_policy {
      days = 7
    }
  }
}

# ---------------------------------------------------------------------------
# Blob container — private
# ---------------------------------------------------------------------------
resource "azurerm_storage_container" "images" {
  name                  = "images"
  storage_account_id    = azurerm_storage_account.this.id
  container_access_type = "private"
}

# ---------------------------------------------------------------------------
# Blob lifecycle — expire objects after retention_days
# ---------------------------------------------------------------------------
resource "azurerm_storage_management_policy" "expiry" {
  storage_account_id = azurerm_storage_account.this.id

  rule {
    name    = "expire-blobs"
    enabled = true

    filters {
      blob_types = ["blockBlob"]
    }

    actions {
      base_blob {
        delete_after_days_since_modification_greater_than = var.retention_days
      }
    }
  }
}

# ---------------------------------------------------------------------------
# App Service plan — consumption (Y1 = serverless)
# ---------------------------------------------------------------------------
resource "azurerm_service_plan" "this" {
  name                = "${var.project}-plan"
  location            = azurerm_resource_group.this.location
  resource_group_name = azurerm_resource_group.this.name
  os_type             = "Linux"
  sku_name            = "Y1"
}

# ---------------------------------------------------------------------------
# Azure Function App
# ---------------------------------------------------------------------------
resource "azurerm_linux_function_app" "this" {
  name                = "${var.project}-func-${random_id.suffix.hex}"
  location            = azurerm_resource_group.this.location
  resource_group_name = azurerm_resource_group.this.name

  service_plan_id            = azurerm_service_plan.this.id
  storage_account_name       = azurerm_storage_account.this.name
  storage_account_access_key = azurerm_storage_account.this.primary_access_key

  https_only = true

  site_config {
    application_stack {
      python_version = "3.11"
    }
    # Equivalent to API Gateway usage plan throttling
    app_scale_limit = 5
  }

  app_settings = {
    FUNCTIONS_WORKER_RUNTIME = "python"
    # Required for v2 programming model (decorator-based)
    AzureWebJobsFeatureFlags = "EnableWorkerIndexing"
    BLOB_CONTAINER           = azurerm_storage_container.images.name
    STORAGE_ACCOUNT_NAME     = azurerm_storage_account.this.name
    STORAGE_ACCOUNT_KEY      = azurerm_storage_account.this.primary_access_key
    THUMBNAIL_SIZE           = tostring(var.thumbnail_size)
    SAS_EXPIRY_HOURS         = tostring(var.sas_expiry_hours)
    # Deploy from zip package
    WEBSITE_RUN_FROM_PACKAGE = "1"
  }

  zip_deploy_file = data.archive_file.function_zip.output_path
}
