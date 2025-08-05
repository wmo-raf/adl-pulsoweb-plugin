import logging
from datetime import timedelta

from adl.core.registries import Plugin
from django.utils import timezone as dj_timezone

from .client import PulsoWebClient

logger = logging.getLogger(__name__)


class PulsoWebPlugin(Plugin):
    type = "adl_pulsoweb_plugin"
    label = "ADL Pulsoweb Plugin"
    
    def get_urls(self):
        return []
    
    def get_default_end_date(self, station_link):
        timezone = station_link.get_timezone()
        
        # get the end date(current time now) in the station timezone
        end_date = dj_timezone.localtime(timezone=timezone)
        # set to end_date of the current hour
        end_date = end_date.replace(minute=0, second=0, microsecond=0)
        
        return end_date
    
    def get_station_data(self, station_link, start_date=None, end_date=None):
        network_connection = station_link.network_connection
        network_conn_name = network_connection.name
        
        if start_date and end_date and end_date == start_date:
            end_date += timedelta(hours=1)
        
        logger.info(f"[ADL_PULSOWEB_PLUGIN] Starting data processing for {network_conn_name}.")
        
        pulsoweb_client = PulsoWebClient(
            network_connection.api_base_url,
            network_connection.api_token,
            network_connection.id
        )
        
        observation_codes = network_connection.observation_codes
        
        # PulsoWeb API expects dates as UTC string format
        start_date_str = start_date.strftime("%Y-%m-%dT%H:%M:%S")
        end_date_str = end_date.strftime("%Y-%m-%dT%H:%M:%S")
        
        station_code = station_link.pulsoweb_station_code
        
        records = pulsoweb_client.get_observation_data(station_code, observation_codes, start_date_str, end_date_str)
        
        return records
