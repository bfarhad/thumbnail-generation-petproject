output "function_url" {
  description = "Invoke URL for POST /api/thumbnails (append ?code=<function_key>)."
  value       = "https://${azurerm_linux_function_app.this.default_hostname}/api/thumbnails"
}

output "function_name" {
  description = "Azure Function App name."
  value       = azurerm_linux_function_app.this.name
}

output "storage_account_name" {
  description = "Storage account name."
  value       = azurerm_storage_account.this.name
}

output "container_name" {
  description = "Blob container name."
  value       = azurerm_storage_container.images.name
}

output "resource_group" {
  description = "Resource group name."
  value       = azurerm_resource_group.this.name
}
