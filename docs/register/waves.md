# Source register: scope and rollout waves

The source register is a source list with statuses, not a field-level mapping. Of 32 banks, only CBE has field names recorded, none is `validated` or `documented`, and 3 have no authoritative source yet.

| Register status | Count | Banks |
| --- | --- | --- |
| partially_verified | 7 | CBE, Dashen, Cooperative Bank of Oromia, Hibret, Rammis, Wegagen, Zemen |
| endpoint_identified_request_unverified | 2 | Awash, Oromia |
| source_identified_schema_unverified | 20 | Addis, Abay, Bank of Abyssinia, Ahadu, Amhara, Berhan, Bunna, DBE, Enat, Gadaa, Global, Goh Betoch, Nib, Omo, Sidama, Siinqee, Siket, Tsedey, Tsehay, ZamZam |
| official_source_unresolved | 3 | Anbesa, Shabelle, Hijra |

## Proposed rollout in waves
Ordered by how much is already known. The agent may confirm or change this in its kickoff plan.

| Wave | Banks | Why this order |
| --- | --- | --- |
| 1 | CBE, Dashen, Addis | The handoff scope; URLs are known and Addis already has a capture |
| 2 | Rammis, Wegagen, Zemen, Cooperative Bank of Oromia, Hibret | Partially verified, mostly JSON or a known rate page |
| 3 | Amhara, Berhan, Bunna, Bank of Abyssinia, Goh Betoch, Nib, Sidama, Siket, Tsehay, ZamZam | A specific rate page URL is known; likely a shared HTML table adapter family |
| 4 | Abay, Ahadu, DBE, Enat, Gadaa, Global, Omo, Siinqee, Tsedey | Only a homepage is known; the rate page or endpoint must be found first |
| 5 | Awash, Oromia, Anbesa, Shabelle, Hijra | POST endpoints needing a nonce, or no official source established |

## Register observations (resolved by docs/decisions/defaults.md)
- The register lists a fifth category `other`; the handoff approved four (default 1).
- Anbesa and Shabelle use a third-party mirror (default 2).
- The register's six mapping statuses differ from the handoff's four verification statuses (default 14).
- Hijra puts its status at bank level because it has no sources; normalize on import.
- Oromia's `action` value looks like a WordPress hook name, not a request parameter, and Oromia and Awash need a nonce (default 15).
- CBE lists an unexplained `_limit: 1` parameter (default 16).
- The Addis entry predates the 2026-10-10 capture (default 18).
- No National Bank of Ethiopia source appears (default 17).
