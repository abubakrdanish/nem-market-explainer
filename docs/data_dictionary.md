# Data dictionary

Columns whose meaning is not obvious from their name. Table layouts and sources are in [data_sources.md](data_sources.md).

## `raw.aemo_dispatchprice` flags

Both flags are integer codes, not booleans. Test them against zero, never `= 1`. The pipeline's predicates are `aemo.SUSPENDED` and `aemo.APC_SET` in `ingestion/aemo.py`, and `aemo.suspension_runs()` returns each region's unbroken runs of suspended intervals. Use pricing-run rows (`INTERVENTION = 0`) for analysis.

### `MARKETSUSPENDEDFLAG`

| Value | Meaning | Rows, July 2021 to September 2026 |
|---|---|---:|
| 0 | not suspended | 2,754,916 |
| 1 | suspended; exact meaning unconfirmed | 2,190 |
| 2 | suspended; exact meaning unconfirmed | 22,249 |

- **Suspended means non-zero.** The June 2022 suspension, from 14:05 on 15 June to 14:00 on 24 June in every region, is flagged 2 for the intervals ending up to 04:00 on 23 June and 1 after that. Filtering on `= 1` finds only the last 34 hours.
- **The flag is per region.** Most non-zero periods cover one region, so group by `regionid`.
- **What 1 and 2 mean is unconfirmed.** No AEMO documentation for the codes has been found. Do not describe a period as one kind of suspension or another from the code alone.
- **Only June 2022 has been checked against AEMO's announcements.** The other non-zero periods are listed in [data_sources.md](data_sources.md#the-june-2022-suspension). Until each is checked against a market notice, the explainer should say the archive flags the region as suspended, not that AEMO suspended the market.

### `APCFLAG`

Administered price cap flag. Values seen include 1, 4, 5, 8, 16, 17, 20, 21 and 24, which look like a bit field. What each bit means is unconfirmed.

- **Set means non-zero.** In June 2022, 10,834 rows are non-zero and only 348 equal 1.
- Do not decode individual bits until AEMO's definition is found.
