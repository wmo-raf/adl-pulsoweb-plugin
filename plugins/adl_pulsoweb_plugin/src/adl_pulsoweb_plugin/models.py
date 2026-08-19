from urllib.parse import urlparse

import requests
from adl.core.models import DataParameter, Unit
from adl.core.models import NetworkConnection, StationLink
from django.db import models
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from modelcluster.fields import ParentalKey
from wagtail.admin.panels import MultiFieldPanel, FieldPanel, InlinePanel
from wagtail.models import Orderable

from .client import CONTEXT_PATH, PulsoWebClient, category_for_status
from .validators import validate_start_date


class PulsoWebConnection(NetworkConnection):
    station_link_model_string_label = "adl_pulsoweb_plugin.PulsoWebStationLink"
    api_base_url = models.CharField(max_length=255, default="https://app.pulsonic.com/rest",
                                    verbose_name=_("API Base URL"))
    api_token = models.CharField(max_length=255, verbose_name=_("API Token"))

    panels = NetworkConnection.panels + [
        MultiFieldPanel([
            FieldPanel("api_base_url"),
            FieldPanel("api_token"),
        ], heading=_("PulsoWeb API Credentials")),
        InlinePanel("variable_mappings", label=_("Variable Mapping"), heading=_("Variable Mappings")),
    ]

    class Meta:
        verbose_name = _("PulsoWeb Connection")
        verbose_name_plural = _("PulsoWeb Connections")

    def get_api_client(self, use_cache=True, timeout=None, retries=None):
        """
        Returns a client for this connection's PulsoWeb API.

        The defaults reproduce the ingestion path's behaviour exactly, so
        nothing changes for existing deployments. Source checks pass
        use_cache=False, timeout=5, retries=0 to stay inside the diagnostic
        probe's budget and to avoid reading a cached context as evidence that
        the source is up.
        """

        return PulsoWebClient(
            self.api_base_url,
            self.api_token,
            self.id,
            use_cache=use_cache,
            timeout=timeout,
            retries=retries,
        )

    @property
    def source_host(self):
        """
        The host the data calls dial, for messages that must never carry a
        full URL.
        """

        return urlparse(self.api_base_url).hostname

    @property
    def context_path(self):
        """The URL path get_context() dials, for messages."""

        base_path = urlparse(self.api_base_url).path.rstrip("/")

        return f"{base_path}/{CONTEXT_PATH}/"

    def get_source_endpoint(self):
        """
        The (host, port) core's DNS -> TCP probe dials (layer 4).

        Returns None where the configured base URL names no host: a wrong
        host is far worse than no host, because it produces blocking layer-4
        failure evidence and sends the operator hunting a network fault that
        does not exist.
        """

        parsed = urlparse(self.api_base_url)

        if not parsed.hostname:
            return None

        return parsed.hostname, parsed.port or (443 if parsed.scheme == "https" else 80)

    def check_source(self):
        """
        Ask whether the source accepts our credentials and offers data
        (layer 5 of the ingestion diagnostic).
        """

        # Lazy: this module does not exist on a core release predating the
        # source-check contracts, and on such a core this method is never
        # called.
        from adl.core.source_checks import SourceCheckResult, SourceCheckStatus

        try:
            # Client construction is inside the guarded region, so a
            # configuration fault surfaces as a check failure rather than as
            # an unhandled exception.
            client = self.get_api_client(use_cache=False, timeout=5, retries=0)
            context = client.get_context()
        except requests.HTTPError as e:
            return SourceCheckResult(
                status=SourceCheckStatus.FAILED,
                category=category_for_status(e.response.status_code),
                message=_("%(host)s returned HTTP %(code)s for %(path)s.") % {
                    "host": self.source_host,
                    "code": e.response.status_code,
                    "path": self.context_path,
                },
            )
        except requests.exceptions.JSONDecodeError:
            # The host answered, so "could not be reached" would misdirect —
            # but a body that will not parse carries no code, so the category
            # is still declined.
            return SourceCheckResult(
                status=SourceCheckStatus.FAILED,
                message=_("%(host)s answered %(path)s with a body that was "
                          "not JSON.") % {
                    "host": self.source_host,
                    "path": self.context_path,
                },
            )
        except requests.RequestException as e:
            # The server sent no code — a connection error, a read timeout, a
            # body that would not parse. Decline the category.
            return SourceCheckResult(
                status=SourceCheckStatus.FAILED,
                message=_("%(host)s could not be reached: %(error)s") % {
                    "host": self.source_host,
                    "error": e,
                },
            )

        # OK is claimed from a parsed body carrying the key the call exists to
        # return, never a bare 2xx: an expired session that redirects to a
        # login page arrives as a clean 200.
        if not isinstance(context, dict) or "stations" not in context:
            return SourceCheckResult(
                status=SourceCheckStatus.FAILED,
                message=_("%(host)s answered but the response was not a "
                          "PulsoWeb context.") % {"host": self.source_host},
            )

        return SourceCheckResult(
            status=SourceCheckStatus.OK,
            message=_("%(host)s accepted our API token and returned "
                      "%(count)s station(s).") % {
                "host": self.source_host,
                "count": len(context["stations"]),
            },
        )

    def get_extra_model_admin_links(self):
        columns = [
            {
                "label": _("View Metadata"),
                "url": reverse("adl_pulsoweb_plugin_granularity", args=[self.id]),
                "icon_name": "list-ul",
                "kwargs": {"attrs": {"target": "_blank"}}
            }
        ]

        return columns

    @property
    def observation_codes(self):
        return [mapping.pulsoweb_parameter_code for mapping in self.variable_mappings.all()]


class PulsoWebVariableMapping(Orderable):
    network_pulsoweb = ParentalKey(PulsoWebConnection, on_delete=models.CASCADE, related_name="variable_mappings")
    adl_parameter = models.ForeignKey(DataParameter, on_delete=models.CASCADE, verbose_name=_("ADL Parameter"))
    pulsoweb_parameter_code = models.CharField(max_length=255, verbose_name=_("Pulsoweb Parameter Code"))
    pulsoweb_parameter_unit = models.ForeignKey(Unit, on_delete=models.CASCADE,
                                                verbose_name=_("Pulsoweb Parameter Unit"))

    panels = [
        FieldPanel("adl_parameter"),
        FieldPanel("pulsoweb_parameter_code"),
        FieldPanel("pulsoweb_parameter_unit"),
    ]

    @property
    def source_parameter_name(self):
        """
        Returns the shortcode of the PulsoWeb variable.
        """
        return self.pulsoweb_parameter_code

    @property
    def source_parameter_unit(self):
        """
        Returns the unit of the PulsoWeb variable.
        """
        return self.pulsoweb_parameter_unit


class PulsoWebStationLink(StationLink):
    pulsoweb_station_code = models.PositiveIntegerField(verbose_name=_("PulsoWeb Station ID"))
    start_date = models.DateTimeField(blank=True, null=True, validators=[validate_start_date],
                                      verbose_name=_("Start Date"),
                                      help_text=_("Start date for data pulling. Select a past date to include the "
                                                  "historical data. Leave blank for collecting realtime data only"), )

    panels = StationLink.panels + [
        FieldPanel("pulsoweb_station_code"),
        FieldPanel("start_date"),
    ]

    class Meta:
        verbose_name = _("PulsoWeb Station Link")
        verbose_name_plural = _("PulsoWeb Station Links")

    def __str__(self):
        return f"{self.pulsoweb_station_code} - {self.station} - {self.station.wigos_id}"

    def get_variable_mappings(self):
        """
        Returns the variable mappings for this station link.
        """

        connection = self.network_connection
        return connection.variable_mappings.all()

    def get_first_collection_date(self):
        """
        Returns the first collection date for this station link.
        Returns None if no start date is set.
        """
        return self.start_date
