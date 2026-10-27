import pytest
from datetime import date
from unittest.mock import Mock, MagicMock
from trusted_view.query import TrustedRatesQueryBuilder, MAJOR_CURRENCIES

class TestQueryBuilderConstruction:

    def test_builder_initialization(self):
        conn = Mock()
        builder = TrustedRatesQueryBuilder(conn)

        assert builder.conn == conn
        assert builder._filters == []
        assert builder._params == []
        assert builder._order_by == []
        assert builder._distinct_on is None
        assert builder._group_by is None

    def test_method_chaining_returns_self(self):
        conn = Mock()
        builder = TrustedRatesQueryBuilder(conn)

        result = (builder
                  .with_currency("USD")
                  .with_source(5)
                  .order_by_buying_rate())

        assert result is builder
        assert len(builder._filters) == 2
        assert len(builder._params) == 2

class TestLockedRulesEnforcement:

    def test_locked_rules_in_where_clause(self):
        conn = Mock()
        builder = TrustedRatesQueryBuilder(conn)
        where_clause = builder._build_where()

        assert "o.is_current = TRUE" in where_clause
        assert "o.identity_status != 'ambiguous'" in where_clause
        assert "o.validation_status != 'rejected'" in where_clause
        assert "o.category_id IS NOT NULL" in where_clause
        assert "rs.is_enabled = TRUE" in where_clause

    def test_locked_rules_cannot_be_bypassed(self):
        conn = Mock()
        builder = TrustedRatesQueryBuilder(conn)
        query = builder.get_sql()

        assert "o.is_current = TRUE" in query
        assert "o.validation_status != 'rejected'" in query

    def test_locked_rules_in_single_location(self):
        conn = Mock()
        builder = TrustedRatesQueryBuilder(conn)

        query1 = builder.get_sql()
        query2 = builder.get_sql()

        assert query1 == query2

class TestFilterMethods:

    def test_with_source(self):
        conn = Mock()
        builder = TrustedRatesQueryBuilder(conn).with_source(5)

        assert "o.source_id = %s" in builder._filters
        assert 5 in builder._params

    def test_with_currency(self):
        conn = Mock()
        builder = TrustedRatesQueryBuilder(conn).with_currency("usd")

        assert "o.source_currency_code = %s" in builder._filters
        assert "USD" in builder._params

    def test_with_category(self):
        conn = Mock()
        builder = TrustedRatesQueryBuilder(conn).with_category("transactional")

        assert "rc.code = %s" in builder._filters
        assert "transactional" in builder._params

    def test_major_currencies_only(self):
        conn = Mock()
        builder = TrustedRatesQueryBuilder(conn).major_currencies_only()

        assert "o.source_currency_code = ANY(%s)" in builder._filters
        assert list(MAJOR_CURRENCIES) in builder._params

    def test_with_date(self):
        conn = Mock()
        test_date = date(2026, 10, 14)
        builder = TrustedRatesQueryBuilder(conn).with_date(test_date)

        assert "o.effective_date = %s" in builder._filters
        assert test_date in builder._params

    def test_with_date_range(self):
        conn = Mock()
        start = date(2026, 10, 1)
        end = date(2026, 10, 14)
        builder = TrustedRatesQueryBuilder(conn).with_date_range(start, end)

        assert "o.effective_date BETWEEN %s AND %s" in builder._filters
        assert start in builder._params
        assert end in builder._params

    def test_multiple_filters_combined(self):
        conn = Mock()
        builder = (TrustedRatesQueryBuilder(conn)
                   .with_currency("USD")
                   .with_source(5))

        where_clause = builder._build_where()

        assert "o.source_currency_code = %s" in where_clause
        assert "o.source_id = %s" in where_clause
        assert "AND" in where_clause

class TestAggregationMethods:

    def test_best_per_bank(self):
        conn = Mock()
        builder = TrustedRatesQueryBuilder(conn).best_per_bank()
        query = builder.get_sql()

        assert "DISTINCT ON (rs.id)" in query
        assert "rs.id" in builder._order_by
        assert "o.buying_rate DESC NULLS LAST" in " ".join(builder._order_by)

    def test_best_per_currency(self):
        conn = Mock()
        builder = TrustedRatesQueryBuilder(conn).best_per_currency()
        query = builder.get_sql()

        assert "DISTINCT ON (o.source_currency_code)" in query
        assert "o.source_currency_code" in builder._order_by

    def test_group_by_date(self):
        conn = Mock()
        builder = TrustedRatesQueryBuilder(conn).group_by_date()

        assert builder._group_by == "o.effective_date"

    def test_group_by_bank(self):
        conn = Mock()
        builder = TrustedRatesQueryBuilder(conn).group_by_bank()

        assert builder._group_by == "rs.id, b.name"

class TestOrderingMethods:

    def test_order_by_buying_rate_desc(self):
        conn = Mock()
        builder = TrustedRatesQueryBuilder(conn).order_by_buying_rate(desc=True)
        order_clause = builder._build_order_by()

        assert "o.buying_rate DESC NULLS LAST" in order_clause

    def test_order_by_buying_rate_asc(self):
        conn = Mock()
        builder = TrustedRatesQueryBuilder(conn).order_by_buying_rate(desc=False)
        order_clause = builder._build_order_by()

        assert "o.buying_rate ASC NULLS LAST" in order_clause

    def test_order_by_bank_name(self):
        conn = Mock()
        builder = TrustedRatesQueryBuilder(conn).order_by_bank_name()
        order_clause = builder._build_order_by()

        assert "b.name" in order_clause

    def test_order_by_currency(self):
        conn = Mock()
        builder = TrustedRatesQueryBuilder(conn).order_by_currency()
        order_clause = builder._build_order_by()

        assert "o.source_currency_code" in order_clause

    def test_order_by_date_desc(self):
        conn = Mock()
        builder = TrustedRatesQueryBuilder(conn).order_by_date(desc=True)
        order_clause = builder._build_order_by()

        assert "o.effective_date DESC" in order_clause

    def test_order_by_date_asc(self):
        conn = Mock()
        builder = TrustedRatesQueryBuilder(conn).order_by_date(desc=False)
        order_clause = builder._build_order_by()

        assert "o.effective_date ASC" in order_clause

    def test_default_ordering(self):
        conn = Mock()
        builder = TrustedRatesQueryBuilder(conn)
        order_clause = builder._build_order_by()

        assert "b.name" in order_clause
        assert "rc.code" in order_clause
        assert "o.source_currency_code" in order_clause

class TestRowTransformation:

    def test_to_row_adds_computed_fields(self):
        conn = Mock()
        builder = TrustedRatesQueryBuilder(conn)

        cols = ["id", "source_verification_status"]
        row = (1, "provisional")

        result = builder._to_row(cols, row)

        assert result["id"] == 1
        assert result["source_verification_status"] == "provisional"
        assert result["is_provisional"] is True

    def test_is_provisional_for_verified_source(self):
        conn = Mock()
        builder = TrustedRatesQueryBuilder(conn)

        cols = ["source_verification_status"]
        row = ("verified",)

        result = builder._to_row(cols, row)
        assert result["is_provisional"] is False

    def test_is_provisional_for_unverified_source(self):
        conn = Mock()
        builder = TrustedRatesQueryBuilder(conn)

        cols = ["source_verification_status"]
        row = ("unverified",)

        result = builder._to_row(cols, row)
        assert result["is_provisional"] is True

    def test_is_provisional_for_provisional_source(self):
        conn = Mock()
        builder = TrustedRatesQueryBuilder(conn)

        cols = ["source_verification_status"]
        row = ("provisional",)

        result = builder._to_row(cols, row)
        assert result["is_provisional"] is True

class TestQueryInspection:

    def test_get_sql_returns_query_string(self):
        conn = Mock()
        builder = (TrustedRatesQueryBuilder(conn)
                   .with_currency("USD"))

        sql = builder.get_sql()

        assert isinstance(sql, str)
        assert "SELECT" in sql
        assert "WHERE" in sql
        assert "o.source_currency_code = %s" in sql

    def test_get_params_returns_parameters(self):
        conn = Mock()
        builder = (TrustedRatesQueryBuilder(conn)
                   .with_currency("USD")
                   .with_source(5))

        params = builder.get_params()

        assert params == ["USD", 5]

    def test_get_params_returns_copy(self):
        conn = Mock()
        builder = TrustedRatesQueryBuilder(conn).with_currency("USD")

        params1 = builder.get_params()
        params2 = builder.get_params()

        assert params1 == params2
        assert params1 is not params2

class TestQueryBuilding:

    def test_build_select_without_distinct(self):
        conn = Mock()
        builder = TrustedRatesQueryBuilder(conn)
        select = builder._build_select()

        assert select.startswith("SELECT")
        assert "DISTINCT ON" not in select
        assert "o.id" in select
        assert "o.buying_rate" in select

    def test_build_select_with_distinct(self):
        conn = Mock()
        builder = TrustedRatesQueryBuilder(conn).best_per_bank()
        select = builder._build_select()

        assert "DISTINCT ON (rs.id)" in select

    def test_build_joins_standard_pattern(self):
        conn = Mock()
        builder = TrustedRatesQueryBuilder(conn)
        joins = builder._build_joins()

        assert "FROM rate_observation o" in joins
        assert "JOIN rate_source rs" in joins
        assert "JOIN bank b" in joins
        assert "LEFT JOIN rate_category rc" in joins

    def test_build_query_complete(self):
        conn = Mock()
        builder = (TrustedRatesQueryBuilder(conn)
                   .with_currency("USD")
                   .order_by_buying_rate())

        query = builder._build_query()

        assert "SELECT" in query
        assert "FROM" in query
        assert "WHERE" in query
        assert "ORDER BY" in query

class TestSQLInjectionPrevention:

    def test_currency_filter_parameterized(self):
        conn = Mock()
        malicious_input = "USD'; DROP TABLE rate_observation; --"
        builder = TrustedRatesQueryBuilder(conn).with_currency(malicious_input)

        sql = builder.get_sql()
        params = builder.get_params()

        assert "o.source_currency_code = %s" in sql
        assert malicious_input.upper() in params
        assert "DROP TABLE" not in sql

    def test_source_filter_parameterized(self):
        conn = Mock()
        builder = TrustedRatesQueryBuilder(conn).with_source(5)

        sql = builder.get_sql()
        params = builder.get_params()

        assert "o.source_id = %s" in sql
        assert 5 in params
        assert "o.source_id = 5" not in sql

class TestExecutionMethods:

    def test_execute_calls_cursor(self):
        mock_cursor = MagicMock()
        mock_cursor.description = [("id",), ("name",)]
        mock_cursor.fetchall.return_value = [(1, "Test")]

        mock_conn = Mock()
        mock_conn.cursor.return_value.__enter__ = Mock(return_value=mock_cursor)
        mock_conn.cursor.return_value.__exit__ = Mock(return_value=False)

        builder = TrustedRatesQueryBuilder(mock_conn)

        builder._to_row = Mock(return_value={"id": 1, "name": "Test"})

        results = builder.execute()

        mock_conn.cursor.assert_called_once()
        mock_cursor.execute.assert_called_once()
        assert len(results) > 0

    def test_to_rows_transforms_all_rows(self):
        conn = Mock()
        builder = TrustedRatesQueryBuilder(conn)

        mock_cursor = Mock()
        mock_cursor.description = [("id",), ("source_verification_status",)]
        mock_cursor.fetchall.return_value = [
            (1, "verified"),
            (2, "provisional"),
            (3, "unverified"),
        ]

        results = builder._to_rows(mock_cursor)

        assert len(results) == 3
        assert results[0]["is_provisional"] is False
        assert results[1]["is_provisional"] is True
        assert results[2]["is_provisional"] is True

class TestComplexQueries:

    def test_best_per_bank_with_currency_filter(self):
        conn = Mock()
        builder = (TrustedRatesQueryBuilder(conn)
                   .with_currency("USD")
                   .best_per_bank())

        sql = builder.get_sql()
        params = builder.get_params()

        assert "DISTINCT ON (rs.id)" in sql
        assert "o.source_currency_code = %s" in sql
        assert "USD" in params

    def test_multiple_filters_with_ordering(self):
        conn = Mock()
        builder = (TrustedRatesQueryBuilder(conn)
                   .with_currency("EUR")
                   .with_source(5)
                   .order_by_buying_rate(desc=True)
                   .order_by_bank_name())

        sql = builder.get_sql()
        params = builder.get_params()

        assert "EUR" in params
        assert 5 in params
        assert "ORDER BY" in sql

    def test_date_range_with_major_currencies(self):
        conn = Mock()
        start = date(2026, 10, 1)
        end = date(2026, 10, 14)

        builder = (TrustedRatesQueryBuilder(conn)
                   .with_date_range(start, end)
                   .major_currencies_only())

        sql = builder.get_sql()
        params = builder.get_params()

        assert start in params
        assert end in params
        assert list(MAJOR_CURRENCIES) in params
