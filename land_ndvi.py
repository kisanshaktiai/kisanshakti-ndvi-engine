# land_ndvi.py

def histogram_to_stats(hist: dict):
    """
    Convert NDVI histogram to statistical values.
    hist = {
      "bins": [...],
      "counts": [...]
    }
    """
    bins = hist.get("bins")
    counts = hist.get("counts")

    if not bins or not counts or len(bins) != len(counts) + 1:
        return None

    total = sum(counts)
    if total == 0:
        return None

    mids = [(bins[i] + bins[i + 1]) / 2 for i in range(len(counts))]

    mean = sum(m * c for m, c in zip(mids, counts)) / total
    variance = sum(c * (m - mean) ** 2 for m, c in zip(mids, counts)) / total
    std = variance ** 0.5

    return {
        "mean": round(mean, 4),
        "std": round(std, 4),
        "pixels": total,
        "min": bins[0],
        "max": bins[-1],
    }


def aggregate_ndvi_from_grids(grid_cells: list):
    """
    grid_cells = [
      {
        "ndvi_histogram": {...},
        "overlap_ratio": 0.0 - 1.0
      }
    ]
    """

    if not grid_cells:
        raise ValueError("No grid NDVI data available")

    weighted_sum = 0.0
    weighted_var = 0.0
    total_weight = 0.0
    total_pixels = 0

    mins = []
    maxs = []

    for cell in grid_cells:
        overlap = float(cell["overlap_ratio"])
        stats = histogram_to_stats(cell["ndvi_histogram"])

        if not stats or overlap <= 0:
            continue

        weight = overlap * stats["pixels"]

        weighted_sum += stats["mean"] * weight
        weighted_var += (stats["std"] ** 2) * weight
        total_weight += weight
        total_pixels += int(stats["pixels"] * overlap)

        mins.append(stats["min"])
        maxs.append(stats["max"])

    if total_weight == 0:
        raise ValueError("No usable NDVI grid overlap")

    mean_ndvi = weighted_sum / total_weight
    ndvi_std = (weighted_var / total_weight) ** 0.5

    return {
        "mean_ndvi": round(mean_ndvi, 3),
        "ndvi_std": round(ndvi_std, 3),
        "ndvi_min": round(min(mins), 3),
        "ndvi_max": round(max(maxs), 3),
        "pixels_used": total_pixels,
    }


def ndvi_confidence_score(land: dict, ndvi: dict):
    """
    Honest confidence scoring for small Indian farms
    """

    area_acres = float(land.get("area_acres") or 0)
    pixels = ndvi["pixels_used"]
    std = ndvi["ndvi_std"]

    score = 1.0
    flags = []

    # Micro land penalty (<10 guntha)
    if area_acres < 0.25:
        score *= 0.65
        flags.append("micro_land")

    # Low pixel support
    if pixels < 25:
        score *= 0.6
        flags.append("low_pixel_support")

    # High noise
    if std > 0.25:
        score *= 0.7
        flags.append("high_variance")

    if score >= 0.75:
        level = "high"
    elif score >= 0.5:
        level = "medium"
    else:
        level = "low"

    return {
        "confidence_score": round(score, 2),
        "confidence_level": level,
        "confidence_flags": flags,
    }
