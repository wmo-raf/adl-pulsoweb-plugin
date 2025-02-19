from datetime import datetime

import zeep


class PulsoWebConnectionError(Exception):
    pass


class PulsoWebClient:
    def __init__(self, wsdl_url, username, password, station_id):
        client = zeep.Client(wsdl=wsdl_url)
        connection = client.service.OpenConnection(username, password, station_id)
        
        if connection.body.OpenConnectionResult:
            self.client = client
        else:
            raise PulsoWebConnectionError("Could not connect to PulsoWeb.")
    
    def close(self):
        if self.client:
            self.client.service.CloseConnection()
    
    def get_parameter_list(self, station_id, param_type, param_name):
        
        param_list = self.client.service.GetParameterList(station_id, param_type, param_name)
        param_list = param_list.body.GetParameterListResult.split("\t")
        
        if param_list[-1] == '':
            param_list.remove(param_list[-1])
        
        param_list = [i.strip() for i in param_list]
        return param_list
    
    def get_last_value(self, station_id, params, param_type, duration):
        value = self.client.service.GetLastValue(station_id, params, param_type, duration)
        result = value.body.GetLastValueResult.split(",")
        return result[1:]
    
    def get_station_latest_data(self, station_id, param_type, duration):
        keys = self.get_parameter_list(station_id, param_type, "LIBEL_CAM")
        params = ",".join(keys)
        values = self.get_last_value(station_id, params, param_type, duration)
        
        # Créer un tableau de correspondance entre keys et values
        data = dict(zip(keys, values))
        date = datetime.now()
        
        for key in data:
            data[key] = data[key].strip()
            
            # convert to float
            if data[key]:
                data[key] = float(data[key])
            else:
                data[key] = None
        
        data['TIMESTAMP'] = date
        
        return data
