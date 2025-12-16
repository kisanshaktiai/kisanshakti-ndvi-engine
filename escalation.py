SMALL_LAND_ACRES = 1.0
MIN_VALID_PIXELS = 9

def should_escalate(land, geometry_confidence, ndvi_result):
    """
    Decide whether micro-tile escalation is required.
    """
    if land["area_acres"] < SMALL_LAND_ACRES:
        return True, "small_land"

    if geometry_confidence == "low":
        return True, "low_geometry_confidence"

    if ndvi_result["coverage_percentage"] < 30:
        return True, "low_coverage"

    return False, None
