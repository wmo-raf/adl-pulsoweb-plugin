"""
Tests for the ingestion-diagnostic contracts: ``get_source_endpoint()``,
``check_source()`` and ``check_station_source()``. See the "Ingestion
Diagnostic Contracts" page in the ADL developer guide.

Convention for everything added to this module: **the tests touch no
database**. Build model instances unsaved and stub the source client, so the
seam under test is exactly the contract core consumes. That means
``SimpleTestCase``, never ``TestCase`` — no fixtures, no per-test migrations.
Django still calls ``setup_databases()`` whatever the test class, so the suite
is run on this plugin's own compose stack with ``make test`` from the repo
root; "DB-free" is about what the tests touch, not where they run.

Surfaces this plugin declines get no test: asserting that core still returns
``UNSUPPORTED`` tests core, not this plugin.
"""

import ast
import datetime
import os
from unittest import mock

import requests
from adl.core.source_checks import SourceCheckStatus
from django.test import SimpleTestCase

from adl_pulsoweb_plugin.client import PulsoWebClient
from adl_pulsoweb_plugin.models import PulsoWebConnection, PulsoWebStationLink
from adl_pulsoweb_plugin.plugins import PulsoWebPlugin

CONTEXT = {"stations": [{"code": 5, "name": "Nairobi"}], "observations": [], "granularities": []}


def make_connection(api_base_url="https://app.pulsonic.com/rest"):
    """An unsaved connection. `id` is left None; nothing here reaches the DB."""

    return PulsoWebConnection(api_base_url=api_base_url, api_token="a-token")


def stub_client(connection, **behaviour):
    """
    Replaces the connection's client factory with one returning a stub, and
    records the arguments the check passed. `behaviour` is applied to the stub
    client's methods, e.g. get_context=mock.Mock(side_effect=...).
    """

    client = mock.Mock(spec=PulsoWebClient)

    for name, value in behaviour.items():
        setattr(client, name, value)

    factory = mock.Mock(return_value=client)
    connection.get_api_client = factory

    return client, factory


def http_error(status_code):
    response = requests.Response()
    response.status_code = status_code

    return requests.HTTPError(f"HTTP {status_code}", response=response)


class SourceEndpointTests(SimpleTestCase):
    """`get_source_endpoint()` names the host the data calls dial (layer 4)."""

    def test_https_defaults_to_443(self):
        connection = make_connection("https://app.pulsonic.com/rest")

        self.assertEqual(connection.get_source_endpoint(), ("app.pulsonic.com", 443))

    def test_http_defaults_to_80(self):
        connection = make_connection("http://app.pulsonic.com/rest")

        self.assertEqual(connection.get_source_endpoint(), ("app.pulsonic.com", 80))

    def test_explicit_port_wins(self):
        connection = make_connection("http://box.local:8080/rest")

        self.assertEqual(connection.get_source_endpoint(), ("box.local", 8080))

    def test_url_naming_no_host_returns_none(self):
        # A base URL saved without a scheme parses as a bare path. Naming a
        # wrong host is worse than naming none: it produces blocking layer-4
        # evidence for a network fault that does not exist.
        connection = make_connection("app.pulsonic.com/rest")

        self.assertIsNone(connection.get_source_endpoint())


class CheckSourceTests(SimpleTestCase):
    """`check_source()` asks whether the source accepts our credentials and
    offers data (layer 5, connection-scoped)."""

    def test_bypasses_the_cache_and_bounds_the_call(self):
        connection = make_connection()
        _, factory = stub_client(connection, get_context=mock.Mock(return_value=CONTEXT))

        connection.check_source()

        factory.assert_called_once_with(use_cache=False, timeout=5, retries=0)

    def test_parsed_context_is_ok_and_counts_the_stations(self):
        connection = make_connection()
        stub_client(connection, get_context=mock.Mock(return_value=CONTEXT))

        result = connection.check_source()

        self.assertEqual(result.status, SourceCheckStatus.OK)
        self.assertIsNone(result.category)
        self.assertIn("1 station(s)", result.message)

    def test_empty_station_list_is_still_ok(self):
        # The source accepted our token and answered with the key the call
        # exists to return. Zero is stated plainly and left to the operator.
        connection = make_connection()
        stub_client(connection, get_context=mock.Mock(return_value={"stations": []}))

        result = connection.check_source()

        self.assertEqual(result.status, SourceCheckStatus.OK)
        self.assertIn("0 station(s)", result.message)

    def test_body_without_the_expected_key_is_not_ok(self):
        # A bare 2xx proves nothing: an expired session redirects to a login
        # page and arrives as a clean 200.
        connection = make_connection()
        stub_client(connection, get_context=mock.Mock(return_value={"error": "nope"}))

        result = connection.check_source()

        self.assertEqual(result.status, SourceCheckStatus.FAILED)
        self.assertIsNone(result.category)

    def test_non_dict_body_is_not_ok(self):
        connection = make_connection()
        stub_client(connection, get_context=mock.Mock(return_value=["not", "a", "context"]))

        result = connection.check_source()

        self.assertEqual(result.status, SourceCheckStatus.FAILED)
        self.assertIsNone(result.category)

    def test_unparseable_body_names_the_host_it_reached(self):
        connection = make_connection()
        error = requests.exceptions.JSONDecodeError("Expecting value", "<html>", 0)
        stub_client(connection, get_context=mock.Mock(side_effect=error))

        result = connection.check_source()

        self.assertEqual(result.status, SourceCheckStatus.FAILED)
        self.assertIsNone(result.category)
        self.assertIn("not JSON", result.message)
        self.assertNotIn("could not be reached", result.message)

    def test_classified_statuses(self):
        for status_code, category in [
            (401, "AUTH_FAILED"),
            (403, "PERMISSION_DENIED"),
            (404, "PATH_NOT_FOUND"),
            (500, "PROTOCOL_ERROR"),
            (503, "PROTOCOL_ERROR"),
        ]:
            with self.subTest(status_code=status_code):
                connection = make_connection()
                stub_client(connection,
                            get_context=mock.Mock(side_effect=http_error(status_code)))

                result = connection.check_source()

                self.assertEqual(result.status, SourceCheckStatus.FAILED)
                self.assertEqual(result.category, category)
                self.assertIn(str(status_code), result.message)

    def test_declined_statuses(self):
        # 400 and 422 are our own malformed request, 429 is our polling
        # schedule, and a 3xx says nothing about the source. Any stamp would
        # blame the source for something it did not do.
        for status_code in (400, 422, 429, 302):
            with self.subTest(status_code=status_code):
                connection = make_connection()
                stub_client(connection,
                            get_context=mock.Mock(side_effect=http_error(status_code)))

                result = connection.check_source()

                self.assertEqual(result.status, SourceCheckStatus.FAILED)
                self.assertIsNone(result.category)

    def test_codeless_failure_declines_the_category(self):
        for error in (requests.ConnectionError("refused"),
                      requests.ReadTimeout("timed out")):
            with self.subTest(error=type(error).__name__):
                connection = make_connection()
                stub_client(connection, get_context=mock.Mock(side_effect=error))

                result = connection.check_source()

                self.assertEqual(result.status, SourceCheckStatus.FAILED)
                self.assertIsNone(result.category)

    def test_messages_name_the_host_and_path_and_never_the_token(self):
        connection = make_connection()
        stub_client(connection, get_context=mock.Mock(side_effect=http_error(401)))

        result = connection.check_source()

        self.assertIn("app.pulsonic.com", result.message)
        self.assertIn("/rest/get_context/", result.message)
        self.assertNotIn("a-token", result.message)
        self.assertNotIn("https://", result.message)


class CheckStationSourceTests(SimpleTestCase):
    """`check_station_source()` asks whether the operator's identifier
    resolves to a real station upstream (layer 5, station-scoped)."""

    def make_station_link(self, connection, code=5):
        station_link = PulsoWebStationLink(pulsoweb_station_code=code)
        station_link.network_connection = connection

        return station_link

    def test_bypasses_the_cache_and_bounds_the_call(self):
        # Unconditionally, over the whole check: a stale list produces a
        # confident false PATH_NOT_FOUND for a station added upstream since.
        connection = make_connection()
        _, factory = stub_client(
            connection, get_stations_metadata=mock.Mock(return_value=CONTEXT["stations"]))

        self.make_station_link(connection).check_station_source()

        factory.assert_called_once_with(use_cache=False, timeout=5, retries=0)

    def test_present_station_is_ok_and_echoes_the_upstream_label(self):
        # The label is what catches a valid-but-wrong identifier: a real
        # station ID belonging to a different site.
        connection = make_connection()
        stub_client(connection,
                    get_stations_metadata=mock.Mock(return_value=CONTEXT["stations"]))

        result = self.make_station_link(connection).check_station_source()

        self.assertEqual(result.status, SourceCheckStatus.OK)
        self.assertIsNone(result.category)
        self.assertIn("5", result.message)
        self.assertIn("Nairobi", result.message)

    def test_present_station_without_a_label_still_reports_ok(self):
        connection = make_connection()
        stub_client(connection,
                    get_stations_metadata=mock.Mock(return_value=[{"code": 5}]))

        result = self.make_station_link(connection).check_station_source()

        self.assertEqual(result.status, SourceCheckStatus.OK)
        self.assertIn("5", result.message)

    def test_identifier_matches_across_types(self):
        # The upstream code arrives as a string in some responses and an
        # integer in others; the configured value is always an integer.
        connection = make_connection()
        stub_client(connection,
                    get_stations_metadata=mock.Mock(return_value=[{"code": "5", "name": "Nairobi"}]))

        result = self.make_station_link(connection).check_station_source()

        self.assertEqual(result.status, SourceCheckStatus.OK)

    def test_absent_from_a_parsed_list_is_path_not_found(self):
        # Positive proof: the list was received and parsed, and this station
        # is not in it.
        connection = make_connection()
        stub_client(connection,
                    get_stations_metadata=mock.Mock(return_value=CONTEXT["stations"]))

        result = self.make_station_link(connection, code=99).check_station_source()

        self.assertEqual(result.status, SourceCheckStatus.FAILED)
        self.assertEqual(result.category, "PATH_NOT_FOUND")
        self.assertIn("99", result.message)

    def test_unreadable_list_fails_without_claiming_absence(self):
        # A failure to read the list proves nothing about this station, so it
        # must never be reported as PATH_NOT_FOUND — and never swallowed
        # into OK.
        for error in (http_error(500),
                      requests.ConnectionError("refused"),
                      requests.ReadTimeout("timed out")):
            with self.subTest(error=type(error).__name__):
                connection = make_connection()
                stub_client(connection,
                            get_stations_metadata=mock.Mock(side_effect=error))

                result = self.make_station_link(connection).check_station_source()

                self.assertEqual(result.status, SourceCheckStatus.FAILED)
                self.assertIsNone(result.category)

    def test_message_reports_the_identifier_and_not_the_url(self):
        connection = make_connection()
        stub_client(connection,
                    get_stations_metadata=mock.Mock(return_value=CONTEXT["stations"]))

        result = self.make_station_link(connection, code=99).check_station_source()

        self.assertNotIn("https://", result.message)
        self.assertNotIn("a-token", result.message)


class ClientTests(SimpleTestCase):
    """The client behaviour the checks and the classification rest on."""

    def make_response(self, status_code=200, body=None):
        response = mock.Mock()
        response.status_code = status_code
        response.json.return_value = body

        if status_code >= 400:
            response.raise_for_status.side_effect = http_error(status_code)
        else:
            response.raise_for_status.return_value = None

        return response

    def test_post_bounds_the_request(self):
        client = PulsoWebClient("https://app.pulsonic.com/rest", "a-token", 1)

        with mock.patch("requests.post", return_value=self.make_response(body={})) as post:
            client.post("get_context")

        self.assertIsNotNone(post.call_args.kwargs["timeout"])

    def test_post_raises_on_an_http_error(self):
        client = PulsoWebClient("https://app.pulsonic.com/rest", "a-token", 1)

        with mock.patch("requests.post", return_value=self.make_response(401)):
            with self.assertRaises(requests.HTTPError):
                client.post("get_context")

    def test_a_check_client_neither_reads_nor_writes_the_context_cache(self):
        from django.core.cache import cache

        cache.set("pulsoweb_context_1", {"stations": ["stale"]}, 60)
        self.addCleanup(cache.delete, "pulsoweb_context_1")

        client = PulsoWebClient("https://app.pulsonic.com/rest", "a-token", 1,
                                use_cache=False, timeout=5, retries=0)

        with mock.patch("requests.Session") as session:
            session.return_value.__enter__.return_value.post.return_value = \
                self.make_response(body=CONTEXT)
            context = client.get_context()

        self.assertEqual(context, CONTEXT)
        self.assertEqual(cache.get("pulsoweb_context_1"), {"stations": ["stale"]})

    def test_the_ingestion_client_still_uses_the_cache(self):
        from django.core.cache import cache

        cache.delete("pulsoweb_context_2")
        self.addCleanup(cache.delete, "pulsoweb_context_2")

        client = PulsoWebClient("https://app.pulsonic.com/rest", "a-token", 2)

        with mock.patch("requests.post", return_value=self.make_response(body=CONTEXT)) as post:
            client.get_context()
            client.get_context()

        self.assertEqual(post.call_count, 1)


class ExceptionStampingTests(SimpleTestCase):
    """`post()` is the single boundary every call routes through, and the one
    place holding the status code, so it is where the stamp lives."""

    def post_and_capture(self, status_code):
        client = PulsoWebClient("https://app.pulsonic.com/rest", "a-token", 1)

        response = mock.Mock()
        response.status_code = status_code
        response.raise_for_status.side_effect = http_error(status_code)

        with mock.patch("requests.post", return_value=response):
            with self.assertRaises(requests.HTTPError) as caught:
                client.post("get_context")

        return caught.exception

    def test_classified_statuses_are_stamped_at_layer_5(self):
        # A code from the server is proof the server answered, so every
        # category derived from one is layer 5.
        for status_code, category in [
            (401, "AUTH_FAILED"),
            (403, "PERMISSION_DENIED"),
            (404, "PATH_NOT_FOUND"),
            (500, "PROTOCOL_ERROR"),
            (502, "PROTOCOL_ERROR"),
        ]:
            with self.subTest(status_code=status_code):
                error = self.post_and_capture(status_code)

                self.assertEqual(error.adl_category, category)
                self.assertEqual(error.adl_layer, 5)

    def test_declined_statuses_are_left_unstamped(self):
        # Declining leaves core's read-time tier free to classify the row
        # later; a write-time stamp would suppress it permanently.
        for status_code in (400, 422, 429, 302):
            with self.subTest(status_code=status_code):
                error = self.post_and_capture(status_code)

                self.assertFalse(hasattr(error, "adl_category"))
                self.assertFalse(hasattr(error, "adl_layer"))

    def test_codeless_errors_propagate_unwrapped(self):
        # Core already resolves ConnectionError and ReadTimeout from the type
        # alone. Wrapping them in a plugin type would delete that.
        for error in (requests.ConnectionError("refused"),
                      requests.ReadTimeout("timed out")):
            with self.subTest(error=type(error).__name__):
                client = PulsoWebClient("https://app.pulsonic.com/rest", "a-token", 1)

                with mock.patch("requests.post", side_effect=error):
                    with self.assertRaises(type(error)) as caught:
                        client.post("get_context")

                self.assertFalse(hasattr(caught.exception, "adl_category"))


class ConnectionStub:
    """The connection as get_station_data() duck-types it: a name, a client
    factory and the configured observation codes. `observation_codes` is a
    property on the real model and reads variable mappings from the database,
    which these tests must not touch."""

    name = "PulsoWeb"
    observation_codes = ["TEMP", "RH"]

    def __init__(self, client):
        self.client = client
        self.get_api_client = mock.Mock(return_value=client)


class StationLinkStub:
    """A station link with no ORM behind it. Core re-initialises
    `adl_sources_count` to None at the start of every run."""

    def __init__(self, connection=None, code=5):
        self.network_connection = connection
        self.pulsoweb_station_code = code
        self.adl_sources_count = None


def observation_response(client, response):
    """Stubs the client's transport so get_observation_data() parses
    `response`."""

    return mock.patch.object(client, "post", return_value=response)


class SourcesCountTests(SimpleTestCase):
    """`adl_sources_count` says the source offered nothing, as distinct from
    us mishandling what it offered."""

    # Three raw items across two observation codes, collapsing into two
    # per-timestamp records.
    RESPONSE = {
        "TEMP": [{"date": "2026-08-19T10:00:00", "value": 21.0},
                 {"date": "2026-08-19T11:00:00", "value": 22.0}],
        "RH": [{"date": "2026-08-19T10:00:00", "value": 60.0}],
    }

    def get_data(self, response):
        client = PulsoWebClient("https://app.pulsonic.com/rest", "a-token", 1)

        with observation_response(client, response):
            return client.get_observation_data(5, ["TEMP", "RH"], "from", "to")

    def test_counts_raw_items_and_not_records(self):
        records, sources_count = self.get_data(self.RESPONSE)

        self.assertEqual(sources_count, 3)
        self.assertEqual(len(records), 2)

    def test_an_empty_response_counts_zero(self):
        records, sources_count = self.get_data({"TEMP": [], "RH": []})

        self.assertEqual(sources_count, 0)
        self.assertEqual(records, [])

    def make_plugin_call(self, station_link, response=None, error=None):
        client = mock.Mock(spec=PulsoWebClient)

        if error is not None:
            client.get_observation_data.side_effect = error
        else:
            client.get_observation_data.return_value = response

        station_link.network_connection = ConnectionStub(client)

        start = datetime.datetime(2026, 8, 19, 10, 0)
        end = datetime.datetime(2026, 8, 19, 11, 0)

        return PulsoWebPlugin().get_station_data(station_link, start, end)

    def test_the_count_is_assigned_in_get_station_data(self):
        station_link = StationLinkStub()

        self.make_plugin_call(station_link, response=([{"observation_time": None}], 3))

        self.assertEqual(station_link.adl_sources_count, 3)

    def test_the_count_accumulates_across_calls(self):
        station_link = StationLinkStub()

        self.make_plugin_call(station_link, response=([], 2))
        self.make_plugin_call(station_link, response=([], 4))

        self.assertEqual(station_link.adl_sources_count, 6)

    def test_an_answered_but_empty_response_commits_zero(self):
        station_link = StationLinkStub()

        self.make_plugin_call(station_link, response=([], 0))

        self.assertEqual(station_link.adl_sources_count, 0)

    def test_a_failed_call_leaves_the_count_unset(self):
        # None is the honest answer for a run that never got an answer: core
        # abstains on NULL, where a 0 would accuse the source of offering
        # nothing.
        station_link = StationLinkStub()

        with self.assertRaises(requests.ConnectionError):
            self.make_plugin_call(station_link, error=requests.ConnectionError("refused"))

        self.assertIsNone(station_link.adl_sources_count)

    def test_a_failure_after_a_successful_call_keeps_the_earlier_count(self):
        # A count above zero on a FAILED row acquits the source: we did see it
        # offering data before the run broke.
        station_link = StationLinkStub()

        self.make_plugin_call(station_link, response=([], 3))

        with self.assertRaises(requests.ConnectionError):
            self.make_plugin_call(station_link, error=requests.ConnectionError("refused"))

        self.assertEqual(station_link.adl_sources_count, 3)


class OlderCoreImportSafetyTests(SimpleTestCase):
    """The plugin must import cleanly on a core release that predates the
    source-check contracts, so nothing may import ``adl.core.source_checks``
    at module level.

    The contracts import it lazily instead, inside the method that needs it::

        def check_source(self):
            from adl.core.source_checks import SourceCheckResult
            ...

    Never wrap that import in ``try/except ImportError``: on an older core the
    method is never called, so the handler is unreachable, and it would turn a
    genuine import failure into a silent "this plugin does not support the
    check".
    """

    # Every module this plugin ships. Extend it as the plugin grows more.
    MODULES = ["models.py", "plugins.py", "client.py", "apps.py", "views.py",
               "validators.py", "wagtail_hooks.py"]

    DENIED = "adl.core.source_checks"

    def test_no_module_level_import_of_source_checks(self):
        package_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        for name in self.MODULES:
            path = os.path.join(package_dir, name)
            if not os.path.exists(path):
                continue  # a module this plugin does not (yet) ship
            with open(path) as f:
                tree = ast.parse(f.read())
            for node in ast.walk(tree):
                if not isinstance(node, (ast.Import, ast.ImportFrom)):
                    continue
                if node.col_offset != 0:
                    continue  # indented imports are lazy, inside a function
                names = [a.name for a in node.names]
                module = getattr(node, "module", "") or ""
                self.assertNotIn(
                    self.DENIED, [module] + names,
                    f"{name} imports {self.DENIED} at module level")
