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
  # Private nodes reach Artifact Registry / Google APIs without public IPs.
  private_ip_google_access = true

  secondary_ip_range {
    range_name    = "pods"
    ip_cidr_range = "10.4.0.0/14"
  }

  secondary_ip_range {
    range_name    = "services"
    ip_cidr_range = "10.8.0.0/20"
  }
}

# 1b. Cloud NAT: private nodes have no external IPs, so outbound internet
# (e.g. the triage bot calling the Gemini API) goes through NAT only.
resource "google_compute_router" "router" {
  name    = "sre-lab-router"
  region  = var.region
  network = google_compute_network.vpc.id
}

resource "google_compute_router_nat" "nat" {
  name                               = "sre-lab-nat"
  router                             = google_compute_router.router.name
  region                             = var.region
  nat_ip_allocate_option             = "AUTO_ONLY"
  source_subnetwork_ip_ranges_to_nat = "ALL_SUBNETWORKS_ALL_IP_RANGES"

  log_config {
    enable = true
    filter = "ERRORS_ONLY"
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

  # Nodes get no public IPs; the control plane is reachable only from the
  # CIDRs listed in var.master_authorized_cidrs.
  private_cluster_config {
    enable_private_nodes    = true
    enable_private_endpoint = false
  }

  master_authorized_networks_config {
    dynamic "cidr_blocks" {
      for_each = var.master_authorized_cidrs
      content {
        cidr_block   = cidr_blocks.value.cidr
        display_name = cidr_blocks.value.name
      }
    }
  }

  deletion_protection = var.deletion_protection
}

# 4. Cloud Storage Bucket for Assets & Data
resource "google_storage_bucket" "assets" {
  name                        = "${var.project_id}-sre-assets"
  location                    = var.region
  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"
  force_destroy               = false

  versioning {
    enabled = true
  }
}

# 5. Private Services Access: Cloud SQL gets an IP inside the VPC only
resource "google_compute_global_address" "sql_private_range" {
  name          = "sre-sql-private-range"
  purpose       = "VPC_PEERING"
  address_type  = "INTERNAL"
  prefix_length = 20
  network       = google_compute_network.vpc.id
}

resource "google_service_networking_connection" "sql_peering" {
  network                 = google_compute_network.vpc.id
  service                 = "servicenetworking.googleapis.com"
  reserved_peering_ranges = [google_compute_global_address.sql_private_range.name]
}

# 6. Cloud SQL (PostgreSQL db-f1-micro) - Minimal Cost Tier
resource "google_sql_database_instance" "postgres" {
  name             = "sre-postgres-instance"
  database_version = "POSTGRES_15"
  region           = var.region

  deletion_protection = var.deletion_protection
  depends_on          = [google_service_networking_connection.sql_peering]

  settings {
    tier                        = "db-f1-micro" # Lowest cost for development & demonstration
    deletion_protection_enabled = var.deletion_protection

    # Was a public IPv4 with no authorized networks and no TLS requirement.
    ip_configuration {
      ipv4_enabled    = false
      private_network = google_compute_network.vpc.id
      ssl_mode        = "ENCRYPTED_ONLY"
    }

    backup_configuration {
      enabled                        = true
      point_in_time_recovery_enabled = true
      backup_retention_settings {
        retained_backups = 7
      }
    }
  }
}

