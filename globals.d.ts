interface Waypoint {
    latlng: L.LatLng;
    name: string;
}

interface ServerCoordinate {
    lat: number;
    lng: number;
}

interface ServerWaypoint extends ServerCoordinate {
    name: string;
}

interface TwistGeometryData {
    name: string;
    is_paved: boolean;
    waypoints: ServerWaypoint[];
    route_geometry: ServerCoordinate[];
}

// Hacky way to get leaflet type checking
declare namespace L {

    // --- Basic Types ---
    type LatLng = { lat: number, lng: number };
    type Map = any; 
    type Point = any;
    type Marker = any;
    type Polyline = any;
    type TileLayer = any;
    type FeatureGroup = any;
    declare var Control: any;
    declare var DomEvent: any;
    declare var DomUtil: any;

    // --- Classes ---
    class Icon {
        constructor(options: object);
    }

    // --- Functions on L ---
    function map(id: string | HTMLElement, options?: object): Map;
    function point(x: number, y: number): Point;
    function marker(latlng: LatLng, options?: object): Marker;
    function polyline(latlngs: LatLng[], options?: object): Polyline;
    function icon(options: object): Icon;
    function tileLayer(urlTemplate: string, options?: object): TileLayer;
    function featureGroup(layers?: any[]): FeatureGroup;
    function setOptions(Object: obj, Object: options): Object;
}

declare var GeoSearch: any;
declare var htmx: any;