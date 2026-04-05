"""Config flow for Cloudflare R2 Upload integration."""

from __future__ import annotations

import logging
from typing import Any

import boto3
import voluptuous as vol
from botocore.exceptions import ClientError, EndpointConnectionError, NoCredentialsError
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.core import HomeAssistant

from .const import (
    CONF_ACCESS_KEY_ID,
    CONF_BUCKET,
    CONF_ENDPOINT_URL,
    CONF_PUBLIC_URL_BASE,
    CONF_SECRET_ACCESS_KEY,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_ENDPOINT_URL): str,
        vol.Required(CONF_ACCESS_KEY_ID): str,
        vol.Required(CONF_SECRET_ACCESS_KEY): str,
        vol.Required(CONF_BUCKET): str,
        vol.Optional(CONF_PUBLIC_URL_BASE, default=""): str,
    }
)


def _validate_credentials(
    endpoint_url: str,
    access_key_id: str,
    secret_access_key: str,
    bucket: str,
) -> str | None:
    """Validate R2 credentials by calling head_bucket. Returns error key or None."""
    try:
        client = boto3.client(
            "s3",
            endpoint_url=endpoint_url,
            aws_access_key_id=access_key_id,
            aws_secret_access_key=secret_access_key,
        )
        client.head_bucket(Bucket=bucket)
    except ClientError as err:
        error_code = err.response.get("Error", {}).get("Code", "")
        if error_code in ("403", "InvalidAccessKeyId", "SignatureDoesNotMatch"):
            return "invalid_auth"
        if error_code in ("404", "NoSuchBucket"):
            return "bucket_not_found"
        _LOGGER.error("Unexpected ClientError validating R2 bucket: %s", err)
        return "cannot_connect"
    except (EndpointConnectionError, ConnectionError):
        return "cannot_connect"
    except NoCredentialsError:
        return "invalid_auth"
    except Exception:
        _LOGGER.exception("Unexpected error validating R2 credentials")
        return "unknown"
    return None


class R2UploadConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Cloudflare R2 Upload."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            # Use bucket as unique ID to prevent duplicates
            await self.async_set_unique_id(user_input[CONF_BUCKET])
            self._abort_if_unique_id_configured()

            # Validate credentials in executor to avoid blocking
            error = await self.hass.async_add_executor_job(
                _validate_credentials,
                user_input[CONF_ENDPOINT_URL],
                user_input[CONF_ACCESS_KEY_ID],
                user_input[CONF_SECRET_ACCESS_KEY],
                user_input[CONF_BUCKET],
            )

            if error:
                errors["base"] = error
            else:
                # Strip empty public_url_base
                if not user_input.get(CONF_PUBLIC_URL_BASE):
                    user_input.pop(CONF_PUBLIC_URL_BASE, None)

                return self.async_create_entry(
                    title=user_input[CONF_BUCKET],
                    data=user_input,
                )

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors,
        )
