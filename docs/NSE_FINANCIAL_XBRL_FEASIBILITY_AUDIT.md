# NSE Financial XBRL Feasibility Audit

Audit date: 2026-08-18. This is a feasibility gate, not a derived-metrics
implementation. Sources were the official NSE financial-results listing
(`corporates-financial-results`) and its `nsearchives.nseindia.com` XBRL links.
No raw financial filing was retained in the repository.

## Sample and coverage

The 20-symbol sample deliberately spans manufacturing (TATAMOTORS, ULTRACEMCO,
HINDALCO, SUNPHARMA), services (INFY, TCS, LTIM, INDHOTEL), banks (HDFCBANK,
SBIN, KOTAKBANK, ICICIBANK), NBFCs (BAJFINANCE, CHOLAFIN, M&MFIN,
SHRIRAMFIN), insurers (HDFCLIFE, SBILIFE), and SMEs (AEROENTER, KRISHIVAL).

14/20 symbols had an accessible NSE quarterly XBRL link. The unavailable
symbols were TATAMOTORS, LTIM, M&MFIN, HDFCLIFE, SBILIFE and KRISHIVAL. In
particular, both insurers had no accessible listing result/XBRL in this sample;
insurance metrics remain `UNKNOWN`, not zero or proxied.

The available records were quarterly and non-cumulative. Both consolidated and
non-consolidated series appear, so every future comparison must retain one
basis and never combine them. The listing exposes `exchdisstime` on all 14
accessible sample records (with broadcast/filing-time fallback available), so
it can provide a point-in-time `available_date`.

## Fact-level findings

| Requested metric | Exact facts observed | Period/basis and unit | Direct or derived | Coverage and decision |
|---|---|---|---|---|
| Revenue growth | `RevenueFromOperations` in ordinary Ind AS, SME and sampled NBFC filings; banks instead expose `RevenueOnInvestments` | Quarterly/non-cumulative; consolidated and standalone both occur; `INR` | Derived: `(current comparable revenue / prior-year same-quarter revenue - 1) * 100` | 10/20 direct `RevenueFromOperations`; possible only within the same taxonomy and basis. Do not use a banking income proxy as generic revenue. |
| PAT growth | `ProfitLossForPeriod` (ordinary Ind AS/NBFC/SME); `ProfitLossForThePeriod` and `ProfitLossAfterTaxesMinorityInterestAndShareOfProfitLossOfAssociates` (banking) | Quarterly/non-cumulative; `INR` | Derived comparable-period growth | 14/20 have a PAT-family fact. Candidate only after exact context, basis and comparable-period validation. |
| Operating margin | No common ordinary-company operating-profit fact. Banking has `OperatingProfitBeforeProvisionAndContingencies`, which is not comparable with industrial operating profit. | Quarterly/non-cumulative; `INR` | Would require reconciled operating profit / revenue | Not feasible generically. Remain `UNKNOWN`; never apply to banks, NBFCs or insurers. |
| Debt-to-equity | `DebtEquityRatio` occurred in ULTRACEMCO and in sampled NBFC filings; quarterly facts did not consistently expose total equity and borrowings for a defensible recomputation. | `pure` ratio where present | Direct only when taxonomy/basis is accepted; otherwise unavailable | Only 1 suitable non-financial sample had the direct ratio. No generic derived leverage metric. |
| Operating cash-flow quality | No cash-flow-from-operations fact in any of the 14 quarterly XBRLs inspected | Not available in this period type | Derived only from a cash-flow filing | 0/20. Remain `UNKNOWN` until a separately verified annual/cash-flow source is audited. |
| Annual/TTM ROE | No common `ReturnOnEquity` fact and no consistently usable total-equity fact in this quarterly sample | `INR` and `pure` appear, but scaling/decimals are fact-specific | Would require annual/TTM PAT and average total equity | 0/20 direct. Deferred pending a separate annual balance-sheet feasibility sample. |
| ROCE | No reconciled EBIT plus capital-employed fact pair | Not consistently available | Would require a documented reconciliation | 0/20. Explicitly deferred/`UNKNOWN`. |
| Earnings consistency | Comparable PAT-family facts recur in the 14 accessible histories | Quarterly, same basis required | Derived from a defined run of comparable periods | Feasible only after a basis-locked multi-period fact store is built; not implemented by this audit. |

All sampled filings used `INR`, `INRPerShare`, and/or `pure` unit references.
The numeric precision/scale is fact/context-specific (`decimals`), so a future
parser must preserve it and may not assume lakh/crore scaling at filing level.

## Taxonomy and sector controls

- Ordinary Ind AS, `BANKING_*`, and `NBFC_INDAS_*` taxonomies are not
  interchangeable. Banking operating profit is before provisions and
  contingencies; it is not an industrial operating-margin numerator.
- NBFC and insurance liabilities are part of the operating model. Generic
  debt-to-equity, operating margin and ROCE rules are prohibited for those
  sectors.
- Insurers had zero available sample XBRLs. They require a separate
  sector-specific source/taxonomy audit before any financial rule exists.

## Revisions and point-in-time policy

No listing record in the accessible 14-company feasibility subset carried a
revision marker, so revised-financial selection has not yet been empirically
validated. A future collector must retain filing ID, source URL, reporting
period, basis, and dissemination date; it must select the latest revision whose
availability is no later than the audit date. Until a revised fixture is
captured, revised financial results remain a release blocker.

## Gate decision

Do not implement financial derived metrics yet. The next permissible work is a
raw fact store plus deterministic context/basis/unit parser and a second audit
containing annual/cash-flow filings and at least one verified revision. Only
then may comparable revenue/PAT growth and earnings consistency be considered
for the eligible non-financial subset. ROCE remains deferred.
