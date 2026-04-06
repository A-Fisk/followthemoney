import csv
import io
from fastapi.responses import StreamingResponse


def csv_response(rows: list[dict], filename: str) -> StreamingResponse:
    """Return rows as a downloadable CSV StreamingResponse."""
    if not rows:
        content = ""
    else:
        buf = io.StringIO()
        writer = csv.DictWriter(buf, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
        content = buf.getvalue()

    return StreamingResponse(
        iter([content]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}.csv"'},
    )
