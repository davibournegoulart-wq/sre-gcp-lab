terraform {
  required_version = ">= 1.5.0"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.0"
    }
  }
  # Remote GCS Backend for state locking and shared visibility
  # backend "gcs" {
  #   bucket = "sre-gcp-lab-tfstate"
  #   prefix = "terraform/state"
  # }
}

provider "google" {
  project = var.project_id
  region  = var.region
}

# 1. Custom VPC Network & Subnet
resource "google_compute_network" "vpc" {
  name                    = "sre-lab-vpc"
  auto_create_subnetworks = false
}

resource "google_compute_subnetwork" "subnet" {
  name          = "sre-lab-subnet-${var.region}"
  ip_cidr_range = "10.0.0.0/20"
  region        = var.region
  network       = google_compute_network.vpc.id

  secondary_ip_range {
    range_name    = "pods"
    ip_cidr_range = "10.4.0.0/14"
  }

  secondary_ip_range {
    range_name    = "services"
    ip_cidr_range = "10.8.0.0/20"
  }
}

# 2. Artifact Registry for Container Images
resource "google_artifact_registry_repository" "repo" {
  location      = var.region
  repository_id = "sre-images"
  description   = "Docker repository for SRE Lab microservices"
  format        = "DOCKER"
}

# 3. GKE Autopilot Cluster (Cost-effective & zero node management)
resource "google_container_cluster" "primary" {
  name     = "sre-autopilot-cluster"
  location = var.region

  enable_autopilot = true
  network          = google_compute_network.vpc.name
  subnetwork       = google_compute_subnetwork.subnet.name

  ip_allocation_policy {
    cluster_secondary_range_name  = "pods"
    services_secondary_range_name = "services"
  }

  release_channel {
    channel = "REGULAR"
  }

  deletion_protection = false
}

# 4. Cloud Storage Bucket for Assets & Data
resource "google_storage_bucket" "assets" {
  name                        = "${var.project_id}-sre-assets"
  location                    = var.region
  uniform_bucket_level_access = true
  force_destroy               = true

  versioning {
    enabled = true
  }
}

# 5. Cloud SQL (PostgreSQL db-f1-micro) - Minimal Cost Tier
resource "google_sql_database_instance" "postgres" {
  name             = "sre-postgres-instance"
  database_version = "POSTGRES_15"
  region           = var.region

  deletion_protection = false

  settings {
    tier = "db-f1-micro" # Lowest cost for development & demonstration

    ip_configuration {
      ipv4_enabled = true
    }

    backup_configuration {
      enabled = false # Disabled to minimize lab storage cost
    }
  }
}
