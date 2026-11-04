output "cluster_name" {
  description = "GKE Autopilot cluster name"
  value       = google_container_cluster.primary.name
}

output "cluster_endpoint" {
  description = "GKE Cluster Endpoint"
  value       = google_container_cluster.primary.endpoint
}

output "artifact_registry_url" {
  description = "Docker repository endpoint in Artifact Registry"
  value       = "${var.region}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.repo.repository_id}"
}

output "cloud_sql_connection_name" {
  description = "Cloud SQL Instance connection name for Cloud SQL Auth Proxy"
  value       = google_sql_database_instance.postgres.connection_name
}

output "cloud_sql_ip" {
  description = "Public IP of Cloud SQL instance"
  value       = google_sql_database_instance.postgres.public_ip_address
}

output "storage_bucket_url" {
  description = "Cloud Storage bucket URL"
  value       = google_storage_bucket.assets.url
}

