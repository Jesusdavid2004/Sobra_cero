import csv
from datetime import date
from io import StringIO

from pydantic import ValidationError

from app.application.dto import DailySales
from app.application.ports import SalesHistoryRepository
from app.domain.exceptions import InvalidSalesHistoryCsvError
from app.domain.rules import MAX_SALES_HISTORY_IMPORT_ROWS
from app.schemas import DailySalesCreate

EXPECTED_HEADERS = ("sales_date", "units_sold", "had_promotion")


class ImportSalesHistoryCsv:
    def __init__(self, repository: SalesHistoryRepository) -> None:
        self._repository = repository

    def execute(self, product_id: int, content: bytes) -> tuple[int, int]:
        try:
            text = content.decode("utf-8-sig")
            reader = csv.DictReader(StringIO(text, newline=""))
            headers = reader.fieldnames
            if headers is None or len(headers) != len(EXPECTED_HEADERS) or set(headers) != set(EXPECTED_HEADERS):
                raise InvalidSalesHistoryCsvError("CSV headers must be sales_date,units_sold,had_promotion")

            entries: list[DailySales] = []
            seen_dates: set[date] = set()
            for row_number, row in enumerate(reader, start=2):
                if row is None or all(value is None or not value.strip() for value in row.values()):
                    continue
                if None in row or any(value is None for value in row.values()):
                    raise InvalidSalesHistoryCsvError(f"CSV row {row_number} has an invalid number of columns")
                raw_date = row["sales_date"].strip()
                sales_date = date.fromisoformat(raw_date)
                if sales_date.isoformat() != raw_date:
                    raise ValueError("sales_date must use YYYY-MM-DD")
                promotion_text = row["had_promotion"].strip().lower()
                if promotion_text not in {"true", "false"}:
                    raise ValueError("had_promotion must be true or false")
                validated = DailySalesCreate(
                    sales_date=sales_date,
                    units_sold=int(row["units_sold"].strip()),
                    had_promotion=promotion_text == "true",
                )
                if validated.sales_date in seen_dates:
                    raise InvalidSalesHistoryCsvError(f"CSV row {row_number} repeats a sales date")
                seen_dates.add(validated.sales_date)
                entries.append(
                    DailySales(
                        sales_date=validated.sales_date,
                        units_sold=validated.units_sold,
                        had_promotion=validated.had_promotion,
                    )
                )
                if len(entries) > MAX_SALES_HISTORY_IMPORT_ROWS:
                    raise InvalidSalesHistoryCsvError(
                        f"CSV cannot contain more than {MAX_SALES_HISTORY_IMPORT_ROWS} data rows"
                    )
        except InvalidSalesHistoryCsvError:
            raise
        except (UnicodeDecodeError, csv.Error, ValueError, ValidationError) as exc:
            raise InvalidSalesHistoryCsvError("CSV contains an invalid sales-history row") from exc

        if not entries:
            raise InvalidSalesHistoryCsvError("CSV must contain at least one data row")
        return self._repository.upsert_many(product_id, entries)
