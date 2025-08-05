from adl.core.models import DataParameter, Unit
from adl.core.models import NetworkConnection, StationLink
from django.db import models
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from modelcluster.fields import ParentalKey
from timezone_field import TimeZoneField
from wagtail.admin.panels import MultiFieldPanel, FieldPanel, InlinePanel
from wagtail.models import Orderable

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
    timezone = TimeZoneField(default='UTC', verbose_name=_("Station Timezone"),
                             help_text=_("Timezone used by the station for recording observations"))
    start_date = models.DateTimeField(blank=True, null=True, validators=[validate_start_date],
                                      verbose_name=_("Start Date"),
                                      help_text=_("Start date for data pulling. Select a past date to include the "
                                                  "historical data. Leave blank for collecting realtime data only"), )
    
    panels = StationLink.panels + [
        FieldPanel("pulsoweb_station_code"),
        FieldPanel("timezone"),
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
    
    def get_timezone(self):
        """
        Returns the timezone for this station link.
        """
        return self.timezone
