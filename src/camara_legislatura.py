from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import pandas as pd

from camara_client import CamaraApiClient


@dataclass(frozen=True)
class LegislaturePeriod:
    id_legislatura: int
    start_date: date
    end_date: date

    @property
    def years(self) -> list[int]:
        return list(range(self.start_date.year, self.end_date.year + 1))


def get_current_legislature_id(deputies_df: pd.DataFrame) -> int:
    if "idLegislatura" not in deputies_df.columns or deputies_df.empty:
        raise RuntimeError("Nao foi possivel identificar a legislatura atual.")

    return int(deputies_df["idLegislatura"].mode().iloc[0])


def get_legislature_period(
    client: CamaraApiClient,
    id_legislatura: int,
    reference_date: date | None = None,
) -> LegislaturePeriod:
    current_date = reference_date or date.today()
    payload = client.get(f"/legislaturas/{id_legislatura}")
    data = payload.get("dados", {})

    start_date = date.fromisoformat(data["dataInicio"])
    end_date = min(date.fromisoformat(data["dataFim"]), current_date)

    return LegislaturePeriod(
        id_legislatura=id_legislatura,
        start_date=start_date,
        end_date=end_date,
    )

