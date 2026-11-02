"""Signed, reusable QR tokens for visitor check-in.

The token is derived from the visitor's UUID and signed with Django's
``SECRET_KEY``. Nothing extra needs to be stored in SQL or Firestore, so every
existing visitor gets a working QR code immediately. The signature makes a
forged or edited token detectable while keeping the same code reusable for
every future visit.
"""

from __future__ import annotations

import uuid
from io import BytesIO

from django.core import signing

from .exceptions import InvalidQrCodeError

QR_PREFIX = "visitra:v1:"
QR_SALT = "visitra.visitor.qr"


def _visitor_id(visitor) -> str:
    return str(getattr(visitor, "pk", visitor))


def make_qr_payload(visitor) -> str:
    """Return the opaque payload encoded into a visitor's QR code."""
    signed = signing.dumps(_visitor_id(visitor), salt=QR_SALT, compress=True)
    return f"{QR_PREFIX}{signed}"


def read_qr_payload(value: str) -> str:
    """Verify a scanned payload and return the visitor UUID as a string."""
    value = (value or "").strip()
    if not value.startswith(QR_PREFIX):
        raise InvalidQrCodeError("This QR code could not be recognized.")

    signed = value[len(QR_PREFIX) :]
    try:
        visitor_id = signing.loads(signed, salt=QR_SALT)
    except signing.BadSignature as exc:
        raise InvalidQrCodeError("This QR code could not be recognized.") from exc

    try:
        return str(uuid.UUID(str(visitor_id)))
    except (ValueError, TypeError, AttributeError) as exc:
        raise InvalidQrCodeError("This QR code could not be recognized.") from exc


def qr_svg(payload: str) -> bytes:
    """Render a QR payload as an SVG image (no Pillow dependency)."""
    import qrcode
    import qrcode.image.svg

    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=10,
        border=2,
    )
    qr.add_data(payload)
    qr.make(fit=True)

    image = qr.make_image(image_factory=qrcode.image.svg.SvgPathImage)
    buffer = BytesIO()
    image.save(buffer)
    return buffer.getvalue()
