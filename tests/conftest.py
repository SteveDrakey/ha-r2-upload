"""Fixtures for R2 Upload tests."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from homeassistant.core import HomeAssistant

from custom_components.r2_upload.const import (
    CONF_ACCESS_KEY_ID,
    CONF_BUCKET,
    CONF_ENDPOINT_URL,
    CONF_PUBLIC_URL_BASE,
    CONF_SECRET_ACCESS_KEY,
)


@pytest.fixture
def mock_config_data() -> dict[str, str]:
    """Return mock config entry data."""
    return {
        CONF_ENDPOINT_URL: "https://test123.r2.cloudflarestorage.com",
        CONF_ACCESS_KEY_ID: "test-access-key",
        CONF_SECRET_ACCESS_KEY: "test-secret-key",
        CONF_BUCKET: "test-bucket",
        CONF_PUBLIC_URL_BASE: "https://cdn.example.com",
    }


@pytest.fixture
def mock_s3_client() -> MagicMock:
    """Return a mock boto3 S3 client."""
    client = MagicMock()
    client.head_bucket.return_value = {}
    client.put_object.return_value = {}
    client.delete_object.return_value = {}
    client.generate_presigned_url.return_value = "https://presigned.example.com/test"
    return client


@pytest.fixture
def mock_boto3(mock_s3_client: MagicMock):
    """Patch boto3.client to return the mock S3 client."""
    with patch(
        "custom_components.r2_upload.config_flow.boto3.client",
        return_value=mock_s3_client,
    ) as mock_cf, patch(
        "custom_components.r2_upload.boto3.client",
        return_value=mock_s3_client,
    ) as mock_init:
        yield mock_s3_client
