variable "project_id" {
  type        = string
  description = "The Google Cloud Project ID"
  default     = "sre-lab-project-davi"
}

variable "region" {
  type        = string
  description = "The GCP region for all resources"
  default     = "southamerica-east1" # São Paulo region
}

variable "environment" {
  type        = string
  description = "Deployment environment"
  default     = "production"
}

