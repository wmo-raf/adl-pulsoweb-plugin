import logging

from adl.core.models import ObservationRecord
from adl.core.registries import Plugin
from django.utils import timezone as dj_timezone

from .client import PulsoWebClient

logger = logging.getLogger(__name__)


class PulsoWebPlugin(Plugin):
    type = "adl_pulsoweb_plugin"
    label = "ADL Pulsoweb Plugin"
    
    client = None
    
    def get_urls(self):
        return []
    
    def get_data(self):
        network_conn_name = self.network_connection.name
        variable_mappings = self.network_connection.variable_mappings.all()
        
        if not variable_mappings:
            logger.warning(f"[ADL_PULSOWEB_PLUGIN] No variable mappings found for {network_conn_name}.")
            return
        
        logger.info(f"[ADL_PULSOWEB_PLUGIN] Starting data processing for {network_conn_name}.")
        
        station_links = self.network_connection.station_links.all()
        
        logger.debug(f"[ADL_PULSOWEB_PLUGIN] Found {len(station_links)} station links for {network_conn_name}.")
        
        self.client = PulsoWebClient(
            wsdl_url=self.network_connection.wsdl_url,
            username=self.network_connection.username,
            password=self.network_connection.password,
            station_id=self.network_connection.station_id
        )
        
        stations_records_count = {}
        
        for station_link in station_links:
            station_name = station_link.station.name
            
            if not station_link.enabled:
                logger.warning(f"[ADL_PULSOWEB_PLUGIN] Station link {station_name} is disabled.")
                continue
            
            logger.debug(f"[ADL_PULSOWEB_PLUGIN] Processing data for {station_name}.")
            
            station_link_records_count = self.process_station_link(station_link)
            
            stations_records_count[station_link.station.id] = station_link_records_count
        
        # close connection
        self.client.close()
        
        return stations_records_count
    
    def process_station_link(self, station_link):
        network_conn_name = self.network_connection.name
        station_name = station_link.station.name
        
        logger.debug(f"[ADL_PULSOWEB_PLUGIN] Getting latest data for {station_name}.")
        
        latest_record = self.client.get_station_latest_data(
            station_id=station_link.pulsoweb_station_id,
            param_type=self.network_connection.parameter_type,
            duration=self.network_connection.duration
        )
        
        timestamp = latest_record.get("TIMESTAMP")
        
        if not timestamp:
            logger.debug(f"[ADL_FTP_PLUGIN] No timestamp found in record {latest_record}")
            return
        
        utc_obs_date = dj_timezone.make_aware(timestamp, station_link.timezone)
        
        for variable_mapping in self.network_connection.variable_mappings.all():
            adl_parameter = variable_mapping.adl_parameter
            pulsoweb_parameter_name = variable_mapping.pulsoweb_parameter_name
            pulsoweb_parameter_unit = variable_mapping.pulsoweb_parameter_unit
            
            value = latest_record.get(pulsoweb_parameter_name)
            
            # is None or nan
            if value is None:
                logger.debug(f"[ADL_PULSOWEB_PLUGIN] No data record found for parameter {adl_parameter.name}")
                continue
            
            if adl_parameter.unit != pulsoweb_parameter_unit:
                value = adl_parameter.convert_value_from_units(value, pulsoweb_parameter_unit)
            
            record_data = {
                "station": station_link.station,
                "parameter": adl_parameter,
                "time": utc_obs_date,
                "value": value,
                "connection": station_link.network_connection,
            }
            
            ObservationRecord.objects.create(**record_data)
            
            return 1
