"""Extract per-pixel Sentinel-2 features from locally downloaded JP2 bands."""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
import re
import tempfile
from collections import Counter
from pathlib import Path
from typing import Any, TextIO

import geopandas as gpd
import numpy as np
import rasterio
from rasterio.enums import Resampling
from rasterio.errors import WindowError
from rasterio.features import geometry_mask, geometry_window
from rasterio.vrt import WarpedVRT
from rasterio.windows import Window
from shapely.geometry import GeometryCollection, MultiPolygon, mapping, shape
from shapely.ops import unary_union
from shapely.validation import make_valid


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_GEOJSON = REPOSITORY_ROOT / "data" / "jawatimur.geojson"
DEFAULT_BAND_DIR = REPOSITORY_ROOT / "data" / "sentinel2"
DEFAULT_OUTPUT_DIR = REPOSITORY_ROOT / "data" / "csv" / "split_dataset"

CLASSES = ("Built-up", "Farm land", "Water body", "Forest", "Mangrove")
CLASS_ID_NAMES = {
    1: "Built-up",
    2: "Farm land",
    3: "Water body",
    4: "Forest",
    5: "Mangrove",
}
CLASS_ALIASES = {
    "built up": "Built-up",
    "builtup": "Built-up",
    "bangunan": "Built-up",
    "bangunan permukiman": "Built-up",
    "farm land": "Farm land",
    "farmland": "Farm land",
    "lahan pertanian": "Farm land",
    "sawah": "Farm land",
    "water body": "Water body",
    "waterbody": "Water body",
    "perairan": "Water body",
    "lautan": "Water body",
    "danau": "Water body",
    "forest": "Forest",
    "hutan": "Forest",
    "mangrove": "Mangrove",
    "hutan mangrove": "Mangrove",
}
ONE_HOT_CLASSES = {
    "built up": "Built-up",
    "farm land": "Farm land",
    "water body": "Water body",
    "forest": "Forest",
    "mangrove": "Mangrove",
}
BANDS = ("B02", "B03", "B04", "B08", "B11")
INDEX_NAMES = ("NDVI", "NDWI", "NDBI")
CSV_FIELDS = ("ID_Poligon", "kelas", "status_split", *BANDS, *INDEX_NAMES)
BAND_PATTERN = re.compile(
    r"_(B02|B03|B04|B08|B11)_(10|20)m$", re.IGNORECASE
)
RESOLUTION_DIR = re.compile(r"^R(?:10|20|60)m$", re.IGNORECASE)


def _normalise_class(value: Any) -> str | None:
    if value is None:
        return None
    text = " ".join(
        str(value).strip().casefold().replace("_", " ").replace("-", " ").split()
    )
    if text.isdigit():
        return CLASS_ID_NAMES.get(int(text))
    if text in CLASS_ALIASES:
        return CLASS_ALIASES[text]
    return next(
        (
            class_name
            for class_name in CLASSES
            if text
            == " ".join(
                class_name.casefold().replace("_", " ").replace("-", " ").split()
            )
        ),
        None,
    )


def _feature_label(properties: dict[str, Any]) -> str:
    for key in ("class", "kelas", "class_name", "label", "kelas_en", "kelas_id"):
        value = properties.get(key)
        if value is not None:
            label = _normalise_class(value)
            if label is not None:
                return label
    if properties.get("class_id") is not None:
        label = _normalise_class(properties["class_id"])
        if label is not None:
            return label

    active: list[str] = []
    for raw_key, raw_value in properties.items():
        key = " ".join(
            str(raw_key).strip().casefold().replace("_", " ").replace("-", " ").split()
        )
        label = ONE_HOT_CLASSES.get(key)
        if label is None:
            continue
        value = str(raw_value).strip().casefold()
        if raw_value is not None and value not in {"", "0", "false", "none", "null"}:
            active.append(label)
    active = list(dict.fromkeys(active))
    if len(active) == 1:
        return active[0]
    if len(active) > 1:
        raise ValueError(f"Feature memiliki beberapa kelas aktif: {active}.")
    raise ValueError(
        "Label tidak dikenali. Gunakan class/class_name/kelas, class_id 1-5, "
        "atau kolom one-hot Built-up, Farm land, Water body, Forest, Mangrove."
    )


def read_label_polygons(geojson_path: Path, geojson_crs: str) -> gpd.GeoDataFrame:
    """Read GeoJSON with Python's JSON parser, avoiding optional GDAL file drivers."""
    with geojson_path.open(encoding="utf-8") as source:
        document = json.load(source)
    if document.get("type") == "Feature":
        features = [document]
    elif document.get("type") == "FeatureCollection":
        features = document.get("features", [])
    else:
        raise ValueError("GeoJSON harus bertipe Feature atau FeatureCollection.")
    if not features:
        raise ValueError(f"GeoJSON tidak memiliki feature: {geojson_path}")
    rows: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    repaired_geometries: list[int] = []
    for index, feature in enumerate(features, start=1):
        geometry_json = feature.get("geometry")
        if geometry_json is None:
            raise ValueError(f"Feature ke-{index} tidak memiliki geometri.")
        geometry = shape(geometry_json)
        if geometry is None or geometry.is_empty or geometry.geom_type not in {
            "Polygon",
            "MultiPolygon",
        }:
            raise ValueError(
                f"Feature ke-{index}: geometri harus Polygon/MultiPolygon yang tidak kosong."
            )
        properties = feature.get("properties") or {}
        if not isinstance(properties, dict):
            raise ValueError(f"Feature ke-{index}: properties harus berupa object JSON.")
        if not geometry.is_valid:
            repaired = make_valid(geometry)
            if isinstance(repaired, GeometryCollection):
                polygon_parts = [
                    part
                    for part in repaired.geoms
                    if part.geom_type in {"Polygon", "MultiPolygon"}
                ]
                repaired = unary_union(polygon_parts) if polygon_parts else repaired
            if repaired.is_empty or repaired.geom_type not in {"Polygon", "MultiPolygon"}:
                raise ValueError(
                    f"Feature ke-{index}: geometri tidak valid dan tidak dapat "
                    "diperbaiki menjadi Polygon/MultiPolygon."
                )
            geometry = repaired
            repaired_geometries.append(index)
        class_name = _feature_label(properties)
        supplied_id = feature.get("id") or properties.get("id") or properties.get("ID_Poligon")
        polygon_id = (
            str(supplied_id).strip()
            if supplied_id is not None and str(supplied_id).strip()
            else f"polygon-{index - 1}"
        )
        if polygon_id in seen_ids:
            raise ValueError(f"ID poligon duplikat: {polygon_id}")
        seen_ids.add(polygon_id)
        rows.append(
            {
                **properties,
                "geometry": geometry,
                "ID_Poligon": polygon_id,
                "kelas": class_name,
            }
        )

    frame = gpd.GeoDataFrame(rows, geometry="geometry", crs=geojson_crs)
    frame = frame.to_crs("EPSG:4326")
    if repaired_geometries:
        print(
            f"Memperbaiki geometri self-intersection pada {len(repaired_geometries)} "
            f"feature: {repaired_geometries}"
        )
    counts = frame["kelas"].value_counts().to_dict()
    missing = sorted(set(CLASSES) - set(counts))
    if missing:
        raise ValueError(f"GeoJSON tidak memuat label untuk: {', '.join(missing)}")
    too_small = {name: count for name, count in counts.items() if count < 2}
    if too_small:
        raise ValueError(
            "Untuk split train/test setiap kelas perlu minimal dua poligon. "
            f"Jumlah: {too_small}"
        )
    return frame


def _scene_key(path: Path, root: Path) -> tuple[str, str]:
    relative = path.relative_to(root)
    parts = [part for part in relative.parts[:-1] if not RESOLUTION_DIR.fullmatch(part)]
    stem = path.stem
    match = BAND_PATTERN.search(stem)
    if match is None:
        raise ValueError(f"Nama file tidak menunjukkan band Sentinel-2: {path.name}")
    band, resolution = match.group(1).upper(), match.group(2)
    expected_resolution = "20" if band == "B11" else "10"
    if resolution != expected_resolution:
        raise ValueError(
            f"{path.name}: {band} harus berasal dari resolusi {expected_resolution} m."
        )
    normalised_stem = BAND_PATTERN.sub("_BAND", stem)
    return str(Path(*parts) / normalised_stem), band


def discover_band_sets(band_dir: Path) -> list[dict[str, Path]]:
    """Group extracted SAFE JP2 files by matching product/granule/acquisition names."""
    if not band_dir.is_dir():
        raise FileNotFoundError(
            f"Folder JP2 tidak ditemukan: {band_dir}\n"
            "Ekstrak ZIP produk Sentinel-2 terlebih dahulu. Letakkan folder SAFE "
            f"hasil ekstrak di {DEFAULT_BAND_DIR}, atau jalankan ulang dengan "
            "--band-dir \"PATH_KE_FOLDER_SAFE\". Folder tersebut harus memuat "
            "*_B02_10m.jp2, *_B03_10m.jp2, *_B04_10m.jp2, *_B08_10m.jp2, "
            "dan *_B11_20m.jp2 dari granula yang sama."
        )
    groups: dict[str, dict[str, Path]] = {}
    for path in band_dir.rglob("*.jp2"):
        match = BAND_PATTERN.search(path.stem)
        if match is None:
            continue
        key, band = _scene_key(path, band_dir)
        if band in groups.setdefault(key, {}):
            raise ValueError(
                f"Band {band} duplikat pada grup {key}; pisahkan produk Sentinel-2 "
                "ke folder berbeda atau masukkan hanya satu akuisisi."
            )
        groups[key][band] = path

    complete = []
    incomplete = []
    for key, paths in groups.items():
        missing = sorted(set(BANDS) - paths.keys())
        if missing:
            incomplete.append((key, missing))
        else:
            complete.append({"scene_id": key, **paths})
    if not complete:
        details = "; ".join(f"{key}: hilang {','.join(missing)}" for key, missing in incomplete[:5])
        raise FileNotFoundError(
            f"Tidak ditemukan set JP2 lengkap B02/B03/B04/B08/B11 di {band_dir}. "
            "Periksa folder SAFE IMG_DATA/R10m dan R20m. "
            + details
        )
    if incomplete:
        print(
            f"Melewati {len(incomplete)} grup JP2 yang tidak lengkap; "
            f"{len(complete)} grup lengkap akan diproses."
        )
    return complete


def assign_polygon_splits(
    frame: gpd.GeoDataFrame,
    test_size: float,
    random_state: int,
) -> dict[str, str]:
    """Stratify whole polygons so samples from the same polygon never leak across splits."""
    if not 0 < test_size < 1:
        raise ValueError("test_size harus di antara 0 dan 1.")
    labels = frame["kelas"].to_numpy()
    ids = frame["ID_Poligon"].astype(str).to_numpy()
    counts = Counter(labels)
    test_count = math.ceil(len(frame) * test_size)
    if test_count < len(CLASSES) or len(frame) - test_count < len(CLASSES):
        raise ValueError(
            "Jumlah poligon terlalu sedikit untuk split train/test terstratifikasi."
        )
    for class_name in CLASSES:
        if counts[class_name] < 2:
            raise ValueError(
                f"Kelas {class_name} perlu minimal dua poligon untuk train/test."
            )
    rng = np.random.default_rng(random_state)
    test_indices: list[int] = []
    for class_name in CLASSES:
        class_indices = np.flatnonzero(labels == class_name)
        rng.shuffle(class_indices)
        class_test_count = max(1, math.ceil(class_indices.size * test_size))
        class_test_count = min(class_test_count, class_indices.size - 1)
        test_indices.extend(class_indices[:class_test_count].tolist())
    test_index_set = set(test_indices)
    train_ids = [polygon_id for index, polygon_id in enumerate(ids) if index not in test_index_set]
    test_ids = [polygon_id for index, polygon_id in enumerate(ids) if index in test_index_set]
    return {
        **{str(polygon_id): "train" for polygon_id in train_ids},
        **{str(polygon_id): "test" for polygon_id in test_ids},
    }


def _open_aligned_bands(
    band_set: dict[str, Path],
) -> tuple[dict[str, Any], list[Any]]:
    """Align every band to B02's 10 m grid; bilinearly upsample B11."""
    reference = rasterio.open(band_set["B02"])
    datasets: list[Any] = [reference]
    aligned: dict[str, Any] = {"B02": reference}
    try:
        for band in BANDS[1:]:
            source = rasterio.open(band_set[band])
            datasets.append(source)
            if (
                source.crs == reference.crs
                and source.transform == reference.transform
                and source.width == reference.width
                and source.height == reference.height
            ):
                aligned[band] = source
            else:
                vrt = WarpedVRT(
                    source,
                    crs=reference.crs,
                    transform=reference.transform,
                    width=reference.width,
                    height=reference.height,
                    resampling=Resampling.bilinear,
                    dtype="float32",
                )
                datasets.append(vrt)
                aligned[band] = vrt
        return aligned, datasets
    except Exception:
        for dataset in reversed(datasets):
            dataset.close()
        raise


def _write_pixel_features(
    geometry: Any,
    polygon_id: str,
    class_name: str,
    split_name: str,
    bands: dict[str, Any],
    writer: csv.DictWriter,
) -> int:
    reference = bands["B02"]
    projected = gpd.GeoSeries([geometry], crs="EPSG:4326").to_crs(
        reference.crs
    ).iloc[0]
    try:
        window = geometry_window(reference, [mapping(projected)])
        window = window.intersection(Window(0, 0, reference.width, reference.height))
    except WindowError:
        return 0
    if window.width <= 0 or window.height <= 0:
        return 0

    transform = reference.window_transform(window)
    polygon_mask = geometry_mask(
        [mapping(projected)],
        out_shape=(int(window.height), int(window.width)),
        transform=transform,
        invert=True,
        all_touched=False,
    )
    if not polygon_mask.any():
        return 0

    arrays: dict[str, np.ma.MaskedArray] = {}
    valid = polygon_mask.copy()
    for band_name in BANDS:
        array = bands[band_name].read(1, window=window, masked=True).astype(np.float32)
        arrays[band_name] = array
        valid &= ~np.ma.getmaskarray(array)
        valid &= np.isfinite(array.filled(np.nan))
    rows, columns = np.nonzero(valid)
    if not len(rows):
        return 0

    values = {
        name: np.asarray(array.data[rows, columns], dtype=np.float32)
        for name, array in arrays.items()
    }
    green = values["B03"]
    red = values["B04"]
    nir = values["B08"]
    swir = values["B11"]
    ndvi_denominator = nir + red
    ndwi_denominator = green + nir
    ndbi_denominator = swir + nir
    indices = {
        "NDVI": np.divide(
            nir - red,
            ndvi_denominator,
            out=np.full_like(nir, np.nan),
            where=np.abs(ndvi_denominator) > 1e-8,
        ),
        "NDWI": np.divide(
            green - nir,
            ndwi_denominator,
            out=np.full_like(nir, np.nan),
            where=np.abs(ndwi_denominator) > 1e-8,
        ),
        "NDBI": np.divide(
            swir - nir,
            ndbi_denominator,
            out=np.full_like(nir, np.nan),
            where=np.abs(ndbi_denominator) > 1e-8,
        ),
    }
    valid_indices = np.logical_and.reduce(
        [np.isfinite(values_array) for values_array in indices.values()]
    )
    rows, columns = rows[valid_indices], columns[valid_indices]
    if not len(rows):
        return 0

    values = {name: band_values[valid_indices] for name, band_values in values.items()}
    indices = {name: index_values[valid_indices] for name, index_values in indices.items()}
    for pixel in range(len(rows)):
        writer.writerow(
            {
                "ID_Poligon": polygon_id,
                "kelas": class_name,
                "status_split": split_name,
                **{name: f"{values[name][pixel]:.8g}" for name in BANDS},
                **{name: f"{indices[name][pixel]:.8g}" for name in INDEX_NAMES},
            }
        )
    return len(rows)


def extract_to_csv(
    geojson_path: Path,
    band_dir: Path,
    output_dir: Path,
    geojson_crs: str = "EPSG:4326",
    test_size: float = 0.2,
    random_state: int = 42,
) -> tuple[Path, Path]:
    """Extract all valid polygon pixels locally and atomically write train/test CSVs."""
    frame = read_label_polygons(geojson_path, geojson_crs)
    band_sets = discover_band_sets(band_dir)
    split_by_id = assign_polygon_splits(frame, test_size, random_state)
    print(f"Label polygon: {len(frame)}; kelas: {frame['kelas'].value_counts().to_dict()}")
    print(f"Set citra JP2 lengkap: {len(band_sets)}")
    print(f"Split polygon: {Counter(split_by_id.values())}")

    output_dir.mkdir(parents=True, exist_ok=True)
    train_path = output_dir / "train_dataset.csv"
    test_path = output_dir / "test_dataset.csv"
    temp_paths: list[Path] = []
    file_handles: list[TextIO] = []
    try:
        train_file = tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8-sig", newline="", dir=output_dir,
            suffix=".train.tmp", delete=False
        )
        test_file = tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8-sig", newline="", dir=output_dir,
            suffix=".test.tmp", delete=False
        )
        temp_paths.extend((Path(train_file.name), Path(test_file.name)))
        file_handles.extend((train_file, test_file))
        train_writer = csv.DictWriter(train_file, fieldnames=CSV_FIELDS)
        test_writer = csv.DictWriter(test_file, fieldnames=CSV_FIELDS)
        train_writer.writeheader()
        test_writer.writeheader()

        pixels_by_split: Counter[str] = Counter()
        pixels_by_class: Counter[tuple[str, str]] = Counter()
        polygons_with_pixels: dict[str, set[str]] = {"train": set(), "test": set()}
        polygons_without_pixels: set[str] = set()
        for scene_index, band_set in enumerate(band_sets, start=1):
            print(f"[{scene_index}/{len(band_sets)}] Membaca grup JP2 {band_set['scene_id']}")
            aligned, datasets = _open_aligned_bands(band_set)
            try:
                for _, feature in frame.iterrows():
                    polygon_id = str(feature["ID_Poligon"])
                    class_name = str(feature["kelas"])
                    split_name = split_by_id[polygon_id]
                    writer = train_writer if split_name == "train" else test_writer
                    count = _write_pixel_features(
                        feature.geometry,
                        polygon_id,
                        class_name,
                        split_name,
                        aligned,
                        writer,
                    )
                    if count:
                        pixels_by_split[split_name] += count
                        pixels_by_class[(split_name, class_name)] += count
                        polygons_with_pixels[split_name].add(polygon_id)
                    else:
                        polygons_without_pixels.add(polygon_id)
            finally:
                for dataset in reversed(datasets):
                    dataset.close()

        for handle in file_handles:
            handle.close()
        file_handles.clear()
        if not pixels_by_split["train"] or not pixels_by_split["test"]:
            raise ValueError(
                "Tidak ada cukup piksel valid pada train/test. Pastikan file JP2 "
                "mencakup poligon berlabel dan citra tidak seluruhnya nodata."
            )
        for split_name in ("train", "test"):
            missing = sorted(
                set(CLASSES)
                - {
                    class_name
                    for current_split, class_name in pixels_by_class
                    if current_split == split_name
                    and pixels_by_class[(current_split, class_name)] > 0
                }
            )
            if missing:
                raise ValueError(
                    f"Split {split_name} tidak memiliki piksel valid kelas {missing}. "
                    "Unduh JP2 yang mencakup poligon kelas tersebut."
                )

        os.replace(temp_paths[0], train_path)
        os.replace(temp_paths[1], test_path)
        print(f"Pixel train: {pixels_by_split['train']:,}; test: {pixels_by_split['test']:,}")
        print(
            "Poligon terwakili:",
            {name: len(ids) for name, ids in polygons_with_pixels.items()},
        )
        print(
            f"Poligon tanpa piksel jernih/tidak tercakup: {len(polygons_without_pixels)}"
        )
        print(f"CSV train: {train_path}")
        print(f"CSV test:  {test_path}")
        print(
            "Hitungan piksel per split/kelas:",
            {f"{split}/{label}": count for (split, label), count in sorted(pixels_by_class.items())},
        )
        return train_path, test_path
    finally:
        for handle in file_handles:
            if not handle.closed:
                handle.close()
        for path in temp_paths:
            if path.exists():
                path.unlink()


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Ekstrak piksel B02/B03/B04/B08/B11 Sentinel-2 JP2 lokal di dalam "
            "poligon GeoJSON dan ekspor train/test CSV."
        )
    )
    parser.add_argument("--geojson", type=Path, default=DEFAULT_GEOJSON)
    parser.add_argument("--band-dir", type=Path, default=DEFAULT_BAND_DIR)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--geojson-crs", default="EPSG:4326")
    parser.add_argument("--test-size", type=float, default=0.2)
    parser.add_argument("--random-state", type=int, default=42)
    args = parser.parse_args()
    if not args.geojson.is_file():
        raise FileNotFoundError(f"GeoJSON label tidak ditemukan: {args.geojson}")
    extract_to_csv(
        geojson_path=args.geojson,
        band_dir=args.band_dir,
        output_dir=args.out_dir,
        geojson_crs=args.geojson_crs,
        test_size=args.test_size,
        random_state=args.random_state,
    )


if __name__ == "__main__":
    main()
