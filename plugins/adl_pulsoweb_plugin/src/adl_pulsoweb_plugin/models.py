from adl.core.models import DataParameter, Unit
from adl.core.models import NetworkConnection, StationLink
from django.db import models
from django.utils.translation import gettext_lazy as _
from modelcluster.fields import ParentalKey
from timezone_field import TimeZoneField
from wagtail.admin.panels import MultiFieldPanel, FieldPanel, InlinePanel
from wagtail.models import Orderable


class PulsoWebConnection(NetworkConnection):
    station_link_model_string_label = "adl_pulsoweb_plugin.PulsoWebStationLink"
    
    wsdl_url = models.CharField(max_length=255, verbose_name=_("WSDL URL"))
    username = models.CharField(max_length=255, verbose_name=_("Username"))
    password = models.CharField(max_length=255, verbose_name=_("Password"))
    station_id = models.CharField(max_length=255, verbose_name=_("Station ID"))
    
    duration = models.IntegerField(verbose_name=_("Duration"), default=1440)
    parameter_type = models.CharField(max_length=100, verbose_name=_("Parameter Type"), default="H")
    
    panels = NetworkConnection.panels + [
        MultiFieldPanel([
            FieldPanel("wsdl_url"),
            FieldPanel("username"),
            FieldPanel("password"),
            FieldPanel("station_id"),
        ], heading=_("PulsoWeb WSDL Credentials")),
        InlinePanel("variable_mappings", label=_("Variable Mapping"), heading=_("Variable Mappings")),
    ]
    
    class Meta:
        verbose_name = _("PulsoWeb Connection")
        verbose_name_plural = _("PulsoWeb Connections")


class PulsoWebVariableMapping(Orderable):
    network_pulsoweb = ParentalKey(PulsoWebConnection, on_delete=models.CASCADE, related_name="variable_mappings")
    adl_parameter = models.ForeignKey(DataParameter, on_delete=models.CASCADE, verbose_name=_("ADL Parameter"))
    pulsoweb_parameter_name = models.CharField(max_length=255, verbose_name=_("Pulsoweb Parameter Name"))
    pulsoweb_parameter_unit = models.ForeignKey(Unit, on_delete=models.CASCADE,
                                                verbose_name=_("Pulsoweb Parameter Unit"))
    
    panels = [
        FieldPanel("adl_parameter"),
        FieldPanel("pulsoweb_parameter_name"),
        FieldPanel("pulsoweb_parameter_unit"),
    ]


class PulsoWebStationLink(StationLink):
    pulsoweb_station_id = models.CharField(max_length=255, verbose_name=_("PulsoWeb Station ID"))
    timezone = TimeZoneField(default='UTC', verbose_name=_("Station Timezone"),
                             help_text=_("Timezone used by the station for recording observations"))
    
    panels = StationLink.panels + [
        FieldPanel("pulsoweb_station_id"),
        FieldPanel("timezone"),
    ]
    
    class Meta:
        verbose_name = _("PulsoWeb Station Link")
        verbose_name_plural = _("PulsoWeb Station Links")
    
    def __str__(self):
        return f"{self.pulsoweb_station_id} - {self.station} - {self.station.wigos_id}"
