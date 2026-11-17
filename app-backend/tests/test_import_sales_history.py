from datetime import date, timedelta

import pytest

from app.application.dto import DailySales
from app.application.use_cases.import_sales_history import ImportSalesHistoryCsv
from app.domain.exceptions import InvalidSalesHistoryCsvError
from app.domain.rules import MAX_SALES_HISTORY_IMPORT_ROWS


class RecordingRepository:
    def __init__(self) -> None:
        self.product_id: int | None = None
        self.entries: list[DailySales] = []

    def upsert_many(self, product_id: int, entries: list[DailySales]) -> tuple[int, int]:
        self.product_id = product_id
        self.entries = list(entries)
        return len(entries), 0


def test_csv_import_parses_bom_and_normalizes_rows_before_persisting() -> None:
    repository = RecordingRepository()
    importer = ImportSalesHistoryCsv(repository)
    content = ("\ufeffsales_date,units_sold,had_promotion\n" "2026-10-01,12,false\n" "2026-10-02,8,TRUE\n").encode(
        "utf-8"
    )

    assert importer.execute(42, content) == (2, 0)
    assert repository.product_id == 42
    assert repository.entries == [
        DailySales(date(2026, 10, 1), 12, False),
        DailySales(date(2026, 10, 2), 8, True),
    ]


def test_csv_import_enforces_the_data_row_limit_before_persisting() -> None:
    repository = RecordingRepository()
    importer = ImportSalesHistoryCsv(repository)
    rows = [
        f"{date(2026, 1, 1) + timedelta(days=offset)},1,false" for offset in range(MAX_SALES_HISTORY_IMPORT_ROWS + 1)
    ]
    content = ("sales_date,units_sold,had_promotion\n" + "\n".join(rows) + "\n").encode()

    with pytest.raises(InvalidSalesHistoryCsvError):
        importer.execute(42, content)

    assert repository.entries == []


@pytest.mark.parametrize(
    "content",
    [
        b"wrong,headers,here\n2026-10-01,1,false\n",
        b"sales_date,units_sold,had_promotion\n2026-10-01,-1,false\n",
        b"sales_date,units_sold,had_promotion\n2026-10-01,1,yes\n",
        b"sales_date,units_sold,had_promotion\n2026-10-01,1,false\n2026-10-01,2,true\n",
        b"sales_date,units_sold,had_promotion\n2026-10-01,1,false,extra\n",
        b"sales_date,units_sold,had_promotion\n",
    ],
)
def test_csv_import_rejects_invalid_content_without_partial_persistence(content: bytes) -> None:
    repository = RecordingRepository()
    importer = ImportSalesHistoryCsv(repository)

    with pytest.raises(InvalidSalesHistoryCsvError):
        importer.execute(42, content)

    assert repository.entries == []
