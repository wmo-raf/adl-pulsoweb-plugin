import logging
from datetime import timedelta

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
        
        self.client = PulsoWebClient(self.network_connection.api_base_url, self.network_connection.api_token,
                                     self.network_connection.id)
        
        stations_records_count = {}
        
        for station_link in station_links:
            station_name = station_link.station.name
            
            if not station_link.enabled:
                logger.warning(f"[ADL_PULSOWEB_PLUGIN] Station link {station_name} is disabled.")
                continue
            
            logger.debug(f"[ADL_PULSOWEB_PLUGIN] Processing data for {station_name}.")
            
            station_link_records_count = self.process_station_link(station_link)
            
            stations_records_count[station_link.station.id] = station_link_records_count
        
        return stations_records_count
    
    def process_station_link(self, station_link):
        station_name = station_link.station.name
        observation_codes = self.network_connection.observation_codes
        
        logger.debug(f"[ADL_PULSOWEB_PLUGIN] Getting latest data for {station_name}.")
        
        station_code = station_link.pulsoweb_station_code
        station_timezone = station_link.timezone
        
        # get the end date(current time now) in the station timezone
        end_date = dj_timezone.localtime(timezone=station_timezone)
        # set to end_date of the current hour
        end_date = end_date.replace(minute=0, second=0, microsecond=0)
        
        # use the start date of the station link if available
        if station_link.start_date:
            start_date = dj_timezone.localtime(station_link.start_date, timezone=station_timezone)
        else:
            # if not available, set the start date to 1 hour before the end date
            start_date = end_date - timedelta(hours=1)
        
        # pulsoweb API expects dates as UTC string format
        start_date_str = start_date.strftime("%Y-%m-%dT%H:%M:%S")
        end_date_str = end_date.strftime("%Y-%m-%dT%H:%M:%S")
        
        records = self.client.get_observation_data(station_code, observation_codes, start_date_str, end_date_str)
        
        observation_records = []
        
        for record in records:
            timestamp = record.get("TIMESTAMP")
            
            if not timestamp:
                logger.debug(f"[ADL_FTP_PLUGIN] No timestamp found in record {record}")
                return
            
            utc_obs_date = dj_timezone.make_aware(timestamp, station_link.timezone)
            
            for variable_mapping in self.network_connection.variable_mappings.all():
                adl_parameter = variable_mapping.adl_parameter
                pulsoweb_parameter_code = variable_mapping.pulsoweb_parameter_code
                pulsoweb_parameter_unit = variable_mapping.pulsoweb_parameter_unit
                
                value = record.get(pulsoweb_parameter_code)
                
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
                
                param_obs_record = ObservationRecord(**record_data)
                observation_records.append(param_obs_record)
        
        records_count = len(observation_records)
        
        if observation_records:
            logger.debug(f"[ADL_PULSOWEB_PLUGIN] Saving {records_count} records for {station_name}.")
            ObservationRecord.objects.bulk_create(
                observation_records,
                update_conflicts=True,
                update_fields=["value"],
                unique_fields=["station", "parameter", "time", "connection"]
            )
        
        return records_count
