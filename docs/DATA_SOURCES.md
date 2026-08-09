# Data Sources

## OpenLigaDB

| Setting | Value |
|---|---|
| Competition | Bundesliga 2026/27 |
| League shortcut | `bl1` |
| Season parameter | `2026` |
| Authentication | None |
| Active client | `src/providers/openligadb.py` |
| Data license | Open Database License (ODbL) |

The runtime calls these endpoint families at `https://api.openligadb.de`:

```text
/getmatchdata/{league}/{season}
/getmatchdata/{league}/{season}/{matchday}
/getavailableteams/{league}/{season}
/getavailablegroups/{league}/{season}
/getbltable/{league}/{season}
/getlastchangedate/{league}/{season}/{matchday}
/getmatchdata/{match_id}
```

## Identity and teams

OpenLigaDB `MatchID` is provider fixture identity. Team provider IDs map to
canonical internal slugs in the local season registry. Display names may change
without becoming primary keys. Logo URLs are consumed as returned, cached by the
PWA for known current hosts, and replaced by initials if unavailable.

## Fixtures, results and standings

`matchDateTimeUTC` is parsed as aware UTC. Full-time scores are selected using
semantic result type (`resultTypeID == 2`, with named full-time fallback).
Missing values remain `null`. Production standings come from `/getbltable`; a
local recalculation exists only for diagnostics.

OpenLigaDB does not provide commercial play-by-play status. The payload exposes
only coarse states: provider-backed `FINISHED` plus derived `SCHEDULED`,
`LIVE_OR_ONGOING` and `UNKNOWN`. No elapsed minute is fabricated.

## Future data

Phase 8A may introduce a separate historical Bundesliga pipeline. No historical
provider, training window or model source has been selected or implemented yet.
Current competition truth remains OpenLigaDB.
