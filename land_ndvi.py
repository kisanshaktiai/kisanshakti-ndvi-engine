def aggregate_ndvi_from_grids(grid_cells: list):
    """
    grid_cells: [
      {
        ndvi_mean,
        overlap_ratio,
        ndvi_min,
        ndvi_max
      }
    ]
    """

    if not grid_cells:
        raise ValueError("No grid NDVI data available")

    weighted_ndvi = 0.0
    weight_sum = 0.0
    mins, maxs = [], []

    for cell in grid_cells:
        w = cell["overlap_ratio"]
        weighted_ndvi += cell["ndvi_mean"] * w
        weight_sum += w
        mins.append(cell["ndvi_min"])
        maxs.append(cell["ndvi_max"])

    if weight_sum == 0:
        raise ValueError("Zero overlap weight")

    return {
        "mean_ndvi": round(weighted_ndvi / weight_sum, 3),
        "ndvi_min": round(min(mins), 3),
        "ndvi_max": round(max(maxs), 3),
        "coverage_percentage": round(weight_sum * 100, 2),
        "confidence_level": "medium",
        "quality_score": min(100, int(weight_sum * 100))
    }
