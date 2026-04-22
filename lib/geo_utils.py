import numpy as np

def nearest_km(lat, lon, poi_array):
    """
    returns nearest point in poi_array, got big help from CLAUDE!
    :param lat: latitude
    :param lon: longitude
    :param poi_array: array of [lat,lon] and names
    :return: nearest point in poi_array [lat,lon]
    """
    dlat = np.radians(poi_array[:, 0] - lat)
    dlon = np.radians(poi_array[:, 1] - lon)
    a    = (np.sin(dlat/2)**2 +
            np.cos(np.radians(lat)) * np.cos(np.radians(poi_array[:, 0])) *
            np.sin(dlon/2)**2)
    return float(6371 * 2 * np.arcsin(np.sqrt(a.clip(0, 1))).min())