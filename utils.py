import datetime
from astral.sun import sun
from astral import Observer

def compute_sun_vector(latitude, longitude, elevation, timestamp=None):
    """
    Computes the sun's azimuth and zenith angle for a given location and time.

    :param latitude: Observer's latitude (degrees).
    :param longitude: Observer's longitude (degrees).
    :param elevation: Observer's elevation (meters).
    :param timestamp: The datetime object for the calculation. If None, uses current time.
    :return: A dictionary with 'azimuth' and 'zenith' in degrees.
    """
    if timestamp is None:
        timestamp = datetime.datetime.now(datetime.timezone.utc)

    obs = Observer(latitude=latitude, longitude=longitude, elevation=elevation)
    s = sun(obs, date=timestamp.date(), tzinfo=timestamp.tzinfo)
    
    azimuth = s['azimuth']
    altitude = s['altitude'] # Elevation angle
    zenith = 90.0 - altitude

    return {
        'azimuth': azimuth,
        'zenith': zenith,
        'altitude': altitude
    }

if __name__ == '__main__':
    # Example usage
    # Coordinates for NASA Goddard Space Flight Center (approx)
    lat = 38.99
    lon = -76.85
    elev = 50
    
    sun_pos = compute_sun_vector(lat, lon, elev)
    print(f"Current Sun Position:")
    print(f"  Azimuth: {sun_pos['azimuth']:.2f}°")
    print(f"  Zenith: {sun_pos['zenith']:.2f}°")
    print(f"  Altitude: {sun_pos['altitude']:.2f}°")
