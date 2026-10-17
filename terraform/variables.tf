variable "project" {
  description = "Project name used for resource naming."
  type        = string
  default     = "thumbnail-service"
}

variable "location" {
  description = "Azure region."
  type        = string
  default     = "westeurope"
}

variable "thumbnail_size" {
  description = "Thumbnail size in pixels (square)."
  type        = number
  default     = 256
}

variable "sas_expiry_hours" {
  description = "SAS URL validity in hours."
  type        = number
  default     = 24
}

variable "retention_days" {
  description = "Blob lifecycle expiry in days."
  type        = number
  default     = 7
}
