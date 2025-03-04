from django.urls import path
from wagtail import hooks

from .views import (
    get_pulsoweb_granularities,
    get_pulsoweb_granularity_observations,
    get_pulsoweb_stations_for_observation
)


@hooks.register('register_admin_urls')
def urlconf_adl_pulsoweb_plugin():
    return [
        path('adl-pulsoweb-plugin/granularity/<int:connection_id>/', get_pulsoweb_granularities,
             name='adl_pulsoweb_plugin_granularity'),
        path('adl-pulsoweb-plugin/granularity/<int:connection_id>/<str:gran_code>/',
             get_pulsoweb_granularity_observations, name='adl_pulsoweb_plugin_granularity_observations'),
        path('adl-pulsoweb-plugin/stations/<int:connection_id>/<str:obs_code>/',
             get_pulsoweb_stations_for_observation, name='adl_pulsoweb_plugin_stations_by_obs'),
    
    ]
