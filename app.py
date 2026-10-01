import streamlit as st
import tempfile
import os
import ezdxf
from ezdxf import path
import simplekml
import xml.etree.ElementTree as ET
from pyproj import Transformer, CRS

# --- Streamlit Page Setup ---
st.set_page_config(
    page_title="Universal CAD & KML Grid Converter",
    page_icon="🗺️",
    layout="centered"
)

st.title("🗺️ Universal CAD ↔ KML Grid Converter")
st.write("Convert CAD DXF files from **any Grid Coordinate System (EPSG)** to Google Earth KML files (**EPSG:4326 / WGS84**) and vice versa. - ranjith.wijekoon@gmail.com")

# --- Helper Function for EPSG Validation ---
def get_crs_info(epsg_code):
    """Validates EPSG code and returns its official name."""
    try:
        crs = CRS.from_epsg(epsg_code)
        return True, crs.name
    except Exception:
        return False, "Invalid EPSG Code"

# --- Core Conversion Functions ---

def convert_dxf_to_kml(dxf_file_path, epsg_code, swap_xy=False):
    transformer = Transformer.from_crs(f"EPSG:{epsg_code}", "EPSG:4326", always_xy=True)

    def transform_coords(x, y, z=0.0):
        # Invert X and Y if local grid definition uses inverted axis order
        easting, northing = (y, x) if swap_xy else (x, y)
        lon, lat = transformer.transform(easting, northing)
        return (lon, lat, z)

    doc = ezdxf.readfile(dxf_file_path)
    msp = doc.modelspace()
    kml = simplekml.Kml()

    for entity in msp:
        dxftype = entity.dxftype()

        if dxftype == 'POINT':
            x, y, z = entity.dxf.location
            kml.newpoint(coords=[transform_coords(x, y, z)])

        elif dxftype == 'LINE':
            start, end = entity.dxf.start, entity.dxf.end
            pt1 = transform_coords(start.x, start.y, start.z)
            pt2 = transform_coords(end.x, end.y, end.z)
            kml.newlinestring(coords=[pt1, pt2])

        elif dxftype in ['LWPOLYLINE', 'POLYLINE', 'SPLINE']:
            try:
                p = path.make_path(entity)
                vertices = [transform_coords(pt.x, pt.y, pt.z) for pt in p.flattening(distance=0.1)]
                if len(vertices) >= 2:
                    kml.newlinestring(coords=vertices)
            except Exception:
                pass

        elif dxftype == 'ARC':
            try:
                p = path.make_path(entity)
                vertices = [transform_coords(pt.x, pt.y, pt.z) for pt in p.flattening(distance=0.1)]
                if len(vertices) >= 2:
                    kml.newlinestring(coords=vertices)
            except Exception:
                pass

        elif dxftype in ['TEXT', 'MTEXT']:
            text_content = entity.plain_text() if dxftype == 'MTEXT' else entity.dxf.text
            insert = entity.dxf.insert
            kml.newpoint(name=text_content, coords=[transform_coords(insert.x, insert.y, insert.z)])

    return kml

def convert_kml_to_dxf(kml_file_path, epsg_code, text_height=2, swap_xy=False):
    transformer = Transformer.from_crs("EPSG:4326", f"EPSG:{epsg_code}", always_xy=True)

    def transform_coords(lon, lat, alt=0.0):
        easting, northing = transformer.transform(lon, lat)
        x, y = (northing, easting) if swap_xy else (easting, northing)
        return (x, y, alt)

    tree = ET.parse(kml_file_path)
    root = tree.getroot()
    ns = {'kml': 'http://www.opengis.net/kml/2.2'}

    doc = ezdxf.new(dxfversion='R12')
    msp = doc.modelspace()

    def parse_coordinates(coord_str):
        points = []
        for coord in coord_str.strip().split():
            parts = coord.split(',')
            if len(parts) >= 2:
                lon, lat = float(parts[0]), float(parts[1])
                alt = float(parts[2]) if len(parts) >= 3 else 0.0
                points.append(transform_coords(lon, lat, alt))
        return points

    for placemark in root.findall('.//kml:Placemark', ns):
        name_elem = placemark.find('kml:name', ns)
        name = name_elem.text if name_elem is not None else "Unnamed"

        point = placemark.find('.//kml:Point', ns)
        if point is not None:
            coord_elem = point.find('kml:coordinates', ns)
            if coord_elem is not None and coord_elem.text:
                pts = parse_coordinates(coord_elem.text)
                if pts:
                    insertion_pt = pts[0]
                    msp.add_point(insertion_pt)
                    msp.add_text(name, dxfattribs={'height': text_height}).set_placement(insertion_pt)

        linestring = placemark.find('.//kml:LineString', ns)
        if linestring is not None:
            coord_elem = linestring.find('kml:coordinates', ns)
            if coord_elem is not None and coord_elem.text:
                pts = parse_coordinates(coord_elem.text)
                if len(pts) >= 2:
                    msp.add_polyline3d(pts)

    return doc
