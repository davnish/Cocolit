import folium
import streamlit as st
from folium.plugins import Draw
from src.data_struct.bbox import BBox
from configs.logger import setup_logger
from pipelines.inference import InferencePipeline
from folium.plugins import Geocoder
import geopandas as gpd
from src.exceptions.exceptions import NotSavedToDatabase
import requests
from src.dal.preds import preds_bbox_to_database



logger = setup_logger("map_ui", "map_ui.log")


@st.cache_resource
def load_inference(model_path) -> InferencePipeline:
    inference = InferencePipeline(model_path)
    return inference


def get_map(config) -> tuple[folium.Map, folium.FeatureGroup]:
    m = folium.Map(tiles=None, zoom_control=False)

    Geocoder(
        collapsed=True,
        add_marker=True,
        placeholder="Search for a city...",
    ).add_to(m)

    tile = folium.TileLayer(
        tiles=config["map_ui"]["tile"],
        attr="Google Satellite",
        name="Satellite",
        overlay=False,
        control=True,
    )

    tile.add_to(m)

    Draw(
        export=False,
        position="topleft",
        draw_options={
            "polyline": False,
            "poly": False,
            "circle": False,
            "polygon": False,
            "marker": False,
            "circlemarker": False,
            "rectangle": True,
            "edit": False,
        },
    ).add_to(m)

    layer_control = folium.LayerControl()

    return m, layer_control


def init_boxes(all_drawings)->None:
    """
    - we are generating the "bboxes" in st.session_state
    which will collect all the bbox from the folium map
    - the condition `len(all_drawings)==0` is used to
    checks if the user deletes the geometry then output['all_drawings'] will be zero,
    so to reset the st.session_state['bboxes'] list too.
    """
    if all_drawings is None or len(all_drawings) == 0:
        if "bboxes" not in st.session_state:
            st.session_state["bboxes"] = []

        elif len(st.session_state["bboxes"]) > 0:
            st.session_state["bboxes"] = []
            logger.info("Init Boxes : Rerun")
            st.rerun()


def add_predictions(configs:dict) -> folium.FeatureGroup:
    """
    If the predictions in `st.session_state['boxes']` not None the it will
    add all prediction to a feature group `pt`
    """
    pt = folium.FeatureGroup(name=configs["map_ui"]["layergroup_name"])

    if "bboxes" in st.session_state and st.session_state["bboxes"]:
        try:
            for bbox in st.session_state["bboxes"]:
                if bbox.preds is not None:
                    trees = folium.GeoJson(
                        bbox.preds,
                        name="CocoTrees",
                        marker=folium.Circle(
                            radius=configs["map_ui"]["prediction"]["radius"],
                            fill_color=configs["map_ui"]["prediction"]["fill_color"],
                            fill_opacity=configs["map_ui"]["prediction"]["fill_opacity"],
                            color=configs["map_ui"]["prediction"]["color"],
                            weight=configs["map_ui"]["prediction"]["weight"],
                        ),
                        highlight_function=lambda x: {
                            "fillOpacity": configs["map_ui"]["prediction"]["highlight"][
                                "fill_opacity"
                            ]
                        },
                    )
                    pt.add_child(trees)

        except Exception as e:
            logger.error(f"Error adding predictions: {e}", exc_info=True)
            st.error("Failed to add predictions. Please refresh the page.")
            raise
    return pt


def get_inference(all_drawings: dict, inference: InferencePipeline, conn: bool) -> None:
    if all_drawings is not None and len(all_drawings) > 0:
        if (
            len(st.session_state["bboxes"]) > 0
            and all_drawings[-1] == st.session_state["bboxes"][-1].data
        ):
            pass
        else:
            bbox = inference.run(BBox(all_drawings[-1]))

            if bbox.preds is not None:
                if conn:
                    try:
                        preds_bbox_to_database(bbox.gdf, bbox.preds)
                        logger.info("Data Saved to database")
                    except Exception:
                        raise NotSavedToDatabase
            else:
                logger.info("No Predictions found")

            st.session_state["bboxes"].append(bbox)
            logger.info("Get Inference : Rerun")
            st.rerun()


def show_metrics() -> None:
    area = 0
    cnt = 0
    if "bboxes" in st.session_state and len(st.session_state["bboxes"]) > 0:
        for bbox in st.session_state["bboxes"]:
            area += bbox.area

            if bbox.preds is not None:
                cnt += len(bbox.preds)

    density = cnt / area if area > 0 else 0
    cols = st.columns(3)
    with cols[0]:
        st.metric("Total Selected Area (Km²)", f"{area / 1e6:.2f}")
    with cols[1]:
        st.metric("Total Count in Selected Area", cnt)
    with cols[2]:
        st.metric(
            "Total Density of Coconutes in Selected Area(per Km²)", f"{density:.2f}"
        )

