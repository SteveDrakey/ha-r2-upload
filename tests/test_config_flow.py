"""Tests for the R2 Upload config flow."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from botocore.exceptions import ClientError, EndpointConnectionError
from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from custom_components.r2_upload.const import DOMAIN


async def test_successful_config_flow(
    hass: HomeAssistant,
    mock_config_data: dict,
    mock_boto3: MagicMock,
) -> None:
    """Test a successful config flow."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], mock_config_data
    )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "test-bucket"
    assert result["data"] == mock_config_data
    mock_boto3.head_bucket.assert_called_once_with(Bucket="test-bucket")


async def test_invalid_credentials(
    hass: HomeAssistant,
    mock_config_data: dict,
    mock_boto3: MagicMock,
) -> None:
    """Test config flow with invalid credentials."""
    mock_boto3.head_bucket.side_effect = ClientError(
        {"Error": {"Code": "403", "Message": "Forbidden"}},
        "HeadBucket",
    )

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], mock_config_data
    )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_auth"}


async def test_unreachable_endpoint(
    hass: HomeAssistant,
    mock_config_data: dict,
    mock_boto3: MagicMock,
) -> None:
    """Test config flow with unreachable endpoint."""
    mock_boto3.head_bucket.side_effect = EndpointConnectionError(
        endpoint_url="https://bad.endpoint.com"
    )

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], mock_config_data
    )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}


async def test_duplicate_bucket_rejected(
    hass: HomeAssistant,
    mock_config_data: dict,
    mock_boto3: MagicMock,
) -> None:
    """Test that a duplicate bucket entry is rejected."""
    # First entry succeeds
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], mock_config_data
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY

    # Second entry with same bucket is aborted
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], mock_config_data
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_bucket_not_found(
    hass: HomeAssistant,
    mock_config_data: dict,
    mock_boto3: MagicMock,
) -> None:
    """Test config flow when bucket does not exist."""
    mock_boto3.head_bucket.side_effect = ClientError(
        {"Error": {"Code": "404", "Message": "Not Found"}},
        "HeadBucket",
    )

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], mock_config_data
    )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "bucket_not_found"}
