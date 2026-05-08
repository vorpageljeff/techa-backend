from datetime import datetime, timezone
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.schemas.inspection import InspectionCreate
from app.services.inspection_service import location_from_wkt, location_to_wkt


def test_inspection_create_accepts_field_evidence_payload():
    anomaly_id = uuid4()
    recorded_at = datetime.now(timezone.utc)

    data = InspectionCreate(
        anomaly_id=anomaly_id,
        notes="Folhas com amarelecimento no reboleiro",
        confirmed_issue="deficiencia_nutricional",
        location_lat=-25.403677,
        location_lon=-54.758904,
        photo_url="https://storage.example.com/inspection/photo-1.jpg",
        recorded_at=recorded_at,
    )

    assert data.anomaly_id == anomaly_id
    assert data.location_lat == -25.403677
    assert data.location_lon == -54.758904
    assert data.photo_url.endswith("photo-1.jpg")
    assert data.mark_anomaly_inspected is True


def test_inspection_create_rejects_invalid_coordinates():
    with pytest.raises(ValidationError):
        InspectionCreate(anomaly_id=uuid4(), location_lat=-91)

    with pytest.raises(ValidationError):
        InspectionCreate(anomaly_id=uuid4(), location_lon=-181)


def test_inspection_create_rejects_non_http_photo_url():
    with pytest.raises(ValidationError):
        InspectionCreate(
            anomaly_id=uuid4(),
            photo_url="file:///local/photo.jpg",
        )


def test_location_wkt_roundtrip():
    location = location_to_wkt(lat=-25.403677, lon=-54.758904)

    assert location == "POINT(-54.758904 -25.403677)"
    assert location_from_wkt(location) == (-25.403677, -54.758904)


def test_location_wkt_allows_missing_coordinates():
    assert location_to_wkt(lat=None, lon=-54.0) is None
    assert location_to_wkt(lat=-25.0, lon=None) is None
    assert location_from_wkt(None) == (None, None)
