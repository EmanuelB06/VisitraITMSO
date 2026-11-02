from __future__ import annotations

import json
import uuid

import pytest
from django.urls import reverse

from visits.models import Purpose
from visits.services import VisitService
from visitors.exceptions import InvalidQrCodeError
from visitors.qr import make_qr_payload, read_qr_payload
from visitors.services import VisitorRegistration, VisitorService

from .conftest import FixedClock, manila


def post_json(client, url, payload):
    return client.post(url, data=json.dumps(payload), content_type="application/json")


@pytest.fixture
def other_purpose(db):
    return Purpose.objects.create(name="ID Printing", sort_order=30)


@pytest.fixture
def other_student(db):
    return VisitorService().register(
        VisitorRegistration(
            visitor_type="STUDENT",
            name="Ana Reyes",
            identifier="2024-00999",
        )
    )


@pytest.mark.django_db
def test_qr_payload_is_reusable_and_unique_per_visitor(student, other_student):
    payload = make_qr_payload(student)

    assert payload.startswith("visitra:v1:")
    assert payload == make_qr_payload(student)
    assert read_qr_payload(payload) == str(student.pk)
    assert make_qr_payload(other_student) != payload


@pytest.mark.django_db
def test_qr_payload_rejects_tampering(student):
    payload = make_qr_payload(student)
    tampered = payload[:-1] + ("A" if payload[-1] != "A" else "B")

    with pytest.raises(InvalidQrCodeError):
        read_qr_payload(tampered)

    with pytest.raises(InvalidQrCodeError):
        read_qr_payload("not-a-visitra-code")


@pytest.mark.django_db
def test_scan_endpoint_requires_staff(client, student):
    response = post_json(client, reverse("visits:qr-scan"), {"qr": make_qr_payload(student)})
    assert response.status_code == 403


@pytest.mark.django_db
def test_scan_endpoint_resolves_a_valid_qr(client, staff_user, student):
    client.force_login(staff_user)

    response = post_json(
        client,
        reverse("visits:qr-scan"),
        {"qr": make_qr_payload(student)},
    )

    assert response.status_code == 200
    visitor = response.json()["visitor"]
    assert visitor["id"] == str(student.pk)
    assert visitor["name"] == "Maria Santos"
    assert visitor["identifier"] == "2024-00123"
    assert visitor["profile_url"].endswith(f"/visitors/{student.pk}/")
    assert visitor["qr_url"].endswith(f"/visitors/{student.pk}/qr.svg")


@pytest.mark.django_db
def test_scan_endpoint_returns_the_active_session(client, staff_user, student, purpose):
    visit = VisitService().time_in(visitor=student, purpose=purpose)
    client.force_login(staff_user)

    response = post_json(
        client,
        reverse("visits:qr-scan"),
        {"qr": make_qr_payload(student)},
    )

    assert response.status_code == 200
    active = response.json()["visitor"]["active_visit"]
    assert active["id"] == str(visit.pk)
    assert active["purpose"] == "MS 365 Assistance"


@pytest.mark.django_db
def test_scan_endpoint_rejects_unknown_and_inactive_visitors(
    client, staff_user, student, other_student
):
    client.force_login(staff_user)

    unknown = make_qr_payload(uuid.uuid4())
    response = post_json(client, reverse("visits:qr-scan"), {"qr": unknown})
    assert response.status_code == 404
    assert "recognized" in response.json()["error"]

    other_student.is_active = False
    other_student.save(update_fields=["is_active"])
    response = post_json(
        client,
        reverse("visits:qr-scan"),
        {"qr": make_qr_payload(other_student)},
    )
    assert response.status_code == 404


@pytest.mark.django_db
def test_scan_endpoint_validates_payload(client, staff_user, student):
    client.force_login(staff_user)
    url = reverse("visits:qr-scan")

    assert post_json(client, url, {}).status_code == 400
    assert post_json(client, url, {"qr": ""}).status_code == 400
    assert post_json(client, url, {"qr": "garbage"}).status_code == 404

    tampered = make_qr_payload(student)
    tampered = tampered[:-1] + ("A" if tampered[-1] != "A" else "B")
    assert post_json(client, url, {"qr": tampered}).status_code == 404

    response = client.post(url, data="{not json", content_type="application/json")
    assert response.status_code == 400


@pytest.mark.django_db
def test_qr_image_is_svg_for_staff(client, staff_user, student):
    client.force_login(staff_user)

    response = client.get(reverse("visitors:qr", kwargs={"pk": student.pk}))

    assert response.status_code == 200
    assert response["Content-Type"].startswith("image/svg+xml")
    assert response["Cache-Control"].startswith("private")
    assert b"<svg" in response.content


@pytest.mark.django_db
def test_qr_image_requires_staff_and_rejects_unknown_visitors(client, staff_user):
    assert client.get(reverse("visitors:qr", kwargs={"pk": uuid.uuid4()})).status_code == 302

    client.force_login(staff_user)
    assert client.get(reverse("visitors:qr", kwargs={"pk": uuid.uuid4()})).status_code == 404


@pytest.mark.django_db
def test_visitor_profile_shows_qr_and_full_history(
    client, staff_user, student, purpose, other_purpose
):
    old_clock = FixedClock(manila(2026, 3, 9, 9, 0))
    old_service = VisitService(clock=old_clock)
    old_visit = old_service.time_in(visitor=student, purpose=purpose)
    old_clock.set(manila(2026, 3, 9, 10, 0))
    old_service.time_out(old_visit)

    VisitService(clock=FixedClock(manila(2026, 3, 10, 9, 0))).time_in(
        visitor=student,
        purpose=other_purpose,
    )

    client.force_login(staff_user)
    response = client.get(reverse("visitors:detail", kwargs={"pk": student.pk}))

    assert response.status_code == 200
    assert b"Maria Santos" in response.content
    assert b"OneTap check-in QR" in response.content
    assert f"/visitors/{student.pk}/qr.svg".encode() in response.content
    # Staff see the visitor's complete history, including previous days.
    assert b"MS 365 Assistance" in response.content
    assert b"ID Printing" in response.content
    assert b"Mar 09, 2026" in response.content


@pytest.mark.django_db
def test_visitor_profile_requires_staff(client, student):
    response = client.get(reverse("visitors:detail", kwargs={"pk": student.pk}))
    assert response.status_code == 302


@pytest.mark.django_db
def test_visitor_profile_404s_for_unknown_visitor(client, staff_user):
    client.force_login(staff_user)
    response = client.get(reverse("visitors:detail", kwargs={"pk": uuid.uuid4()}))
    assert response.status_code == 404
