"""Indian States & Union Territories catalogue for spatial mapping (36 States/UTs).

Names correspond 1:1 with properties.ST_NM in public/geo/india-states.geojson.
"""
from __future__ import annotations

from typing import Dict, List, TypedDict


class StateEntry(TypedDict):
    code: str
    name: str
    capital: str
    latitude: float
    longitude: float


INDIAN_STATES: List[StateEntry] = [
    {"code": "AN", "name": "Andaman & Nicobar", "capital": "Port Blair", "latitude": 11.7401, "longitude": 92.6586},
    {"code": "AP", "name": "Andhra Pradesh", "capital": "Amaravati", "latitude": 16.5062, "longitude": 80.6480},
    {"code": "AR", "name": "Arunachal Pradesh", "capital": "Itanagar", "latitude": 27.0844, "longitude": 93.6053},
    {"code": "AS", "name": "Assam", "capital": "Guwahati", "latitude": 26.1445, "longitude": 91.7362},
    {"code": "BR", "name": "Bihar", "capital": "Patna", "latitude": 25.5941, "longitude": 85.1376},
    {"code": "CH", "name": "Chandigarh", "capital": "Chandigarh", "latitude": 30.7333, "longitude": 76.7794},
    {"code": "CT", "name": "Chhattisgarh", "capital": "Raipur", "latitude": 21.2514, "longitude": 81.6296},
    {"code": "DNHDD", "name": "Dadra and Nagar Haveli and Daman and Diu", "capital": "Daman", "latitude": 20.4283, "longitude": 72.8397},
    {"code": "DL", "name": "Delhi", "capital": "New Delhi", "latitude": 28.6139, "longitude": 77.2090},
    {"code": "GA", "name": "Goa", "capital": "Panaji", "latitude": 15.4909, "longitude": 73.8278},
    {"code": "GJ", "name": "Gujarat", "capital": "Gandhinagar", "latitude": 23.2156, "longitude": 72.6369},
    {"code": "HR", "name": "Haryana", "capital": "Chandigarh", "latitude": 29.0588, "longitude": 76.0856},
    {"code": "HP", "name": "Himachal Pradesh", "capital": "Shimla", "latitude": 31.1048, "longitude": 77.1734},
    {"code": "JK", "name": "Jammu & Kashmir", "capital": "Srinagar", "latitude": 34.0837, "longitude": 74.7973},
    {"code": "JH", "name": "Jharkhand", "capital": "Ranchi", "latitude": 23.3441, "longitude": 85.3096},
    {"code": "KA", "name": "Karnataka", "capital": "Bengaluru", "latitude": 12.9716, "longitude": 77.5946},
    {"code": "KL", "name": "Kerala", "capital": "Thiruvananthapuram", "latitude": 8.5241, "longitude": 76.9366},
    {"code": "LA", "name": "Ladakh", "capital": "Leh", "latitude": 34.1526, "longitude": 77.5771},
    {"code": "LD", "name": "Lakshadweep", "capital": "Kavaratti", "latitude": 10.5667, "longitude": 72.6417},
    {"code": "MP", "name": "Madhya Pradesh", "capital": "Bhopal", "latitude": 23.2599, "longitude": 77.4126},
    {"code": "MH", "name": "Maharashtra", "capital": "Mumbai", "latitude": 19.0760, "longitude": 72.8777},
    {"code": "MN", "name": "Manipur", "capital": "Imphal", "latitude": 24.8170, "longitude": 93.9368},
    {"code": "ML", "name": "Meghalaya", "capital": "Shillong", "latitude": 25.5788, "longitude": 91.8933},
    {"code": "MZ", "name": "Mizoram", "capital": "Aizawl", "latitude": 23.7271, "longitude": 92.7176},
    {"code": "NL", "name": "Nagaland", "capital": "Kohima", "latitude": 25.6751, "longitude": 94.1086},
    {"code": "OR", "name": "Odisha", "capital": "Bhubaneswar", "latitude": 20.2961, "longitude": 85.8245},
    {"code": "PY", "name": "Puducherry", "capital": "Puducherry", "latitude": 11.9416, "longitude": 79.8083},
    {"code": "PB", "name": "Punjab", "capital": "Chandigarh", "latitude": 30.9010, "longitude": 75.8573},
    {"code": "RJ", "name": "Rajasthan", "capital": "Jaipur", "latitude": 26.9124, "longitude": 75.7873},
    {"code": "SK", "name": "Sikkim", "capital": "Gangtok", "latitude": 27.3389, "longitude": 88.6065},
    {"code": "TN", "name": "Tamil Nadu", "capital": "Chennai", "latitude": 13.0827, "longitude": 80.2707},
    {"code": "TG", "name": "Telangana", "capital": "Hyderabad", "latitude": 17.3850, "longitude": 78.4867},
    {"code": "TR", "name": "Tripura", "capital": "Agartala", "latitude": 23.8315, "longitude": 91.2868},
    {"code": "UP", "name": "Uttar Pradesh", "capital": "Lucknow", "latitude": 26.8467, "longitude": 80.9462},
    {"code": "UT", "name": "Uttarakhand", "capital": "Dehradun", "latitude": 30.3165, "longitude": 78.0322},
    {"code": "WB", "name": "West Bengal", "capital": "Kolkata", "latitude": 22.5726, "longitude": 88.3639},
]

STATES_BY_NAME: Dict[str, StateEntry] = {s["name"]: s for s in INDIAN_STATES}
STATES_BY_CODE: Dict[str, StateEntry] = {s["code"]: s for s in INDIAN_STATES}
