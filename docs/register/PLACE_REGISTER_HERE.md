{
  "project": "Ethiopian Bank Exchange Rate Intelligence System",
  "register_status": "initial_source_investigation_completed",
  "verification_policy": "Do not treat an identified URL as a fully validated source. Preserve verification gaps explicitly.",
  "banks": [
    {
      "bank_name": "Commercial Bank of Ethiopia",
      "bank_code": "CBE",
      "sources": [
        {
          "source_name": "CBE Daily Exchange Rates API",
          "source_type": "api",
          "source_url": "https://combanketh.et/cbeapi/daily-exchange-rates/",
          "documentation_url": "https://combanketh.et/Exchange-rate-documentation",
          "http_method": "GET",
          "query_parameters": {
            "_limit": 1,
            "Date": "YYYY-MM-DD"
          },
          "available_categories": ["cash", "transactional"],
          "known_source_fields": {
            "currency_code": "currency.CurrencyCode",
            "currency_name": "currency.CurrencyName",
            "cash_buying": "cashBuying",
            "cash_selling": "cashSelling",
            "transactional_buying": "transactionalBuying",
            "transactional_selling": "transactionalSelling"
          },
          "mapping_status": "partially_verified",
          "requires_verification": [
            "Exact response structure and field types",
            "Publication and effective-date semantics",
            "Stable source record identifier",
            "Currency and rate-value validation",
            "Empty-response and error behavior",
            "Historical-date behavior"
          ]
        }
      ]
    },
    {
      "bank_name": "Dashen Bank",
      "bank_code": "DASHEN",
      "sources": [
        {
          "source_name": "Dashen Daily Exchange Rates",
          "source_type": "webpage",
          "source_url": "https://dashenbanksc.com/daily-exchange-rates/",
          "http_method": "GET",
          "available_categories": [
            "transactional",
            "cash",
            "weighted_average"
          ],
          "source_sections": [
            {
              "section_name": "Transactions Buying/Selling",
              "canonical_category": "transactional"
            },
            {
              "section_name": "Cash Buying/Selling",
              "canonical_category": "cash"
            },
            {
              "section_name": "Weighted Average Rate",
              "canonical_category": "weighted_average"
            }
          ],
          "mapping_status": "partially_verified",
          "requires_verification": [
            "Exact HTML selectors and table structure",
            "Buying and selling column mappings",
            "Currency labels and codes",
            "Publication date for each table",
            "Different effective dates between tables",
            "Behavior when a table is missing or malformed"
          ]
        }
      ]
    },
    {
      "bank_name": "Addis International Bank",
      "bank_code": "ADIB",
      "sources": [
        {
          "source_name": "Addis International Bank Exchange Rates API",
          "source_type": "api",
          "source_url": "https://api.addisbanksc.com/api/exchange-rates",
          "http_method": "GET",
          "available_categories": [],
          "known_source_fields": {},
          "mapping_status": "source_identified_schema_unverified",
          "requires_verification": [
            "Response structure and field names",
            "Currency code and name fields",
            "Buying and selling rate semantics",
            "Supported rate categories",
            "Publication and effective-date semantics",
            "Stable source record identifier",
            "Empty-response and error behavior"
          ]
        }
      ]
    },
    {
      "bank_name": "Abay Bank",
      "bank_code": "ABAY",
      "sources": [
        {
          "source_name": "Abay Bank Official Website",
          "source_type": "webpage",
          "source_url": "https://www.abaybanksc.com/",
          "http_method": "GET",
          "available_categories": [],
          "known_source_fields": {},
          "mapping_status": "source_identified_schema_unverified",
          "requires_verification": [
            "Exact exchange-rate page or endpoint",
            "Response format and table structure",
            "Currency and rate-category mappings",
            "Buying and selling columns",
            "Effective-date semantics"
          ]
        }
      ]
    },
    {
      "bank_name": "Bank of Abyssinia",
      "bank_code": "BOA",
      "sources": [
        {
          "source_name": "Bank of Abyssinia Exchange Rates",
          "source_type": "webpage",
          "source_url": "https://www.bankofabyssinia.com/exchange-rate-2/",
          "http_method": "GET",
          "available_categories": [],
          "known_source_fields": {},
          "mapping_status": "source_identified_schema_unverified",
          "requires_verification": [
            "Actual response and table structure",
            "Currency code mapping",
            "Rate categories and buying/selling semantics",
            "Effective date and update behavior"
          ]
        }
      ]
    },
    {
      "bank_name": "Ahadu Bank",
      "bank_code": "AHADU",
      "sources": [
        {
          "source_name": "Ahadu Bank Official Website",
          "source_type": "webpage",
          "source_url": "https://ahadubank.com/",
          "http_method": "GET",
          "available_categories": [],
          "known_source_fields": {},
          "mapping_status": "source_identified_schema_unverified",
          "requires_verification": [
            "Exact official exchange-rate page or endpoint",
            "Static HTML versus dynamically loaded data",
            "Rate categories and currency fields",
            "Effective-date semantics"
          ]
        }
      ]
    },
    {
      "bank_name": "Amhara Bank",
      "bank_code": "AMHARA",
      "sources": [
        {
          "source_name": "Amhara Bank Daily Exchange Rate",
          "source_type": "webpage",
          "source_url": "https://www.amharabank.com/daily-exchange-rate/",
          "http_method": "GET",
          "available_categories": [],
          "known_source_fields": {},
          "mapping_status": "source_identified_schema_unverified",
          "requires_verification": [
            "HTML table structure",
            "Currency and rate-category mapping",
            "Buying and selling columns",
            "Effective date and missing-value behavior"
          ]
        }
      ]
    },
    {
      "bank_name": "Awash Bank",
      "bank_code": "AWASH",
      "sources": [
        {
          "source_name": "Awash Bank AJAX Endpoint",
          "source_type": "ajax_endpoint",
          "source_url": "https://awashbank.com/wp-admin/admin-ajax.php",
          "http_method": "POST",
          "available_categories": [],
          "known_source_fields": {},
          "mapping_status": "endpoint_identified_request_unverified",
          "requires_verification": [
            "Required action and POST parameters",
            "How the official page constructs the request",
            "Required nonce or session values",
            "Response schema",
            "Currency and rate-category semantics",
            "Effective-date extraction",
            "Endpoint stability"
          ]
        }
      ]
    },
    {
      "bank_name": "Berhan Bank",
      "bank_code": "BERHAN",
      "sources": [
        {
          "source_name": "Berhan Bank Exchange Rates",
          "source_type": "webpage",
          "source_url": "https://berhanbanksc.com/exchange-rates/",
          "http_method": "GET",
          "available_categories": [],
          "known_source_fields": {},
          "mapping_status": "source_identified_schema_unverified",
          "requires_verification": [
            "HTML structure and selectors",
            "Currency and category fields",
            "Buying and selling columns",
            "Publication date"
          ]
        }
      ]
    },
    {
      "bank_name": "Bunna Bank",
      "bank_code": "BUNNA",
      "sources": [
        {
          "source_name": "Bunna Bank Foreign Exchange",
          "source_type": "webpage",
          "source_url": "https://bunnabanksc.com/foreign-exchange/",
          "http_method": "GET",
          "available_categories": [],
          "known_source_fields": {},
          "mapping_status": "source_identified_schema_unverified",
          "requires_verification": [
            "Actual response structure",
            "Currency and rate-category mappings",
            "Buying and selling semantics",
            "Effective-date extraction"
          ]
        }
      ]
    },
    {
      "bank_name": "Cooperative Bank of Oromia",
      "bank_code": "CBO",
      "sources": [
        {
          "source_name": "Cooperative Bank of Oromia Daily Exchange Rates",
          "source_type": "webpage",
          "source_url": "https://coopbankoromia.com.et/daily-exchange-rates/",
          "http_method": "GET",
          "query_parameters": {
            "er_date": "YYYY-MM-DD"
          },
          "available_categories": [],
          "known_source_fields": {},
          "mapping_status": "partially_verified",
          "requires_verification": [
            "Whether er_date is supported and how it behaves",
            "Actual HTML or JSON response structure",
            "Currency and rate-category fields",
            "Buying and selling mappings",
            "Historical-date availability",
            "Effective-date semantics"
          ]
        }
      ]
    },
    {
      "bank_name": "Development Bank of Ethiopia",
      "bank_code": "DBE",
      "sources": [
        {
          "source_name": "Development Bank of Ethiopia Official Website",
          "source_type": "webpage",
          "source_url": "https://dbe.com.et/",
          "http_method": "GET",
          "available_categories": [],
          "known_source_fields": {},
          "mapping_status": "source_identified_schema_unverified",
          "requires_verification": [
            "Whether an official exchange-rate publication exists",
            "Exact page or endpoint",
            "Supported rate categories",
            "Currency and date fields"
          ]
        }
      ]
    },
    {
      "bank_name": "Enat Bank",
      "bank_code": "ENAT",
      "sources": [
        {
          "source_name": "Enat Bank Official Website",
          "source_type": "webpage",
          "source_url": "https://www.enatbanksc.com/",
          "http_method": "GET",
          "available_categories": [],
          "known_source_fields": {},
          "mapping_status": "source_identified_schema_unverified",
          "requires_verification": [
            "Exact exchange-rate page or endpoint",
            "Response structure",
            "Currency and rate-category mappings",
            "Effective-date semantics"
          ]
        }
      ]
    },
    {
      "bank_name": "Gadaa Bank",
      "bank_code": "GADAA",
      "sources": [
        {
          "source_name": "Gadaa Bank Official Website",
          "source_type": "webpage",
          "source_url": "https://gadaabank.com.et/",
          "http_method": "GET",
          "available_categories": [],
          "known_source_fields": {},
          "mapping_status": "source_identified_schema_unverified",
          "requires_verification": [
            "Exact official exchange-rate page or endpoint",
            "Response format",
            "Currency and rate categories",
            "Effective-date extraction"
          ]
        }
      ]
    },
    {
      "bank_name": "Global Bank Ethiopia",
      "bank_code": "GLOBAL",
      "sources": [
        {
          "source_name": "Global Bank Ethiopia Official Website",
          "source_type": "webpage",
          "source_url": "https://www.globalbankethiopia.com/",
          "http_method": "GET",
          "available_categories": [],
          "known_source_fields": {},
          "mapping_status": "source_identified_schema_unverified",
          "requires_verification": [
            "Exact exchange-rate page or endpoint",
            "HTML or dynamic response structure",
            "Currency and rate-category mappings",
            "Publication-date semantics"
          ]
        }
      ]
    },
    {
      "bank_name": "Goh Betoch Bank",
      "bank_code": "GOH_BETOCH",
      "sources": [
        {
          "source_name": "Goh Betoch Today's Exchange Rate",
          "source_type": "webpage",
          "source_url": "https://www.gohbetbank.com/todays-exchange-rate/",
          "http_method": "GET",
          "available_categories": [],
          "known_source_fields": {},
          "mapping_status": "source_identified_schema_unverified",
          "requires_verification": [
            "HTML table structure",
            "Currency and rate-category fields",
            "Buying and selling columns",
            "Meaning of today's date",
            "Behavior when rates are not updated"
          ]
        }
      ]
    },
    {
      "bank_name": "Hibret Bank",
      "bank_code": "HIBRET",
      "sources": [
        {
          "source_name": "Hibret Bank Exchange Rate",
          "source_type": "webpage",
          "source_url": "https://www.hibretbank.com.et/about/exchange-rate/",
          "http_method": "GET",
          "available_categories": [],
          "known_source_fields": {},
          "mapping_status": "partially_verified",
          "requires_verification": [
            "Exact table structure",
            "Differences between the exchange-rate page and homepage",
            "Currency and rate-category mappings",
            "Effective-date semantics",
            "Missing or stale rate handling"
          ]
        }
      ]
    },
    {
      "bank_name": "Nib International Bank",
      "bank_code": "NIB",
      "sources": [
        {
          "source_name": "Nib International Bank Exchange Rate",
          "source_type": "webpage",
          "source_url": "https://www.nibbanksc.com/exchange-rate/",
          "http_method": "GET",
          "available_categories": [],
          "known_source_fields": {},
          "mapping_status": "source_identified_schema_unverified",
          "requires_verification": [
            "HTML structure and selectors",
            "Currency and rate-category mappings",
            "Buying and selling columns",
            "Effective date"
          ]
        }
      ]
    },
    {
      "bank_name": "Omo Bank",
      "bank_code": "OMO",
      "sources": [
        {
          "source_name": "Omo Bank Official Website",
          "source_type": "webpage",
          "source_url": "https://omobanksc.com/",
          "http_method": "GET",
          "available_categories": [],
          "known_source_fields": {},
          "mapping_status": "source_identified_schema_unverified",
          "requires_verification": [
            "Exact exchange-rate page or endpoint",
            "Response structure",
            "Currency and rate-category mappings",
            "Publication-date semantics"
          ]
        }
      ]
    },
    {
      "bank_name": "Oromia Bank",
      "bank_code": "OROMIA",
      "sources": [
        {
          "source_name": "Oromia Bank Ninja Tables AJAX Endpoint",
          "source_type": "ajax_endpoint",
          "source_url": "https://oromiabank.com/wp-admin/admin-ajax.php",
          "http_method": "POST",
          "known_request_parameters": {
            "action": "wp_ajax_ninja_tables_public_action",
            "table_id": "8233",
            "target_action": "get-all-data",
            "default_sorting": "old_first",
            "skip_rows": 0,
            "limit_rows": 0,
            "chunk_number": 0,
            "ninja_table_public_nonce": "previously_observed_dynamic_value"
          },
          "available_categories": [],
          "known_source_fields": {},
          "mapping_status": "endpoint_identified_request_unverified",
          "requires_verification": [
            "Actual current table ID",
            "How the official page obtains the nonce",
            "Required POST parameters",
            "Actual response schema",
            "Currency and rate-category mappings",
            "Effective-date semantics",
            "Pagination and ordering behavior"
          ]
        }
      ]
    },
    {
      "bank_name": "Rammis Bank",
      "bank_code": "RAMMIS",
      "sources": [
        {
          "source_name": "Rammis Latest Exchange Rates API",
          "source_type": "api",
          "source_url": "https://rammisbank.et/api/v1/exchange-rates/latest?base_currency=ETB",
          "http_method": "GET",
          "query_parameters": {
            "base_currency": "ETB"
          },
          "available_categories": [],
          "known_source_fields": {},
          "mapping_status": "partially_verified",
          "requires_verification": [
            "Actual response schema and field types",
            "Currency orientation and base-currency semantics",
            "Buying and selling definitions",
            "Rate categories",
            "Effective-date semantics",
            "Consistency with the official visible page"
          ]
        }
      ]
    },
    {
      "bank_name": "Sidama Bank",
      "bank_code": "SIDAMA",
      "sources": [
        {
          "source_name": "Sidama Bank Exchange Rate",
          "source_type": "webpage",
          "source_url": "https://sidamabanksc.com/exchange-rate/",
          "http_method": "GET",
          "available_categories": [],
          "known_source_fields": {},
          "mapping_status": "source_identified_schema_unverified",
          "requires_verification": [
            "HTML table structure",
            "Currency and rate-category mappings",
            "Buying and selling columns",
            "Effective-date semantics"
          ]
        }
      ]
    },
    {
      "bank_name": "Siinqee Bank",
      "bank_code": "SIINQEE",
      "sources": [
        {
          "source_name": "Siinqee Bank Official Website",
          "source_type": "webpage",
          "source_url": "https://siinqeebank.com/",
          "http_method": "GET",
          "available_categories": [],
          "known_source_fields": {},
          "mapping_status": "source_identified_schema_unverified",
          "requires_verification": [
            "Exact exchange-rate page or endpoint",
            "Response structure",
            "Currency and rate-category mappings",
            "Effective-date semantics"
          ]
        }
      ]
    },
    {
      "bank_name": "Siket Bank",
      "bank_code": "SIKET",
      "sources": [
        {
          "source_name": "Siket Bank Exchange Rate",
          "source_type": "webpage",
          "source_url": "https://siketbank.com/exchange-rate",
          "http_method": "GET",
          "available_categories": [],
          "known_source_fields": {},
          "mapping_status": "source_identified_schema_unverified",
          "requires_verification": [
            "HTML structure and selectors",
            "Currency and rate-category fields",
            "Buying and selling columns",
            "Effective-date extraction"
          ]
        }
      ]
    },
    {
      "bank_name": "Tsedey Bank",
      "bank_code": "TSEDEY",
      "sources": [
        {
          "source_name": "Tsedey Bank Official Website",
          "source_type": "webpage",
          "source_url": "https://www.tsedeybank.com.et/",
          "http_method": "GET",
          "available_categories": [],
          "known_source_fields": {},
          "mapping_status": "source_identified_schema_unverified",
          "requires_verification": [
            "Exact exchange-rate page or endpoint",
            "Response structure",
            "Currency and rate-category mappings",
            "Effective-date semantics"
          ]
        }
      ]
    },
    {
      "bank_name": "Tsehay Bank",
      "bank_code": "TSEHAY",
      "sources": [
        {
          "source_name": "Tsehay Bank Exchange Rate",
          "source_type": "webpage",
          "source_url": "https://tsehaybank.com.et/exchange-rate/",
          "http_method": "GET",
          "available_categories": [],
          "known_source_fields": {},
          "mapping_status": "source_identified_schema_unverified",
          "requires_verification": [
            "HTML table structure",
            "Currency and rate-category mappings",
            "Buying and selling columns",
            "Effective-date extraction"
          ]
        }
      ]
    },
    {
      "bank_name": "Wegagen Bank",
      "bank_code": "WEGAGEN",
      "sources": [
        {
          "source_name": "Wegagen Strapi Exchange Rates API",
          "source_type": "api",
          "source_url": "https://weg.back.strapi.wegagen.com/api/exchange-rates?populate=*",
          "http_method": "GET",
          "available_categories": [],
          "known_source_fields": {},
          "mapping_status": "partially_verified",
          "requires_verification": [
            "Actual JSON schema and nested fields",
            "Currency and rate-category mappings",
            "Buying and selling semantics",
            "Effective-date extraction",
            "Intermittent failure handling",
            "Consistency with the official published page"
          ]
        }
      ]
    },
    {
      "bank_name": "ZamZam Bank",
      "bank_code": "ZAMZAM",
      "sources": [
        {
          "source_name": "ZamZam Bank Exchange Rates",
          "source_type": "webpage",
          "source_url": "https://zamzambank.com/exchange-rates/",
          "http_method": "GET",
          "available_categories": [],
          "known_source_fields": {},
          "mapping_status": "source_identified_schema_unverified",
          "requires_verification": [
            "HTML structure and selectors",
            "Currency and rate-category mappings",
            "Buying and selling columns",
            "Effective-date semantics"
          ]
        }
      ]
    },
    {
      "bank_name": "Zemen Bank",
      "bank_code": "ZEMEN",
      "sources": [
        {
          "source_name": "Zemen Bank Exchange Rates",
          "source_type": "webpage",
          "source_url": "https://zemenbank.com/exchange-rates/",
          "http_method": "GET",
          "available_categories": [],
          "known_source_fields": {},
          "mapping_status": "partially_verified",
          "requires_verification": [
            "Underlying AJAX request and request parameters",
            "Actual response schema",
            "Transaction, cash, and weighted-average table mapping",
            "Currency and buying/selling fields",
            "Effective-date semantics",
            "Consistency between visible page and returned data"
          ]
        }
      ]
    },
    {
      "bank_name": "Anbesa International Bank",
      "bank_code": "ANBESA",
      "sources": [
        {
          "source_name": "Third-Party Exchange Rate Mirror",
          "source_type": "third_party_mirror",
          "source_url": "https://kehulum.com/exchange-rate/lion--anbesa-international-bank-sc-114",
          "http_method": "GET",
          "available_categories": [],
          "known_source_fields": {},
          "mapping_status": "official_source_unresolved",
          "requires_verification": [
            "Identify the bank's official exchange-rate publication",
            "Determine whether an official API or webpage exists",
            "Do not use the mirror as an authoritative source without an explicit fallback policy"
          ]
        }
      ]
    },
    {
      "bank_name": "Shabelle Bank",
      "bank_code": "SHABELLE",
      "sources": [
        {
          "source_name": "Third-Party Exchange Rate Mirror",
          "source_type": "third_party_mirror",
          "source_url": "https://kehulum.com/exchange-rate/shabelle-bank-sc-129",
          "http_method": "GET",
          "available_categories": [],
          "known_source_fields": {},
          "mapping_status": "official_source_unresolved",
          "requires_verification": [
            "Identify the bank's official exchange-rate publication",
            "Determine whether an official API or webpage exists",
            "Do not use the mirror as an authoritative source without an explicit fallback policy"
          ]
        }
      ]
    },
    {
      "bank_name": "Hijra Bank",
      "bank_code": "HIJRA",
      "sources": [],
      "mapping_status": "official_source_unresolved",
      "requires_verification": [
        "Identify the official exchange-rate page or API",
        "Confirm whether exchange rates are publicly published",
        "Determine the available rate categories and effective-date semantics"
      ]
    }
  ],
  "canonical_categories": [
    "cash",
    "transactional",
    "weighted_average",
    "indicative_reference",
    "other"
  ],
  "mapping_rules": {
    "unknown_currency": "flag_for_review",
    "unknown_category": "flag_for_review",
    "ambiguous_publication_identity": "preserve_and_flag",
    "changed_values": "require_change_review",
    "identical_normalized_snapshot": "deduplicate",
    "unverified_field_mapping": "do_not_assume",
    "missing_rate": "preserve_as_missing_not_zero",
    "missing_effective_date": "mark_date_unresolved",
    "third_party_data": "keep_separate_from_official_bank_data",
    "failed_collection": "record_failure_without_replacing_last_valid_observation",
    "different_table_effective_dates": "preserve_date_per_table_or_observation",
    "suspicious_rate_change": "flag_for_review_not_automatically_reject"
  },
  "verification_status_definitions": {
    "documented": "An official interface is documented; live data correctness may still require validation.",
    "source_identified_schema_unverified": "A candidate official source has been identified, but its actual response mapping is not confirmed.",
    "endpoint_identified_request_unverified": "An endpoint is known, but its required request details and response schema remain unverified.",
    "partially_verified": "Some source behavior or fields are known, but important mapping or correctness checks remain.",
    "validated": "Actual responses have been checked against official published values across multiple currencies, categories, and dates where possible.",
    "official_source_unresolved": "An authoritative bank-controlled source has not been established."
  }
}