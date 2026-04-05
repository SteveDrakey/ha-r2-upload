"""Cloudflare R2 Upload integration for Home Assistant."""

from __future__ import annotations

import logging
import mimetypes
from typing import Any

import boto3
import voluptuous as vol
from botocore.exceptions import ClientError, EndpointConnectionError, NoCredentialsError
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError
import homeassistant.helpers.config_validation as cv

from .const import (
    CONF_ACCESS_KEY_ID,
    CONF_BUCKET,
    CONF_ENDPOINT_URL,
    CONF_PUBLIC_URL_BASE,
    CONF_SECRET_ACCESS_KEY,
    DEFAULT_EXPIRY,
    DEFAULT_STORAGE_CLASS,
    DOMAIN,
    EVENT_DELETED,
    EVENT_SIGNED_URL,
    EVENT_UPLOAD_COMPLETE,
)

_LOGGER = logging.getLogger(__name__)

SERVICE_PUT = "put"
SERVICE_SIGN_URL = "sign_url"
SERVICE_DELETE = "delete"

SERVICE_PUT_SCHEMA = vol.Schema(
    {
        vol.Required("file_path"): cv.string,
        vol.Required("key"): cv.string,
        vol.Optional("content_type"): cv.string,
        vol.Optional("metadata", default={}): vol.Schema(
            {cv.string: cv.string}
        ),
        vol.Optional("storage_class", default=DEFAULT_STORAGE_CLASS): cv.string,
    }
)

SERVICE_SIGN_URL_SCHEMA = vol.Schema(
    {
        vol.Required("key"): cv.string,
        vol.Optional("expiry", default=DEFAULT_EXPIRY): cv.positive_int,
    }
)

SERVICE_DELETE_SCHEMA = vol.Schema(
    {
        vol.Required("key"): cv.string,
    }
)


def _create_client(data: dict[str, Any]) -> boto3.client:
    """Create a boto3 S3 client from config entry data."""
    return boto3.client(
        "s3",
        endpoint_url=data[CONF_ENDPOINT_URL],
        aws_access_key_id=data[CONF_ACCESS_KEY_ID],
        aws_secret_access_key=data[CONF_SECRET_ACCESS_KEY],
    )


def _do_put_object(
    client: Any,
    bucket: str,
    file_path: str,
    key: str,
    content_type: str | None,
    metadata: dict[str, str],
    storage_class: str,
) -> None:
    """Upload a file to R2 (runs in executor)."""
    if not content_type:
        content_type = mimetypes.guess_type(file_path)[0] or "application/octet-stream"

    with open(file_path, "rb") as fh:
        file_data = fh.read()

    params: dict[str, Any] = {
        "Bucket": bucket,
        "Key": key,
        "Body": file_data,
        "ContentType": content_type,
        "StorageClass": storage_class,
    }
    if metadata:
        params["Metadata"] = metadata

    client.put_object(**params)


def _do_generate_presigned_url(
    client: Any,
    bucket: str,
    key: str,
    expiry: int,
) -> str:
    """Generate a presigned URL (runs in executor)."""
    return client.generate_presigned_url(
        "get_object",
        Params={"Bucket": bucket, "Key": key},
        ExpiresIn=expiry,
    )


def _do_delete_object(client: Any, bucket: str, key: str) -> None:
    """Delete an object from R2 (runs in executor)."""
    client.delete_object(Bucket=bucket, Key=key)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Cloudflare R2 Upload from a config entry."""
    client = await hass.async_add_executor_job(_create_client, dict(entry.data))

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {
        "client": client,
        "config": dict(entry.data),
    }

    # Only register services once (shared across all entries)
    if not hass.services.has_service(DOMAIN, SERVICE_PUT):
        _register_services(hass)

    return True


def _get_entry_data(hass: HomeAssistant, entry_id: str | None = None) -> dict[str, Any]:
    """Get the first (or specified) entry's client and config."""
    entries = hass.data.get(DOMAIN, {})
    if not entries:
        raise HomeAssistantError("No R2 Upload entries configured")
    if entry_id and entry_id in entries:
        return entries[entry_id]
    # Return first entry if none specified
    return next(iter(entries.values()))


def _register_services(hass: HomeAssistant) -> None:
    """Register integration services."""

    async def handle_put(call: ServiceCall) -> None:
        """Handle the put service call."""
        entry_data = _get_entry_data(hass)
        client = entry_data["client"]
        config = entry_data["config"]
        bucket = config[CONF_BUCKET]

        file_path = call.data["file_path"]
        key = call.data["key"]
        content_type = call.data.get("content_type")
        metadata = call.data.get("metadata", {})
        storage_class = call.data.get("storage_class", DEFAULT_STORAGE_CLASS)

        try:
            await hass.async_add_executor_job(
                _do_put_object,
                client,
                bucket,
                file_path,
                key,
                content_type,
                metadata,
                storage_class,
            )
        except (ClientError, NoCredentialsError, EndpointConnectionError) as err:
            _LOGGER.error(
                "Failed to upload %s to R2 bucket %s key %s: %s",
                file_path, bucket, key, err,
            )
            raise HomeAssistantError(
                f"Failed to upload to R2: {err}"
            ) from err
        except FileNotFoundError as err:
            _LOGGER.error("File not found: %s", file_path)
            raise HomeAssistantError(
                f"File not found: {file_path}"
            ) from err

        resolved_content_type = content_type or mimetypes.guess_type(file_path)[0] or "application/octet-stream"

        event_data: dict[str, Any] = {
            "bucket": bucket,
            "key": key,
            "content_type": resolved_content_type,
            "metadata": metadata,
        }

        public_url_base = config.get(CONF_PUBLIC_URL_BASE)
        if public_url_base:
            public_url = f"{public_url_base.rstrip('/')}/{key}"
            event_data["public_url"] = public_url

        hass.bus.async_fire(EVENT_UPLOAD_COMPLETE, event_data)
        _LOGGER.info("Uploaded %s to R2 bucket %s key %s", file_path, bucket, key)

    async def handle_sign_url(call: ServiceCall) -> None:
        """Handle the sign_url service call."""
        entry_data = _get_entry_data(hass)
        client = entry_data["client"]
        config = entry_data["config"]
        bucket = config[CONF_BUCKET]

        key = call.data["key"]
        expiry = call.data.get("expiry", DEFAULT_EXPIRY)

        try:
            url = await hass.async_add_executor_job(
                _do_generate_presigned_url,
                client,
                bucket,
                key,
                expiry,
            )
        except (ClientError, NoCredentialsError, EndpointConnectionError) as err:
            _LOGGER.error(
                "Failed to generate presigned URL for R2 bucket %s key %s: %s",
                bucket, key, err,
            )
            raise HomeAssistantError(
                f"Failed to generate presigned URL: {err}"
            ) from err

        hass.bus.async_fire(
            EVENT_SIGNED_URL,
            {"key": key, "url": url, "expiry": expiry},
        )
        _LOGGER.info("Generated presigned URL for R2 bucket %s key %s", bucket, key)

    async def handle_delete(call: ServiceCall) -> None:
        """Handle the delete service call."""
        entry_data = _get_entry_data(hass)
        client = entry_data["client"]
        config = entry_data["config"]
        bucket = config[CONF_BUCKET]

        key = call.data["key"]

        try:
            await hass.async_add_executor_job(
                _do_delete_object,
                client,
                bucket,
                key,
            )
        except (ClientError, NoCredentialsError, EndpointConnectionError) as err:
            _LOGGER.error(
                "Failed to delete from R2 bucket %s key %s: %s",
                bucket, key, err,
            )
            raise HomeAssistantError(
                f"Failed to delete from R2: {err}"
            ) from err

        hass.bus.async_fire(
            EVENT_DELETED,
            {"bucket": bucket, "key": key},
        )
        _LOGGER.info("Deleted from R2 bucket %s key %s", bucket, key)

    hass.services.async_register(DOMAIN, SERVICE_PUT, handle_put, schema=SERVICE_PUT_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_SIGN_URL, handle_sign_url, schema=SERVICE_SIGN_URL_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_DELETE, handle_delete, schema=SERVICE_DELETE_SCHEMA)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    hass.data[DOMAIN].pop(entry.entry_id, None)

    # If no more entries, remove the services
    if not hass.data[DOMAIN]:
        hass.data.pop(DOMAIN)
        hass.services.async_remove(DOMAIN, SERVICE_PUT)
        hass.services.async_remove(DOMAIN, SERVICE_SIGN_URL)
        hass.services.async_remove(DOMAIN, SERVICE_DELETE)

    return True
