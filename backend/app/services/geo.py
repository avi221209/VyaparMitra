"""
Static Indian city geocoding dictionary.
No external network calls, no geocoding API keys required.
"""
from typing import Optional, Tuple

CITY_COORDINATES: dict[str, Tuple[float, float]] = {
    # Core 6 Network Nodes
    "gurgaon": (28.4595, 77.0266),
    "gurugram": (28.4595, 77.0266),
    "bhiwandi": (19.3002, 73.0586),
    "kolkata": (22.5726, 88.3639),
    "calcutta": (22.5726, 88.3639),
    "ahmedabad": (23.0225, 72.5714),
    "bengaluru": (12.9716, 77.5946),
    "bangalore": (12.9716, 77.5946),
    "pune": (18.5204, 73.8567),

    # Major Metros and Regional Commercial Hubs
    "delhi": (28.6139, 77.2090),
    "new delhi": (28.6139, 77.2090),
    "mumbai": (19.0760, 72.8777),
    "chennai": (13.0827, 80.2707),
    "hyderabad": (17.3850, 78.4867),
    "jaipur": (26.9124, 75.7873),
    "lucknow": (26.8467, 80.9462),
    "kanpur": (26.4499, 80.3319),
    "nagpur": (21.1458, 79.0882),
    "indore": (22.7196, 75.8577),
    "bhopal": (23.2599, 77.4126),
    "patna": (25.5941, 85.1376),
    "vadodara": (22.3072, 73.1812),
    "surat": (21.1702, 72.8311),
    "kochi": (9.9312, 76.2673),
    "cochin": (9.9312, 76.2673),
    "chandigarh": (30.7333, 76.7794),
    "guwahati": (26.1445, 91.7362),
    "bhubaneswar": (20.2961, 85.8245),
    "coimbatore": (11.0168, 76.9558),
    "visakhapatnam": (17.6868, 83.2185),
    "vizag": (17.6868, 83.2185),
    "agra": (27.1767, 78.0081),
    "varanasi": (25.3176, 82.9739),
    "ludhiana": (30.9010, 75.8573),
    "amritsar": (31.6340, 74.8723),
    "raipur": (21.2514, 81.6296),
    "ranchi": (23.3441, 85.3096),
    "jodhpur": (26.2389, 73.0243),
    "madurai": (9.9252, 78.1198),
    "mysuru": (12.2958, 76.6394),
    "mysore": (12.2958, 76.6394),
    "thiruvananthapuram": (8.5241, 76.9366),
    "trivandrum": (8.5241, 76.9366),
    "vijayawada": (16.5062, 80.6480),
    "nashik": (19.9975, 73.7898),
}


def get_city_coordinates(city: Optional[str]) -> Optional[Tuple[float, float]]:
    """
    Look up latitude and longitude for an Indian city name.
    Returns (lat, lon) tuple, or None if unknown.
    """
    if not city:
        return None
    normalized = city.strip().lower()
    return CITY_COORDINATES.get(normalized)
