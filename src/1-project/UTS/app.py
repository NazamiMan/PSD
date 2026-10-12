"""Streamlit map for reviewing digitized East Java land-cover polygons."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any, Iterator

import streamlit as st


CLASSES = ("Built-up", "Farm land", "Water body", "Forest", "Mangrove")
CLASS_COLORS = {
    "Built-up": "#e53935",
    "Farm land": "#fdd835",
    "Water body": "#1e88e5",
    "Forest": "#43a047",
    "Mangrove": "#00897b",
}
CLASS_LABELS = {
    "Built-up": "Bangunan / Built-up",
    "Farm land": "Lahan pertanian / Sawah",
    "Water body": "Perairan / Water body",
    "Forest": "Hutan non-mangrove / Forest",
    "Mangrove": "Hutan mangrove / Mangrove",
}


def find_repository_root() -> Path:
    for candidate in Path(__file__).resolve().parents:
        if (candidate / "data" / "jawatimur.geojson").is_file():
            return candidate
    raise FileNotFoundError(
        "GeoJSON tidak ditemukan. Pastikan data/jawatimur.geojson tersedia di root repository."
    )


def feature_class(properties: dict[str, Any]) -> str:
    active = [
        name
        for name in CLASSES
        if properties.get(name) is not None
        and str(properties.get(name)).strip().casefold()
        not in {"", "0", "false", "none", "null"}
    ]
    if len(active) != 1:
        raise ValueError(
            f"Setiap fitur harus memiliki tepat satu label kelas aktif; ditemukan {active}."
        )
    return active[0]


def iter_positions(coordinates: Any) -> Iterator[tuple[float, float]]:
    if (
        isinstance(coordinates, (list, tuple))
        and len(coordinates) >= 2
        and all(isinstance(value, (int, float)) for value in coordinates[:2])
    ):
        yield float(coordinates[0]), float(coordinates[1])
        return
    if isinstance(coordinates, (list, tuple)):
        for child in coordinates:
            yield from iter_positions(child)


def make_leaflet_html(feature_collection: dict[str, Any]) -> str:
    geojson_json = json.dumps(feature_collection, ensure_ascii=False).replace("</", "<\\/")
    colors_json = json.dumps(CLASS_COLORS)
    return (
        """
<div id="lulc-map" style="width:100%;height:680px;border-radius:8px"></div>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css">
<script>
(() => {
  const geojson = __GEOJSON__;
  const colors = __COLORS__;
  const mapElement = document.getElementById("lulc-map");
  const showError = (message) => {
    mapElement.textContent = message;
    mapElement.style.padding = "1rem";
    mapElement.style.color = "#b00020";
  };
  const loadLeaflet = () => {
    if (window.L) {
      initializeMap();
      return;
    }
    const script = document.createElement("script");
    script.src = "https://unpkg.com/leaflet@1.9.4/dist/leaflet.js";
    script.onload = initializeMap;
    script.onerror = () => showError("Gagal memuat Leaflet. Periksa koneksi internet.");
    document.head.appendChild(script);
  };
  const initializeMap = () => {
    if (!window.L || mapElement.dataset.initialized === "true") return;
    mapElement.dataset.initialized = "true";
    const map = L.map(mapElement).setView([-7.8, 113.5], 7);
    const imagery = L.tileLayer(
      "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
      {
        attribution: "Tiles © Esri — Source: Esri, Maxar, Earthstar Geographics, and the GIS User Community",
        maxZoom: 19
      }
    ).addTo(map);
    const overlays = {};
    const grouped = {};
    for (const feature of geojson.features) {
      const className = feature.properties.kelas_tampil;
      (grouped[className] ||= []).push(feature);
    }
    for (const [className, features] of Object.entries(grouped)) {
      const layer = L.geoJSON(
        {type: "FeatureCollection", features},
        {
          style: {
            color: colors[className],
            fillColor: colors[className],
            fillOpacity: 0.35,
            weight: 2
          },
          onEachFeature: (feature, item) => {
            item.bindTooltip(feature.properties.kelas_tampil);
          }
        }
      ).addTo(map);
      overlays[`${className} (${features.length})`] = layer;
    }
    L.control.layers({"Citra satelit": imagery}, overlays, {collapsed: false}).addTo(map);
    L.control.scale().addTo(map);
    const allLayers = L.featureGroup(Object.values(overlays));
    if (allLayers.getLayers().length) {
      map.fitBounds(allLayers.getBounds().pad(0.05));
    }
  };
  loadLeaflet();
})();
</script>
"""
        .replace("__GEOJSON__", geojson_json)
        .replace("__COLORS__", colors_json)
    )


def main() -> None:
    st.set_page_config(page_title="UTS LULC Jawa Timur", layout="wide")
    st.title("Pemeriksaan Poligon Tutupan Lahan Jawa Timur")
    st.caption(
        "Poligon digitasi ditampilkan di atas basemap satelit. Ini adalah label GeoJSON, "
        "bukan hasil prediksi model."
    )

    geojson_path = find_repository_root() / "data" / "jawatimur.geojson"
    try:
        with geojson_path.open(encoding="utf-8") as source:
            geojson = json.load(source)
    except (OSError, json.JSONDecodeError) as error:
        st.error(f"Gagal membaca GeoJSON {geojson_path}: {error}")
        st.stop()

    features_by_class: dict[str, list[dict[str, Any]]] = {
        class_name: [] for class_name in CLASSES
    }
    for index, feature in enumerate(geojson.get("features", []), start=1):
        properties = feature.get("properties") or {}
        try:
            class_name = feature_class(properties)
        except ValueError as error:
            st.error(f"Label GeoJSON pada fitur ke-{index} tidak valid: {error}")
            st.stop()
        display_feature = dict(feature)
        display_feature["properties"] = {**properties, "kelas_tampil": class_name}
        features_by_class[class_name].append(display_feature)

    st.sidebar.header("Filter kelas")
    selected_classes = [
        class_name
        for class_name in CLASSES
        if st.sidebar.checkbox(
            CLASS_LABELS[class_name],
            value=True,
            key=f"class-{class_name}",
        )
    ]

    counts = Counter(
        {
            class_name: len(features)
            for class_name, features in features_by_class.items()
        }
    )
    metric_columns = st.columns(len(CLASSES) + 1)
    metric_columns[0].metric("Total poligon", sum(counts.values()))
    for column, class_name in zip(metric_columns[1:], CLASSES):
        column.metric(CLASS_LABELS[class_name], counts[class_name])

    if not selected_classes:
        st.info("Pilih minimal satu kelas di sidebar untuk menampilkannya.")
        st.stop()

    positions = [
        position
        for feature in geojson.get("features", [])
        for position in iter_positions(
            (feature.get("geometry") or {}).get("coordinates", [])
        )
    ]
    if not positions:
        st.error("GeoJSON tidak memiliki koordinat poligon yang dapat dipetakan.")
        st.stop()
    selected_features = [
        {
            "type": "Feature",
            "geometry": feature["geometry"],
            "properties": {"kelas_tampil": class_name},
        }
        for class_name in selected_classes
        for feature in features_by_class[class_name]
    ]
    map_html = make_leaflet_html(
        {"type": "FeatureCollection", "features": selected_features}
    )
    st.html(map_html, unsafe_allow_javascript=True)

    with st.expander("Ringkasan jumlah label"):
        st.markdown(
            "\n".join(
                f"- **{CLASS_LABELS[class_name]}:** {counts[class_name]} poligon"
                for class_name in CLASSES
            )
        )


if __name__ == "__main__":
    main()
