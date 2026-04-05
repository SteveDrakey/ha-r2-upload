# Cloudflare R2 Upload for Home Assistant

A Home Assistant custom integration that uploads files to Cloudflare R2 (S3-compatible storage) and generates presigned read URLs. Designed for uploading camera snapshots (e.g. 3D printer cameras) and serving them via presigned or public URLs.

## Features

- Upload files to Cloudflare R2 with custom metadata
- Generate time-limited presigned URLs for private objects
- Delete objects from R2
- Fires events on each operation for use in automations
- Supports multiple buckets via multiple config entries
- Fully async — all S3 calls run in the executor

## Installation

### HACS (Custom Repository)

1. Open HACS in Home Assistant
2. Click the three dots menu → **Custom repositories**
3. Add this repository URL and select **Integration** as the category
4. Click **Add**
5. Search for "Cloudflare R2 Upload" in HACS and install it
6. Restart Home Assistant

### Manual

Copy the `custom_components/r2_upload` directory into your Home Assistant `custom_components` folder and restart.

## Configuration

Configuration is done entirely through the UI:

1. Go to **Settings → Devices & Services → Add Integration**
2. Search for **Cloudflare R2 Upload**
3. Enter your R2 credentials:
   - **Endpoint URL**: Your Cloudflare R2 S3-compatible endpoint (e.g. `https://<account_id>.r2.cloudflarestorage.com`)
   - **Access Key ID**: R2 API token access key
   - **Secret Access Key**: R2 API token secret key
   - **Bucket Name**: Your R2 bucket name
   - **Public URL Base** (optional): Base URL for public access (e.g. `https://prints.example.com`)

The integration validates your credentials during setup by calling `head_bucket`.

## Services

### `r2_upload.put`

Upload a local file to R2.

| Parameter | Required | Description |
|---|---|---|
| `file_path` | Yes | Absolute path to the local file |
| `key` | Yes | Object key/path in the bucket |
| `content_type` | No | MIME type (auto-detected if omitted) |
| `metadata` | No | Dict of custom metadata |
| `storage_class` | No | Storage class (default: `STANDARD`) |

Fires event: `r2_upload_complete`

### `r2_upload.sign_url`

Generate a presigned read URL.

| Parameter | Required | Description |
|---|---|---|
| `key` | Yes | Object key in the bucket |
| `expiry` | No | URL validity in seconds (default: `3600`) |

Fires event: `r2_upload_signed_url`

### `r2_upload.delete`

Delete an object from R2.

| Parameter | Required | Description |
|---|---|---|
| `key` | Yes | Object key to delete |

Fires event: `r2_upload_deleted`

## Example Automations

### Capture 3D printer snapshot, upload to R2, and send notification with presigned URL

```yaml
automation:
  - alias: "Upload printer snapshot every 5 minutes"
    trigger:
      - platform: time_pattern
        minutes: "/5"
    action:
      # Take a snapshot from the camera
      - service: camera.snapshot
        target:
          entity_id: camera.printer_cam
        data:
          filename: /config/www/snapshots/printer_latest.jpg

      # Upload to R2
      - service: r2_upload.put
        data:
          file_path: /config/www/snapshots/printer_latest.jpg
          key: "snapshots/printer1/latest.jpg"
          content_type: "image/jpeg"
          metadata:
            source: "printer_cam"

      # Generate a presigned URL
      - service: r2_upload.sign_url
        data:
          key: "snapshots/printer1/latest.jpg"
          expiry: 3600

  - alias: "Notify on signed URL generated"
    trigger:
      - platform: event
        event_type: r2_upload_signed_url
    action:
      - service: notify.mobile_app
        data:
          title: "Printer Snapshot"
          message: "Latest snapshot available"
          data:
            url: "{{ trigger.event.data.url }}"
```

### Upload with public URL

If you configured a `public_url_base`, the `r2_upload_complete` event includes a `public_url` field:

```yaml
automation:
  - alias: "Notify with public URL after upload"
    trigger:
      - platform: event
        event_type: r2_upload_complete
    action:
      - service: notify.mobile_app
        data:
          title: "Upload Complete"
          message: "{{ trigger.event.data.public_url }}"
```

## Important Notes

- File paths used with `r2_upload.put` must be in your Home Assistant `allowlist_external_dirs` configuration
- All S3 operations run in the executor thread pool to avoid blocking the HA event loop
- The integration uses `boto3` — no additional dependencies needed beyond what's declared in `manifest.json`
