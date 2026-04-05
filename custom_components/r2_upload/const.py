"""Constants for the Cloudflare R2 Upload integration."""

DOMAIN = "r2_upload"

CONF_ENDPOINT_URL = "endpoint_url"
CONF_ACCESS_KEY_ID = "access_key_id"
CONF_SECRET_ACCESS_KEY = "secret_access_key"
CONF_BUCKET = "bucket"
CONF_PUBLIC_URL_BASE = "public_url_base"

DEFAULT_EXPIRY = 3600
DEFAULT_STORAGE_CLASS = "STANDARD"

EVENT_UPLOAD_COMPLETE = "r2_upload_complete"
EVENT_SIGNED_URL = "r2_upload_signed_url"
EVENT_DELETED = "r2_upload_deleted"
