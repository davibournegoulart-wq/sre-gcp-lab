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


variable "master_authorized_cidrs" {
  type        = list(object({ cidr = string, name = string }))
  description = "CIDRs allowed to reach the GKE control plane (e.g. your office/home /32). Empty = nobody from outside Google."
  default     = []
}

variable "deletion_protection" {
  type        = bool
  description = "Blocks terraform destroy on GKE and Cloud SQL. Set false only for a deliberate teardown."
  default     = true
}
