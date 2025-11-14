import datetime

import requests
from django.core.cache import cache


class PulsoWebConnectionError(Exception):
    pass


class PulsoWebClient:
    def __init__(self, baseurl, token, connection_id):
        self.baseurl = baseurl
        self.token = token
        self.connection_id = connection_id
    
    def get_observations_metadata(self):
        context = self.get_context()
        observations = context["observations"]
        
        return observations
    
    def get_granularities_metadata(self):
        context = self.get_context()
        
        granularities = context["granularities"]
        return granularities
    
    def get_stations_metadata(self):
        context = self.get_context()
        stations = context["stations"]
        return stations
    
    def get_observations_for_granular(self, gran_code, include_stations_count=True):
        observations_list = self.get_observations_metadata()
        gran_obs_list = []
        
        for obs in observations_list:
            if str(obs["granularity"]) == str(gran_code):
                gran_obs = {
                    "code": obs["code"],
                    "label": obs["label"],
                    "unit": obs["unit"],
                    "description": obs["description"],
                }
                if include_stations_count:
                    stations_count = len(self.get_stations_with_obs(obs["code"]))
                    gran_obs["stations_count"] = stations_count
                gran_obs_list.append(gran_obs)
        
        if include_stations_count:
            # sort by stations count
            gran_obs_list = sorted(gran_obs_list, key=lambda x: x["stations_count"], reverse=True)
        
        return gran_obs_list
    
    def get_stations_with_obs(self, obs_code):
        stations = self.get_stations_metadata()
        obs_stations = []
        for station in stations:
            if obs_code in station["observations"]:
                station_info = {
                    "code": station["code"],
                    "name": station["name"],
                }
                obs_stations.append(station_info)
        
        # sort by name
        # obs_stations = sorted(obs_stations, key=lambda x: x["name"], reverse=True)
        
        return obs_stations
    
    def get_stations_for_granularity(self, gran_code):
        observations = self.get_observations_for_granular(gran_code)
        
        stations = []
        
        for obs in observations:
            obs_code = obs["code"]
            obs_stations = self.get_stations_with_obs(obs_code)
            stations.extend(obs_stations)
        
        return stations
    
    def get_structured_data(self):
        gran_metadata = self.get_granularities_metadata()
        
        data = []
        
        for gran in gran_metadata:
            gran_data = {
                "granularity": gran,
                "stations": [],
            }
            
            gran_code = gran["code"]
            observations = self.get_observations_for_granular(gran_code)
            
            for obs in observations:
                obs_code = obs["code"]
                stations = self.get_stations_with_obs(obs_code)
                
                for station in stations:
                    gran_data["stations"].append({
                        "code": station["code"],
                        "name": station["name"],
                    })
            
            data.append(gran_data)
        
        return data
    
    def get_observation_by_code(self, obs_code):
        observations = self.get_observations_metadata()
        
        for obs in observations:
            if obs["code"] == obs_code:
                return obs
        
        return None
    
    def post(self, path, payload=None):
        if payload is None:
            payload = {}
        
        payload = {
            "key": self.token,
            **payload
        }
        
        url = f"{self.baseurl}/{path}/"
        response = requests.post(url, json=payload)
        return response.json()
    
    def get_granularities(self):
        context = self.get_context()
        granularities = context["granularities"]
        return granularities
    
    def get_granularity_by_code(self, gran_code):
        granularities = self.get_granularities()
        
        for gran in granularities:
            if str(gran["code"]) == str(gran_code):
                return gran
        
        return None
    
    def get_context(self):
        cache_key = f"pulsoweb_context_{self.connection_id}"
        context = cache.get(cache_key)
        
        if context and context.get("stations"):
            return context
        
        path = "get_context"
        context = self.post(path)
        
        # cache for 1 hour
        cache.set(cache_key, context, 3600)
        return context
    
    def get_observation_data(self, station_code, observations, start_date, end_date):
        path = "get_data"
        
        payload = {
            "station": station_code,
            "observations": observations,
            "from": start_date,
            "to": end_date
        }
        
        response = self.post(path, payload)
        records = {}
        
        for obs_code, obs_data in response.items():
            for item in obs_data:
                date = item["date"]
                if date not in records:
                    records[date] = {"observation_time": datetime.datetime.strptime(date, "%Y-%m-%dT%H:%M:%S")}
                records[date][obs_code] = item["value"]
        
        return list(records.values())
    
    def get_logs(self, start_date, end_date):
        path = "get_logs"
        
        payload = {
            "from": start_date,
            "to": end_date
        }
        
        response = self.post(path, payload)
        
        return response
