# Cloudflare R2 Upload for Home Assistant

A Home Assistant custom integration that uploads files to Cloudflare R2 (S3-compatible storage) and generates presigned read URLs. Built for uploading camera snapshots (e.g. from 3D printer cameras) to R2 so they can be served to external apps or shared via notifications.

## How It Works

This integration exposes three **services** (`put`, `sign_url`, `delete`) that you call from automations or scripts. Since HA services don't return values, results are delivered via **events** that you listen for in separate automations.

The typical flow:

1. **`camera.snapshot`** saves an image to disk
2. **`r2_upload.put`** uploads that file to your R2 bucket → fires `r2_upload_complete`
3. **`r2_upload.sign_url`** generates a time-limited URL → fires `r2_upload_signed_url`
4. A separate automation **listens for the event** and sends a notification with the URL

```
camera.snapshot → r2_upload.put → r2_upload_complete event
                  r2_upload.sign_url → r2_upload_signed_url event → notify
```

## Features

- Upload files to Cloudflare R2 with custom metadata and auto-detected MIME types
- Generate time-limited presigned URLs for private objects
- Delete objects from R2
- Fires events on each operation for chaining in automations
- Optional public URL construction when a public URL base is configured
- Supports multiple buckets via multiple config entries
- Fully async — all S3 calls run in the executor to avoid blocking the HA event loop

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

Configuration is done entirely through the UI — no YAML needed.

1. Go to **Settings → Devices & Services → Add Integration**
2. Search for **Cloudflare R2 Upload**
3. Enter your R2 credentials:

| Field | Required | Description |
|---|---|---|
| **Endpoint URL** | Yes | Your Cloudflare R2 S3-compatible endpoint, e.g. `https://<account_id>.r2.cloudflarestorage.com` |
| **Access Key ID** | Yes | R2 API token access key |
| **Secret Access Key** | Yes | R2 API token secret key |
| **Bucket Name** | Yes | Your R2 bucket name |
| **Public URL Base** | No | Base URL for public access, e.g. `https://prints.example.com`. When set, upload events include a `public_url` field. |

The integration validates your credentials during setup by calling `head_bucket`. You'll see a clear error if the credentials are wrong, the bucket doesn't exist, or the endpoint is unreachable.

You can add multiple entries for different buckets.

## Services

### `r2_upload.put`

Upload a local file to R2.

| Parameter | Required | Description |
|---|---|---|
| `file_path` | Yes | Absolute path to the local file (must be in `allowlist_external_dirs`) |
| `key` | Yes | Object key/path in the bucket, e.g. `snapshots/printer1/latest.jpg` |
| `content_type` | No | MIME type override. Auto-detected from file extension if omitted. |
| `metadata` | No | Dict of custom string metadata, e.g. `{"printer": "HD2"}` |
| `storage_class` | No | Storage class (default: `STANDARD`) |

**Event fired:** `r2_upload_complete` with data: `bucket`, `key`, `content_type`, `metadata`, and `public_url` (if configured).

### `r2_upload.sign_url`

Generate a presigned read URL for an existing object.

| Parameter | Required | Description |
|---|---|---|
| `key` | Yes | Object key in the bucket |
| `expiry` | No | URL validity in seconds (default: `3600` = 1 hour) |

**Event fired:** `r2_upload_signed_url` with data: `key`, `url`, `expiry`.

### `r2_upload.delete`

Delete an object from R2.

| Parameter | Required | Description |
|---|---|---|
| `key` | Yes | Object key to delete |

**Event fired:** `r2_upload_deleted` with data: `bucket`, `key`.

## Events

All three services fire events so you can chain results in automations. The key fields:

| Event | Key Fields |
|---|---|
| `r2_upload_complete` | `bucket`, `key`, `content_type`, `metadata`, `public_url` |
| `r2_upload_signed_url` | `key`, `url`, `expiry` |
| `r2_upload_deleted` | `bucket`, `key` |

Access event data in automations via `{{ trigger.event.data.url }}`, `{{ trigger.event.data.public_url }}`, etc.

## Example Automations

### Full flow: snapshot → upload → presigned URL → notification

This uses two automations. The first takes a snapshot and uploads it. The second listens for the signed URL event and sends a notification.

```yaml
# Automation 1: Take snapshot, upload, and request a presigned URL
automation:
  - alias: "Upload printer snapshot every 5 minutes"
    trigger:
      - platform: time_pattern
        minutes: "/5"
    action:
      - service: camera.snapshot
        target:
          entity_id: camera.printer_cam
        data:
          filename: /config/www/snapshots/printer_latest.jpg

      - service: r2_upload.put
        data:
          file_path: /config/www/snapshots/printer_latest.jpg
          key: "snapshots/printer1/latest.jpg"
          content_type: "image/jpeg"
          metadata:
            source: "printer_cam"

      - service: r2_upload.sign_url
        data:
          key: "snapshots/printer1/latest.jpg"
          expiry: 3600
```

```yaml
# Automation 2: React to the signed URL event
automation:
  - alias: "Send printer snapshot notification"
    trigger:
      - platform: event
        event_type: r2_upload_signed_url
    condition:
      - condition: template
        value_template: "{{ trigger.event.data.key == 'snapshots/printer1/latest.jpg' }}"
    action:
      - service: notify.mobile_app
        data:
          title: "Printer Snapshot"
          message: "Latest snapshot available"
          data:
            url: "{{ trigger.event.data.url }}"
```

### Using public URLs instead of presigned URLs

If you configured a **Public URL Base** (e.g. via a Cloudflare R2 custom domain), you don't need `sign_url` at all — the public URL is included in the upload event:

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

## Allowlisting File Paths

Home Assistant requires that file paths accessed by integrations are explicitly allowed. Add your snapshot directory to `configuration.yaml`:

```yaml
homeassistant:
  allowlist_external_dirs:
    - /config/www/snapshots
```

## Troubleshooting

- **"Failed to upload to R2"** — Check your credentials, bucket name, and that the R2 API token has write permissions.
- **"File not found"** — Verify the file path exists and is in `allowlist_external_dirs`.
- **Events not firing** — Check the HA logs at **Settings → System → Logs** for error details.
- **Presigned URLs not working** — Ensure your R2 bucket hasn't restricted presigned URL access. The default R2 settings allow them.
