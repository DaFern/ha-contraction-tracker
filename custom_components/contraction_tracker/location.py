"""Conservative, local-only zone resolution. No coordinate history is stored."""

from math import asin, cos, isfinite, radians, sin, sqrt
import re


def entity_id(value, domain):
    return isinstance(value, str) and re.fullmatch(domain + r"\.[a-z0-9_]+", value) is not None


def finite(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and isfinite(value)


def uncertain():
    return {"location": "uncertain", "source": "automatic", "label": "Location uncertain · automatic"}


def manual(settings):
    names = {"unspecified": "Not specified", "home": "At home", "hospital": "In hospital / birth centre"}
    return {"location": settings["location"], "source": "manual",
            "label": names[settings["location"]] + " · manual"}


def classify(accuracy, age, zones):
    """zones is [(kind, centre_distance_metres, radius_metres)].

    Require the complete GPS accuracy circle inside exactly one selected zone,
    with no boundary/overlap ambiguity. Elsewhere is not home or hospital.
    """
    if (not finite(accuracy) or not 0 <= accuracy <= 100
            or not finite(age) or not -30 <= age <= 900 or not zones):
        return uncertain()
    inside, boundary = [], False
    for kind, distance, radius in zones:
        if kind not in ("home", "hospital") or not finite(distance) or distance < 0 or not finite(radius) or radius <= 0:
            return uncertain()
        if distance + accuracy < radius:
            inside.append(kind)
        elif distance - accuracy <= radius:
            boundary = True
    if boundary or len(inside) > 1:
        return uncertain()
    kind = inside[0] if inside else "elsewhere"
    label = {"home": "Home zone", "hospital": "Hospital zone", "elsewhere": "Elsewhere"}[kind]
    return {"location": kind, "source": "automatic", "label": label + " · automatic"}


def resolve(settings, states, now):
    """Read selected person's current GPS source only; never guess another phone."""
    if settings["mode"] == "manual":
        return manual(settings)
    person = states.get(settings["person"])
    if not person or person["state"] in ("unknown", "unavailable"):
        return uncertain()
    source_id = person["attributes"].get("source", "")
    if not entity_id(source_id, "device_tracker"):
        return uncertain()
    source = states.get(source_id)
    if not source or source["state"] in ("unknown", "unavailable"):
        return uncertain()
    attrs = source["attributes"]
    lat, lon = attrs.get("latitude"), attrs.get("longitude")
    stamp = source.get("reported")
    if (attrs.get("source_type") != "gps" or attrs.get("restored")
            or not finite(lat) or not -90 <= lat <= 90 or not finite(lon) or not -180 <= lon <= 180
            or not finite(stamp)):
        return uncertain()
    zones = []
    for zone_id in [settings["home"], *settings["hospitals"]]:
        zone = states.get(zone_id)
        if not zone or zone["state"] in ("unknown", "unavailable"):
            return uncertain()
        za = zone["attributes"]
        zlat, zlon = za.get("latitude"), za.get("longitude")
        if not finite(zlat) or not -90 <= zlat <= 90 or not finite(zlon) or not -180 <= zlon <= 180:
            return uncertain()
        arc = sin(radians(zlat - lat) / 2) ** 2 + cos(radians(lat)) * cos(radians(zlat)) * sin(radians(zlon - lon) / 2) ** 2
        distance = 6371000 * 2 * asin(sqrt(min(1, max(0, arc))))
        zones.append(("home" if zone_id == settings["home"] else "hospital", distance, za.get("radius")))
    return classify(attrs.get("gps_accuracy"), now - stamp, zones)
