"""Prototype region catalogue — 36 Indian cities (UIUX §8.1: "36 regions").

Point locations chosen to spread across states/orography (coast, plains,
hills, arid zones) so the reliability map has realistic spatial structure.
"""
from __future__ import annotations

from typing import Dict, List, TypedDict


class RegionRow(TypedDict):
    region_id: str
    region_name: str
    state: str
    latitude: float
    longitude: float
    elevation: float
    coastal: bool


REGIONS: List[RegionRow] = [
    {"region_id": "MH_MUM", "region_name": "Mumbai", "state": "Maharashtra", "latitude": 19.076, "longitude": 72.877, "elevation": 14.0, "coastal": True},
    {"region_id": "MH_PUN", "region_name": "Pune", "state": "Maharashtra", "latitude": 18.520, "longitude": 73.857, "elevation": 560.0, "coastal": False},
    {"region_id": "MH_NAG", "region_name": "Nagpur", "state": "Maharashtra", "latitude": 21.146, "longitude": 79.088, "elevation": 310.0, "coastal": False},
    {"region_id": "DL_DEL", "region_name": "Delhi", "state": "Delhi", "latitude": 28.614, "longitude": 77.209, "elevation": 216.0, "coastal": False},
    {"region_id": "UP_LKO", "region_name": "Lucknow", "state": "Uttar Pradesh", "latitude": 26.847, "longitude": 80.947, "elevation": 123.0, "coastal": False},
    {"region_id": "UP_VNS", "region_name": "Varanasi", "state": "Uttar Pradesh", "latitude": 25.318, "longitude": 82.974, "elevation": 81.0, "coastal": False},
    {"region_id": "BR_PAT", "region_name": "Patna", "state": "Bihar", "latitude": 25.594, "longitude": 85.138, "elevation": 53.0, "coastal": False},
    {"region_id": "JH_RNC", "region_name": "Ranchi", "state": "Jharkhand", "latitude": 23.344, "longitude": 85.309, "elevation": 651.0, "coastal": False},
    {"region_id": "WB_KOL", "region_name": "Kolkata", "state": "West Bengal", "latitude": 22.573, "longitude": 88.364, "elevation": 9.0, "coastal": True},
    {"region_id": "WB_SIL", "region_name": "Siliguri", "state": "West Bengal", "latitude": 26.727, "longitude": 88.395, "elevation": 122.0, "coastal": False},
    {"region_id": "OD_BBI", "region_name": "Bhubaneswar", "state": "Odisha", "latitude": 20.296, "longitude": 85.825, "elevation": 45.0, "coastal": True},
    {"region_id": "AP_VJA", "region_name": "Vijayawada", "state": "Andhra Pradesh", "latitude": 16.506, "longitude": 80.648, "elevation": 23.0, "coastal": False},
    {"region_id": "AP_TIR", "region_name": "Tirupati", "state": "Andhra Pradesh", "latitude": 13.629, "longitude": 79.419, "elevation": 153.0, "coastal": False},
    {"region_id": "TS_HYD", "region_name": "Hyderabad", "state": "Telangana", "latitude": 17.385, "longitude": 78.487, "elevation": 542.0, "coastal": False},
    {"region_id": "KA_BLR", "region_name": "Bengaluru", "state": "Karnataka", "latitude": 12.972, "longitude": 77.594, "elevation": 920.0, "coastal": False},
    {"region_id": "KA_MNG", "region_name": "Mangaluru", "state": "Karnataka", "latitude": 12.914, "longitude": 74.856, "elevation": 22.0, "coastal": True},
    {"region_id": "TN_MAA", "region_name": "Chennai", "state": "Tamil Nadu", "latitude": 13.083, "longitude": 80.271, "elevation": 6.7, "coastal": True},
    {"region_id": "TN_CBE", "region_name": "Coimbatore", "state": "Tamil Nadu", "latitude": 11.017, "longitude": 76.956, "elevation": 411.0, "coastal": False},
    {"region_id": "KL_TRV", "region_name": "Thiruvananthapuram", "state": "Kerala", "latitude": 8.524, "longitude": 76.937, "elevation": 4.0, "coastal": True},
    {"region_id": "KL_KOC", "region_name": "Kochi", "state": "Kerala", "latitude": 9.932, "longitude": 76.267, "elevation": 0.0, "coastal": True},
    {"region_id": "GJ_AHM", "region_name": "Ahmedabad", "state": "Gujarat", "latitude": 23.023, "longitude": 72.571, "elevation": 53.0, "coastal": False},
    {"region_id": "GJ_SRT", "region_name": "Surat", "state": "Gujarat", "latitude": 21.170, "longitude": 72.831, "elevation": 13.0, "coastal": True},
    {"region_id": "RJ_JAI", "region_name": "Jaipur", "state": "Rajasthan", "latitude": 26.912, "longitude": 75.787, "elevation": 431.0, "coastal": False},
    {"region_id": "RJ_JDR", "region_name": "Jodhpur", "state": "Rajasthan", "latitude": 26.239, "longitude": 73.024, "elevation": 231.0, "coastal": False},
    {"region_id": "MP_BHO", "region_name": "Bhopal", "state": "Madhya Pradesh", "latitude": 23.260, "longitude": 77.413, "elevation": 527.0, "coastal": False},
    {"region_id": "MP_JBP", "region_name": "Jabalpur", "state": "Madhya Pradesh", "latitude": 23.181, "longitude": 79.986, "elevation": 411.0, "coastal": False},
    {"region_id": "CHD_CHD", "region_name": "Chandigarh", "state": "Chandigarh", "latitude": 30.733, "longitude": 76.779, "elevation": 321.0, "coastal": False},
    {"region_id": "PB_AMD", "region_name": "Amritsar", "state": "Punjab", "latitude": 31.634, "longitude": 74.872, "elevation": 234.0, "coastal": False},
    {"region_id": "HR_HIS", "region_name": "Hisar", "state": "Haryana", "latitude": 29.149, "longitude": 75.722, "elevation": 215.0, "coastal": False},
    {"region_id": "UK_DDH", "region_name": "Dehradun", "state": "Uttarakhand", "latitude": 30.317, "longitude": 78.032, "elevation": 640.0, "coastal": False},
    {"region_id": "HP_SHM", "region_name": "Shimla", "state": "Himachal Pradesh", "latitude": 31.105, "longitude": 77.171, "elevation": 2276.0, "coastal": False},
    {"region_id": "JK_SRN", "region_name": "Srinagar", "state": "Jammu & Kashmir", "latitude": 34.084, "longitude": 74.798, "elevation": 1585.0, "coastal": False},
    {"region_id": "AS_GHY", "region_name": "Guwahati", "state": "Assam", "latitude": 26.145, "longitude": 91.736, "elevation": 55.0, "coastal": False},
    {"region_id": "TR_AGR", "region_name": "Agartala", "state": "Tripura", "latitude": 23.832, "longitude": 91.281, "elevation": 12.8, "coastal": False},
    {"region_id": "GA_ITN", "region_name": "Itanagar", "state": "Arunachal Pradesh", "latitude": 27.084, "longitude": 93.605, "elevation": 435.0, "coastal": False},
    {"region_id": "GO_PAN", "region_name": "Panaji", "state": "Goa", "latitude": 15.490, "longitude": 73.828, "elevation": 7.0, "coastal": True},
]

REGION_INDEX: Dict[str, RegionRow] = {r["region_id"]: r for r in REGIONS}
