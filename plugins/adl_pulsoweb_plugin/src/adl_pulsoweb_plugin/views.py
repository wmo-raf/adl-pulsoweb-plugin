from django.shortcuts import render
from rest_framework.generics import get_object_or_404

from .client import PulsoWebClient
from .models import PulsoWebConnection


def get_pulsoweb_granularities(request, connection_id):
    conn = get_object_or_404(PulsoWebConnection, pk=connection_id)
    
    client = PulsoWebClient(conn.api_base_url, conn.api_token, conn.id)
    
    data = client.get_granularities()
    
    context = {
        "connection_id": connection_id,
        "data": data
    }
    
    return render(request, template_name="adl_pulsoweb_plugin/granularities_list.html", context=context)


def get_pulsoweb_granularity_observations(request, connection_id, gran_code):
    conn = get_object_or_404(PulsoWebConnection, pk=connection_id)
    
    client = PulsoWebClient(conn.api_base_url, conn.api_token, conn.id)
    
    gran = client.get_granularity_by_code(gran_code)
    
    data = client.get_observations_for_granular(gran_code)
    
    context = {
        "gran": gran,
        "connection_id": connection_id,
        "data": data
    }
    
    return render(request, template_name="adl_pulsoweb_plugin/granularity_detail.html", context=context)


def get_pulsoweb_stations_for_observation(request, connection_id, obs_code):
    conn = get_object_or_404(PulsoWebConnection, pk=connection_id)
    
    client = PulsoWebClient(conn.api_base_url, conn.api_token, conn.id)
    
    observation = client.get_observation_by_code(obs_code)
    
    stations = client.get_stations_with_obs(obs_code)
    
    context = {
        "connection_id": connection_id,
        "obs": observation,
        "stations": stations
    }
    
    return render(request, template_name="adl_pulsoweb_plugin/stations_list.html", context=context)
