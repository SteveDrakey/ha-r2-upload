"""Tests for the R2 Upload integration setup and services."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from botocore.exceptions import ClientError
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError

from custom_components.r2_upload.const import DOMAIN

from pytest_homeassistant_custom_component.common import MockConfigEntry


async def _setup_entry(
    hass: HomeAssistant,
    mock_config_data: dict,
    mock_boto3: MagicMock,
) -> MockConfigEntry:
    """Create and set up a config entry."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data=mock_config_data,
        title="test-bucket",
        unique_id="test-bucket",
    )
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def test_successful_setup(
    hass: HomeAssistant,
    mock_config_data: dict,
    mock_boto3: MagicMock,
) -> None:
    """Test successful setup creates client in hass.data."""
    entry = await _setup_entry(hass, mock_config_data, mock_boto3)

    assert DOMAIN in hass.data
    assert entry.entry_id in hass.data[DOMAIN]
    assert "client" in hass.data[DOMAIN][entry.entry_id]


async def test_services_registered(
    hass: HomeAssistant,
    mock_config_data: dict,
    mock_boto3: MagicMock,
) -> None:
    """Test all three services are registered after setup."""
    await _setup_entry(hass, mock_config_data, mock_boto3)

    assert hass.services.has_service(DOMAIN, "put")
    assert hass.services.has_service(DOMAIN, "sign_url")
    assert hass.services.has_service(DOMAIN, "delete")


async def test_put_service(
    hass: HomeAssistant,
    mock_config_data: dict,
    mock_boto3: MagicMock,
    tmp_path,
) -> None:
    """Test the put service uploads correctly."""
    await _setup_entry(hass, mock_config_data, mock_boto3)

    test_file = tmp_path / "test.jpg"
    test_file.write_bytes(b"fake image data")

    events = []
    hass.bus.async_listen("r2_upload_complete", lambda e: events.append(e))

    await hass.services.async_call(
        DOMAIN,
        "put",
        {
            "file_path": str(test_file),
            "key": "snapshots/test.jpg",
            "content_type": "image/jpeg",
            "metadata": {"printer": "test"},
        },
        blocking=True,
    )

    mock_boto3.put_object.assert_called_once()
    call_kwargs = mock_boto3.put_object.call_args
    assert call_kwargs.kwargs["Bucket"] == "test-bucket"
    assert call_kwargs.kwargs["Key"] == "snapshots/test.jpg"
    assert call_kwargs.kwargs["ContentType"] == "image/jpeg"
    assert call_kwargs.kwargs["Metadata"] == {"printer": "test"}

    await hass.async_block_till_done()
    assert len(events) == 1
    assert events[0].data["bucket"] == "test-bucket"
    assert events[0].data["key"] == "snapshots/test.jpg"
    assert events[0].data["public_url"] == "https://cdn.example.com/snapshots/test.jpg"


async def test_sign_url_service(
    hass: HomeAssistant,
    mock_config_data: dict,
    mock_boto3: MagicMock,
) -> None:
    """Test the sign_url service generates a presigned URL."""
    await _setup_entry(hass, mock_config_data, mock_boto3)

    events = []
    hass.bus.async_listen("r2_upload_signed_url", lambda e: events.append(e))

    await hass.services.async_call(
        DOMAIN,
        "sign_url",
        {"key": "snapshots/test.jpg", "expiry": 7200},
        blocking=True,
    )

    mock_boto3.generate_presigned_url.assert_called_once_with(
        "get_object",
        Params={"Bucket": "test-bucket", "Key": "snapshots/test.jpg"},
        ExpiresIn=7200,
    )

    await hass.async_block_till_done()
    assert len(events) == 1
    assert events[0].data["key"] == "snapshots/test.jpg"
    assert events[0].data["url"] == "https://presigned.example.com/test"
    assert events[0].data["expiry"] == 7200


async def test_delete_service(
    hass: HomeAssistant,
    mock_config_data: dict,
    mock_boto3: MagicMock,
) -> None:
    """Test the delete service removes an object."""
    await _setup_entry(hass, mock_config_data, mock_boto3)

    events = []
    hass.bus.async_listen("r2_upload_deleted", lambda e: events.append(e))

    await hass.services.async_call(
        DOMAIN,
        "delete",
        {"key": "snapshots/old.jpg"},
        blocking=True,
    )

    mock_boto3.delete_object.assert_called_once_with(
        Bucket="test-bucket", Key="snapshots/old.jpg"
    )

    await hass.async_block_till_done()
    assert len(events) == 1
    assert events[0].data["bucket"] == "test-bucket"
    assert events[0].data["key"] == "snapshots/old.jpg"


async def test_put_client_error_raises(
    hass: HomeAssistant,
    mock_config_data: dict,
    mock_boto3: MagicMock,
    tmp_path,
) -> None:
    """Test that ClientError during put raises HomeAssistantError."""
    await _setup_entry(hass, mock_config_data, mock_boto3)

    test_file = tmp_path / "test.jpg"
    test_file.write_bytes(b"fake data")

    mock_boto3.put_object.side_effect = ClientError(
        {"Error": {"Code": "AccessDenied", "Message": "Access Denied"}},
        "PutObject",
    )

    with pytest.raises(HomeAssistantError, match="Failed to upload to R2"):
        await hass.services.async_call(
            DOMAIN,
            "put",
            {"file_path": str(test_file), "key": "test.jpg"},
            blocking=True,
        )


async def test_unload_cleans_up(
    hass: HomeAssistant,
    mock_config_data: dict,
    mock_boto3: MagicMock,
) -> None:
    """Test that unloading cleans up hass.data."""
    entry = await _setup_entry(hass, mock_config_data, mock_boto3)

    assert DOMAIN in hass.data
    assert entry.entry_id in hass.data[DOMAIN]

    await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()

    # Domain key removed when last entry is unloaded
    assert DOMAIN not in hass.data
    # Services removed
    assert not hass.services.has_service(DOMAIN, "put")
