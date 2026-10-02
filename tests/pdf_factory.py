"""Small PDF fixture builder used by parser tests."""


def build_pdf(page_contents: list[bytes]) -> bytes:
    """Build a minimal PDF with one content stream per page."""

    page_count = len(page_contents)
    font_object_number = 3 + (page_count * 2)
    objects: list[bytes] = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        (
            f"<< /Type /Pages /Kids [{''.join(f'{3 + (index * 2)} 0 R ' for index in range(page_count))}] "
            f"/Count {page_count} >>"
        ).encode(),
    ]

    for index, content in enumerate(page_contents):
        page_object_number = 3 + (index * 2)
        content_object_number = page_object_number + 1
        objects.extend(
            [
                (
                    f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
                    f"/Resources << /Font << /F1 {font_object_number} 0 R >> >> "
                    f"/Contents {content_object_number} 0 R >>"
                ).encode(),
                f"<< /Length {len(content)} >>\nstream\n".encode()
                + content
                + b"\nendstream",
            ]
        )

    objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")

    pdf = b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n"
    offsets = [0]
    for object_number, obj in enumerate(objects, start=1):
        offsets.append(len(pdf))
        pdf += f"{object_number} 0 obj\n".encode() + obj + b"\nendobj\n"

    xref_offset = len(pdf)
    pdf += f"xref\n0 {len(objects) + 1}\n".encode()
    pdf += b"0000000000 65535 f \n"
    pdf += b"".join(f"{offset:010d} 00000 n \n".encode() for offset in offsets[1:])
    pdf += (
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
        f"startxref\n{xref_offset}\n%%EOF\n"
    ).encode()
    return pdf
