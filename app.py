import math
import time
from typing import Any

import pandas as pd
import requests
import streamlit as st

APP_TITLE = "Lunch Roulette SG"
USER_AGENT = "LunchRouletteSG/0.4 (personal lunch discovery app; photo attribution enabled)"
COMMONS_API_URL = "https://commons.wikimedia.org/w/api.php"
ONEMAP_SEARCH_URL = "https://www.onemap.gov.sg/api/common/elastic/search"
OVERPASS_URLS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
]
BUDGET_BANDS = ["Unknown", "$", "$$", "$$$", "$$$$"]
PRICE_GUIDE = {"$": "Under S$10", "$$": "S$10–20", "$$$": "S$21–40", "$$$$": "Over S$40"}
LEGACY_BUDGETS = {"Under S$10": "$", "S$10–20": "$$", "S$21–40": "$$$", "Over S$40": "$$$$"}
MRT_STATIONS = [
    "Admiralty", "Aljunied", "Ang Mo Kio", "Bakau", "Balmoral", "Bartley", "Bayfront",
    "Beauty World", "Bedok", "Bedok North", "Bedok Reservoir", "Bencoolen", "Bendemeer",
    "Boon Keng", "Boon Lay", "Botanic Gardens", "Braddell", "Bras Basah", "Bright Hill",
    "Bugis", "Buangkok", "Caldecott", "Canberra", "Cashew", "Changi Airport", "Chinatown",
    "Chinese Garden", "Choa Chu Kang", "City Hall", "Clarke Quay", "Clementi", "Commonwealth",
    "Dakota", "Dhoby Ghaut", "Dover", "Downtown", "Eunos", "Expo", "Farrer Park",
    "Farrer Road", "Fort Canning", "Gardens by the Bay", "Geylang Bahru", "Great World",
    "HarbourFront", "Haw Par Villa", "Hillview", "Holland Village", "Hougang", "Jalan Besar",
    "Joo Koon", "Kaki Bukit", "Kallang", "Kembangan", "Kent Ridge", "Khatib", "King Albert Park",
    "Kovan", " Labrador Park", "Lakeside", "Lavender", "Little India", "MacPherson", "Marina Bay",
    "Marina South Pier", "Marymount", "Mattar", "Mayflower", "Newton", "Nicoll Highway",
    "one-north", "Orchard", "Orchard Boulevard", "Outram Park", "Pasir Panjang", "Pasir Ris",
    "Paya Lebar", "Pioneer", "Potong Pasir", "Promenade", "Queenstown", "Raffles Place",
    "Redhill", "Rochor", "Sengkang", "Serangoon", "Shenton Way", "Simei", "Sixth Avenue",
    "Somerset", "Stadium", "Stevens", "Tai Seng", "Tampines", "Tampines East", "Tampines West",
    "Tanah Merah", "Tanjong Pagar", "Telok Ayer", "Telok Blangah", "Tiong Bahru", "Toa Payoh",
    "Tuas Crescent", "Tuas Link", "Tuas West Road", "Ubi", "Upper Changi", "Upper Thomson",
    "Woodlands", "Woodlands North", "Woodlands South", "Yew Tee", "Yio Chu Kang", "Yishun",
]
OVERRIDE_COLUMNS = [
    "id", "name", "address_override", "cuisine_override", "budget_band",
    "personal_rating", "notes", "website_override", "opening_hours_override", "image_url_override",
]

st.set_page_config(page_title=APP_TITLE, page_icon="🍜", layout="wide")

st.markdown("""
<style>
.block-container {padding-top:.7rem; padding-bottom:1.5rem; max-width:1000px; padding-left:1rem; padding-right:1rem;}
.hero {background:linear-gradient(120deg,#143c35,#347765);padding:1.25rem 1.3rem;
       border-radius:18px;color:white;margin-bottom:1rem;}
.hero h1 {font-size:clamp(1.6rem,5vw,2.4rem);margin:0;}
.hero p {color:#dcebe6;margin:.35rem 0 0 0;}
div[data-testid="stMetric"] {background:rgba(100,120,120,.08);padding:10px;border-radius:12px;}
@media (max-width: 640px) {
  .block-container {padding-left:.65rem; padding-right:.65rem;}
  div[data-testid="stVerticalBlockBorderWrapper"] {border-radius:13px;}
  div[data-testid="stButton"] button {min-height:2.65rem;}
}
div[data-testid="stExpander"] {border-radius:12px;}
.small-muted {color:#777;font-size:.85rem;}
.price-badge {display:inline-block;background:#e0eee5;color:#205a3e;border-radius:7px;padding:2px 8px;font-weight:750;font-size:.88rem;letter-spacing:.03em;}
.food-thumb {width:76px;height:76px;border-radius:12px;background:#f2f4f3;display:flex;align-items:center;justify-content:center;font-size:1.8rem;}
.place-meta {color:#737780;font-size:.9rem;line-height:1.5;}
div[data-testid="stRadio"] > div {gap:.35rem;}
</style>
""", unsafe_allow_html=True)

st.markdown(
    '<div class="hero"><h1>🍜 Lunch Roulette SG</h1>'
    '<p>Good food, less decision fatigue.</p></div>',
    unsafe_allow_html=True,
)
st.caption("Your office lunch companion · Singapore")

if "places" not in st.session_state:
    st.session_state.places = []
if "favourites" not in st.session_state:
    st.session_state.favourites = set()
if "overrides" not in st.session_state:
    st.session_state.overrides = pd.DataFrame(columns=OVERRIDE_COLUMNS)
if "office_location" not in st.session_state:
    st.session_state.office_location = None
if "search_label" not in st.session_state:
    st.session_state.search_label = ""


def normalize_overrides(frame: pd.DataFrame) -> pd.DataFrame:
    for col in OVERRIDE_COLUMNS:
        if col not in frame.columns:
            frame[col] = ""
    frame = frame[OVERRIDE_COLUMNS].fillna("")
    frame["id"] = frame["id"].astype(str)
    frame["budget_band"] = frame["budget_band"].replace(LEGACY_BUDGETS)
    return frame.drop_duplicates(subset=["id"], keep="last")


def price_band(price: str) -> str:
    if not price:
        return "Unknown"
    text = str(price).strip().lower()
    # Never infer SGD unless the source explicitly identifies SGD.
    if "sgd" in text or "s$" in text or "sg$" in text:
        digits = "".join(ch if ch.isdigit() else " " for ch in text).split()
        if digits:
            amount = int(digits[0])
            if amount < 10:
                return "Under S$10"
            if amount <= 20:
                return "S$10–20"
            if amount <= 40:
                return "S$21–40"
            return "Over S$40"
    return "Listed (currency unclear)"


def apply_overrides(places: list[dict[str, Any]]) -> list[dict[str, Any]]:
    overrides = normalize_overrides(st.session_state.overrides)
    lookup = {str(row["id"]): row for _, row in overrides.iterrows() if str(row["id"]).strip()}
    for place in places:
        row = lookup.get(str(place["id"]))
        place["budget_band"] = "Unknown"
        place["personal_rating"] = ""
        place["notes"] = ""
        if row is None:
            continue
        for source, target in [
            ("address_override", "address"),
            ("cuisine_override", "cuisine"),
            ("website_override", "website"),
            ("opening_hours_override", "opening_hours"),
            ("image_url_override", "image_url"),
        ]:
            val = str(row.get(source, "")).strip()
            if val:
                place[target] = val
        budget = str(row.get("budget_band", "")).strip()
        if budget in BUDGET_BANDS:
            place["budget_band"] = budget
        place["personal_rating"] = str(row.get("personal_rating", "")).strip()
        place["notes"] = str(row.get("notes", "")).strip()
    return places


@st.cache_data(ttl=3600, show_spinner=False)
def geocode_place(query: str) -> dict[str, Any] | None:
    response = requests.get(
        ONEMAP_SEARCH_URL,
        params={"searchVal": query, "returnGeom": "Y", "getAddrDetails": "Y", "pageNum": 1},
        headers={"User-Agent": USER_AGENT},
        timeout=18,
    )
    response.raise_for_status()
    results = response.json().get("results", [])
    if not results:
        return None
    item = results[0]
    if not item.get("LATITUDE") or not item.get("LONGITUDE"):
        return None
    return {
        "lat": float(item["LATITUDE"]),
        "lon": float(item["LONGITUDE"]),
        "display_name": item.get("ADDRESS", query),
    }


@st.cache_data(ttl=1800, show_spinner=False)
def discover_places(lat: float, lon: float, radius_m: int) -> list[dict[str, Any]]:
    """Discover mapped food places, rotating through public Overpass servers."""
    query = f"""
    [out:json][timeout:18];
    (
      nwr(around:{radius_m},{lat},{lon})["amenity"~"^(restaurant|cafe|fast_food|food_court|ice_cream)$"];
      nwr(around:{radius_m},{lat},{lon})["shop"~"^(bakery|confectionery|deli|pastry)$"];
    );
    out center tags;
    """
    last_error = "All public data servers are unavailable."
    transient_statuses = {429, 502, 503, 504}
    for endpoint in OVERPASS_URLS:
        # One retry for transient server load, then fail over to the next endpoint.
        for attempt in range(2):
            try:
                response = requests.post(
                    endpoint, data={"data": query},
                    headers={"User-Agent": USER_AGENT}, timeout=(5, 20)
                )
                if response.status_code in transient_statuses:
                    last_error = f"HTTP {response.status_code} from a restaurant data server"
                    if attempt == 0:
                        time.sleep(0.8)
                        continue
                    break
                response.raise_for_status()
                payload = response.json()
                elements = payload.get("elements", [])
                places = []
                seen = set()
                for item in elements:
                    tags = item.get("tags", {})
                    name = tags.get("name") or tags.get("brand")
                    if not name:
                        continue
                    if "lat" in item and "lon" in item:
                        p_lat, p_lon = float(item["lat"]), float(item["lon"])
                    elif "center" in item:
                        p_lat, p_lon = float(item["center"]["lat"]), float(item["center"]["lon"])
                    else:
                        continue
                    osm_type, osm_id = item.get("type", "node"), item.get("id")
                    uid = f"{osm_type}/{osm_id}"
                    if uid in seen:
                        continue
                    seen.add(uid)
                    category = tags.get("amenity") or tags.get("shop") or "food"
                    addr_parts = [
                        tags.get("addr:housenumber"), tags.get("addr:street"),
                        tags.get("addr:building"), tags.get("addr:unit"),
                        tags.get("addr:suburb") or tags.get("addr:neighbourhood"),
                        tags.get("addr:postcode"),
                    ]
                    address = ", ".join(dict.fromkeys(x for x in addr_parts if x)) or "Not listed"
                    places.append({
                        "id": uid, "name": name,
                        "category": category.replace("_", " ").title(),
                        "lat": p_lat, "lon": p_lon, "address": address,
                        "cuisine": tags.get("cuisine", "").replace("_", ", ").title(),
                        "website": tags.get("website") or tags.get("contact:website", ""),
                        "phone": tags.get("phone") or tags.get("contact:phone", ""),
                        "opening_hours": tags.get("opening_hours", ""),
                        "image_url": tags.get("image") or tags.get("image_url") or "",
                        "source_price": tags.get("price", ""),
                        "osm_url": f"https://www.openstreetmap.org/{osm_type}/{osm_id}",
                    })
                return places
            except (requests.RequestException, ValueError, KeyError) as exc:
                last_error = str(exc)[:250]
                if attempt == 0:
                    time.sleep(0.8)
                else:
                    break
    raise RuntimeError(last_error)


def distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = math.radians(lat2-lat1), math.radians(lon2-lon1)
    a = math.sin(dp/2)**2 + math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2
    return 2*r*math.asin(math.sqrt(a))


@st.cache_data(ttl=86400, show_spinner=False)
def commons_search_photo(search_term: str, mode: str = "place") -> dict[str, str] | None:
    """Search Wikimedia Commons; cuisine results are illustrative, not venue photos."""
    term = str(search_term or "").strip()
    if not term:
        return None
    search_text = f'"{term}" Singapore' if mode == "place" else term
    params = {
        "action": "query", "format": "json", "generator": "search",
        "gsrsearch": f"filetype:bitmap {search_text}", "gsrnamespace": 6,
        "gsrlimit": 8, "prop": "imageinfo",
        "iiprop": "url|extmetadata", "iiurlwidth": 360,
    }
    try:
        response = requests.get(COMMONS_API_URL, params=params,
                                headers={"User-Agent": USER_AGENT}, timeout=(3, 7))
        response.raise_for_status()
        pages = response.json().get("query", {}).get("pages", {})
    except (requests.RequestException, ValueError, TypeError):
        return None

    term_words = {w.casefold() for w in term.replace("-", " ").split() if len(w) > 2}
    for page in pages.values():
        title = str(page.get("title", ""))
        info_list = page.get("imageinfo", [])
        if not info_list:
            continue
        info = info_list[0]
        meta = info.get("extmetadata", {})
        description = (title + " " + str(meta.get("ImageDescription", {}).get("value", ""))).casefold()
        if mode == "place" and (not term_words or not all(word in description for word in term_words)):
            continue
        thumb = info.get("thumburl") or info.get("url")
        if not thumb or not str(thumb).startswith("https://"):
            continue
        return {
            "url": str(thumb),
            "page_url": str(info.get("descriptionurl") or "https://commons.wikimedia.org/"),
            "title": title.replace("File:", "", 1),
            "artist": str(meta.get("Artist", {}).get("value", "")),
            "license": str(meta.get("LicenseShortName", {}).get("value", "")),
            "kind": "restaurant" if mode == "place" else "illustrative",
        }
    return None


def photo_for_place(place: dict[str, Any], lookup_place_photo: bool = False) -> dict[str, str] | None:
    """Prefer OSM/user photos, then a possible Commons match, then cuisine imagery."""
    direct = str(place.get("image_url") or "").strip()
    if direct.startswith("https://"):
        return {"url": direct, "page_url": place.get("osm_url", "https://www.openstreetmap.org/"),
                "title": "Photo linked from map data or your correction", "artist": "",
                "license": "Check original source", "kind": "mapped"}
    if lookup_place_photo:
        match = commons_search_photo(str(place.get("name", "")), "place")
        if match:
            return match
    cuisine = str(place.get("cuisine") or "").strip().casefold()
    if any(x in cuisine for x in ("singapore", "malay", "hawker", "chinese")):
        query = "Singapore hawker food"
    elif any(x in cuisine for x in ("japanese", "sushi", "ramen")):
        query = "Japanese cuisine food"
    elif "korean" in cuisine:
        query = "Korean cuisine food"
    elif "indian" in cuisine:
        query = "Indian cuisine food"
    elif "thai" in cuisine:
        query = "Thai cuisine food"
    elif "vietnamese" in cuisine:
        query = "Vietnamese cuisine food"
    elif any(x in cuisine for x in ("italian", "pizza", "pasta")):
        query = "Italian cuisine food"
    elif any(x in cuisine for x in ("western", "burger", "american")):
        query = "burger western food"
    else:
        query = "restaurant meal food"
    return commons_search_photo(query, "cuisine")


def maps_url(place: dict[str, Any]) -> str:
    return f"https://www.google.com/maps/search/?api=1&query={place['lat']},{place['lon']}"


with st.sidebar:
    st.subheader("Your data")
    st.caption("Import a corrections CSV to restore your own prices, notes and ratings.")
    uploaded = st.file_uploader("Import corrections CSV", type=["csv"])
    if uploaded is not None:
        try:
            st.session_state.overrides = normalize_overrides(pd.read_csv(uploaded, dtype=str).fillna(""))
            st.success("Your corrections were imported.")
        except Exception:
            st.error("That CSV could not be read.")
    st.divider()
    st.caption("Location lookup: OneMap · Restaurant data: OpenStreetMap contributors")


discover_tab, saved_tab, manage_tab = st.tabs(["🔎 Discover Food", "❤️ My Food List", "🛠 Manage Places"])

with discover_tab:
    st.markdown("### Find your next lunch")
    st.caption("Choose where to start, then browse nearby food in one clean list.")

    station_names = sorted(set(x.strip() for x in MRT_STATIONS))
    if "location_mode" not in st.session_state:
        st.session_state.location_mode = "Choose an MRT station"
    if "selected_station" not in st.session_state:
        st.session_state.selected_station = "Raffles Place"
    if "radius_choice" not in st.session_state:
        st.session_state.radius_choice = "10 min · 800 m"

    with st.container(border=True):
        st.markdown("**📍 Location**")
        location_mode = st.radio(
            "Start from", ["Choose an MRT station", "Type an office / building"],
            horizontal=True, key="location_mode", label_visibility="collapsed"
        )
        if location_mode == "Choose an MRT station":
            selected_station = st.selectbox(
                "MRT station", station_names,
                index=station_names.index(st.session_state.selected_station) if st.session_state.selected_station in station_names else station_names.index("Raffles Place"),
                key="selected_station"
            )
            office_query = f"{selected_station} MRT Station"
        else:
            office_query = st.text_input("Office / building name", placeholder="e.g. One Raffles Place", key="office_query")

        radius_choice = st.selectbox(
            "Search distance", ["5 min · 400 m", "10 min · 800 m", "15 min · 1.2 km", "20 min · 1.6 km"],
            index=["5 min · 400 m", "10 min · 800 m", "15 min · 1.2 km", "20 min · 1.6 km"].index(st.session_state.radius_choice),
            key="radius_choice"
        )
        radius = {"5 min · 400 m": 400, "10 min · 800 m": 800, "15 min · 1.2 km": 1200, "20 min · 1.6 km": 1600}[radius_choice]
        if st.button("Find lunch", type="primary", use_container_width=True):
            st.session_state.run_search = True

    with st.expander("Filters and display", expanded=False):
        cuisine_values = sorted({x.strip() for p in st.session_state.places for x in p.get("cuisine", "").split(",") if x.strip()})
        chosen_cuisines = st.multiselect("Cuisine", cuisine_values, placeholder="Any cuisine")
        type_values = sorted({p["category"] for p in st.session_state.places})
        type_filter = st.selectbox("Food type", ["All types"] + type_values)
        sort_choice = st.selectbox("Sort results", ["Nearest first", "Name A–Z", "Random order"])
        show_map = st.checkbox("Show map", value=False)

    if st.session_state.pop("run_search", False):
        if not office_query.strip():
            st.warning("Choose an MRT station or enter an office/building name.")
        else:
            try:
                with st.spinner("Finding your location…"):
                    office = geocode_place(office_query.strip())
                if not office:
                    st.warning("Location not found. Try a nearby MRT station or building name.")
                else:
                    try:
                        with st.spinner("Finding nearby places…"):
                            found = discover_places(office["lat"], office["lon"], radius)
                    except RuntimeError:
                        if radius > 400:
                            with st.spinner("Trying a smaller search area…"):
                                found = discover_places(office["lat"], office["lon"], max(400, radius // 2))
                        else:
                            raise
                    for place in found:
                        place["distance_km"] = distance_km(office["lat"], office["lon"], place["lat"], place["lon"])
                    found = apply_overrides(found)
                    st.session_state.places = sorted(found, key=lambda item: item["distance_km"])
                    st.session_state.visible_place_count = 30
                    st.session_state.office_location = office
                    st.session_state.search_label = office_query.strip()
            except requests.RequestException:
                st.error("The location service is temporarily unavailable. Please try again.")
            except RuntimeError as exc:
                st.error("Restaurant data services are temporarily unavailable. Your app is still running; please retry shortly.")
                st.caption(f"Technical detail: {str(exc)[:180]}")
                if st.button("↻ Retry restaurant search", key="retry_restaurant_search", use_container_width=True):
                    st.session_state.run_search = True
                    st.rerun()

    places = apply_overrides(st.session_state.places) if st.session_state.places else []
    st.session_state.places = places
    saved_count = len(st.session_state.favourites)
    st.caption(f"📍 {st.session_state.search_label or 'Choose a location'}  ·  {len(places)} places found  ·  {saved_count} saved")

    # Defaults when the collapsed filter panel has not been opened.
    if "chosen_cuisines" not in locals():
        chosen_cuisines = []
    if "type_filter" not in locals():
        type_filter = "All types"
    if "sort_choice" not in locals():
        sort_choice = "Nearest first"
    if "show_map" not in locals():
        show_map = False

    filtered = []
    for place in places:
        cuisines = {item.strip().lower() for item in place.get("cuisine", "").split(",") if item.strip()}
        cuisine_ok = not chosen_cuisines or bool(cuisines & {item.lower() for item in chosen_cuisines})
        type_ok = type_filter == "All types" or place["category"] == type_filter
        if cuisine_ok and type_ok:
            filtered.append(place)

    if sort_choice == "Name A–Z":
        filtered.sort(key=lambda item: item.get("name", "").casefold())
    elif sort_choice == "Random order":
        # Deterministic per rerun unless the user requests a new random pick below.
        import random
        random.Random(42).shuffle(filtered)
    else:
        filtered.sort(key=lambda item: item.get("distance_km", float("inf")))

    if show_map and filtered:
        st.map(pd.DataFrame([{"lat": place["lat"], "lon": place["lon"]} for place in filtered]), latitude="lat", longitude="lon")

    if not places:
        st.info("Choose an MRT station above and tap **Find lunch** to discover nearby places.")
    elif not filtered:
        st.info("No places match these filters. Try clearing your cuisine or food-type selections.")
    else:
        active_filter_count = len(chosen_cuisines) + (type_filter != "All types")
        result_col, sort_col = st.columns([3, 2])
        with result_col:
            st.markdown(f"### Nearby food · {len(filtered)}")
        with sort_col:
            st.caption(f"{active_filter_count} active filter(s)" if active_filter_count else "All matching places")

        if "visible_place_count" not in st.session_state:
            st.session_state.visible_place_count = 30
        # Reset the visible cap when the current result set is smaller than the cap.
        visible_count = min(st.session_state.visible_place_count, len(filtered))
        for card_index, place in enumerate(filtered[:visible_count]):
            is_saved = place["id"] in st.session_state.favourites
            price = place.get("budget_band", "Unknown")
            # Limit exact venue-photo lookups to the first 8 cards; all Commons
            # results are cached for 24 hours to keep public-service traffic low.
            photo = photo_for_place(place, lookup_place_photo=(card_index < 8))
            if price in PRICE_GUIDE:
                price_html = f"<span class='price-badge'>{price}</span> <span class='place-meta'>Your estimate</span>"
            else:
                price_html = "<span class='place-meta'>Price unknown</span>"
            cuisine = place.get("cuisine") or "Cuisine not listed"
            hours = place.get("opening_hours") or "Hours not listed"
            address = place.get("address") or "Address not listed"
            image_url = str(place.get("image_url") or "").strip()
            with st.container(border=True):
                image_col, info_col, heart_col = st.columns([0.85, 4.0, 0.45], vertical_alignment="top")
                with image_col:
                    if photo and photo.get("url"):
                        try:
                            st.image(photo["url"], width=76)
                            if photo.get("kind") == "illustrative":
                                st.caption("Example")
                        except Exception:
                            st.markdown("<div class='food-thumb'>🍜</div>", unsafe_allow_html=True)
                    else:
                        st.markdown("<div class='food-thumb'>🍜</div>", unsafe_allow_html=True)
                with info_col:
                    st.markdown(f"**{place['name']}**")
                    st.markdown(f"<div class='place-meta'>{cuisine} · {place['distance_km'] * 1000:.0f} m away</div>", unsafe_allow_html=True)
                    st.markdown(price_html, unsafe_allow_html=True)
                    if place.get("personal_rating"):
                        st.caption(f"Your rating: {place['personal_rating']}/5")
                with heart_col:
                    if st.button("♥" if is_saved else "♡", key=f"save_{place['id']}", help="Remove from saved places" if is_saved else "Save this place"):
                        if is_saved:
                            st.session_state.favourites.remove(place["id"])
                        else:
                            st.session_state.favourites.add(place["id"])
                        st.rerun()
                with st.expander("Details", expanded=False):
                    st.write(f"**Address:** {address}")
                    st.write(f"**Opening hours:** {hours}")
                    if price in PRICE_GUIDE:
                        st.write(f"**Your estimated spend:** {PRICE_GUIDE[price]} per person")
                    if place.get("notes"):
                        st.write(f"**Your note:** {place['notes']}")
                    if place.get("website"):
                        st.markdown(f"[Restaurant website ↗]({place['website']})")
                    if photo and photo.get("page_url"):
                        if photo.get("kind") == "illustrative":
                            st.caption("Illustrative cuisine photo — not verified as this restaurant.")
                        elif photo.get("kind") == "restaurant":
                            st.caption("Possible restaurant photo from Wikimedia Commons; verify the match at the source.")
                        else:
                            st.caption("Photo linked from map data or your own correction.")
                        credits = [x for x in [photo.get("artist"), photo.get("license")] if x]
                        if credits:
                            st.caption("Photo credit / licence: " + " · ".join(credits))
                        st.markdown(f"[Photo source ↗]({photo['page_url']})")
                    st.markdown(f"[Check Google Maps ↗]({maps_url(place)}) · [OpenStreetMap source ↗]({place['osm_url']})")
                    if st.button("Edit details", key=f"editgo_{place['id']}", use_container_width=True):
                        st.session_state.edit_place_id = place["id"]
                        st.info("Open Manage Places to edit this listing.")

        if visible_count < len(filtered):
            if st.button(f"Load {min(30, len(filtered) - visible_count)} more places", use_container_width=True):
                st.session_state.visible_place_count = visible_count + 30
                st.rerun()
        elif len(filtered) > 30:
            st.caption("You've reached the end of the matching list.")

    if st.button("🎲 Pick a random lunch", use_container_width=True, disabled=not bool(filtered)):
        import random
        pick = random.choice(filtered)
        st.success(f"Today's pick: {pick['name']} · {pick['distance_km'] * 1000:.0f} m away")
        st.markdown(f"[Get directions in Google Maps ↗]({maps_url(pick)})")

with saved_tab:
    st.markdown("### Your food shortlist")
    saved = [p for p in places if p["id"] in st.session_state.favourites]
    if not saved:
        st.info("Save places from Discover Food and they'll appear here for this session.")
    else:
        for p in saved:
            with st.container(border=True):
                st.markdown(f"**{p['name']}** · {p['distance_km']:.2f} km")
                price_label = f"{p.get('budget_band')} · your estimate" if p.get('budget_band') in PRICE_GUIDE else "Price unknown"
                st.caption(f"{p['cuisine'] or 'Cuisine not listed'} · {price_label} · Your rating: {p.get('personal_rating') or 'Not rated'}")
                st.markdown(f"[Open in Google Maps ↗]({maps_url(p)})")
                if p.get("notes"):
                    st.write(p["notes"])
                if st.button("Unsave", key=f"unsave_{p['id']}"):
                    st.session_state.favourites.remove(p["id"])
                    st.rerun()
    st.caption("Saved-place selection currently lasts for the active app session. Export corrections in Manage Places; permanent cross-device favourites can be added later.")

with manage_tab:
    st.markdown("### Manage restaurant details")
    st.write("Keep the discovery tab focused on finding lunch. Use this tab to add your own corrections and budget estimates.")
    if not places:
        st.info("Search for nearby food first, then return here to edit a restaurant.")
    else:
        place_options = {f"{p['name']} · {p['distance_km']:.2f} km": p["id"] for p in places}
        labels = list(place_options.keys())
        default_idx = 0
        edit_id = st.session_state.get("edit_place_id")
        if edit_id:
            for i, label in enumerate(labels):
                if place_options[label] == edit_id:
                    default_idx = i
                    break
        selected_label = st.selectbox("Choose a restaurant to edit", labels, index=default_idx)
        selected_id = place_options[selected_label]
        selected = next(p for p in places if p["id"] == selected_id)
        current_df = normalize_overrides(st.session_state.overrides)
        rows = current_df[current_df["id"] == selected_id]
        old = rows.iloc[0].to_dict() if not rows.empty else {}
        with st.form("manage_place_form"):
            st.caption("Personal corrections are your notes, not independently verified public data.")
            addr = st.text_input("Address", value=str(old.get("address_override") or ("" if selected["address"] == "Not listed" else selected["address"])))
            cuisine = st.text_input("Cuisine", value=str(old.get("cuisine_override") or selected["cuisine"]), placeholder="e.g. Japanese, ramen")
            budget = st.selectbox("Your estimated budget", BUDGET_BANDS, index=BUDGET_BANDS.index(str(old.get("budget_band") or selected.get("budget_band", "Unknown"))) if str(old.get("budget_band") or selected.get("budget_band", "Unknown")) in BUDGET_BANDS else 0)
            rating_options = ["", "1", "2", "3", "4", "5"]
            saved_rating = str(old.get("personal_rating", ""))
            rating_index = rating_options.index(saved_rating) if saved_rating in rating_options else 0
            rating = st.selectbox("Your personal rating", rating_options, index=rating_index)
            notes = st.text_area("Notes / what to order", value=str(old.get("notes", "")), placeholder="e.g. try the dry ramen")
            website = st.text_input("Website", value=str(old.get("website_override") or selected.get("website", "")))
            hours = st.text_input("Opening hours", value=str(old.get("opening_hours_override") or selected.get("opening_hours", "")))
            image_url = st.text_input("Photo URL (optional)", value=str(old.get("image_url_override") or selected.get("image_url", "")), placeholder="https://…")
            st.caption("Use a direct image URL you have permission to use. If no photo is available, the card shows a simple placeholder.")
            if st.form_submit_button("Save corrections", type="primary"):
                old_df = normalize_overrides(st.session_state.overrides)
                old_df = old_df[old_df["id"] != selected_id]
                new = pd.DataFrame([{
                    "id": selected_id, "name": selected["name"],
                    "address_override": addr, "cuisine_override": cuisine,
                    "budget_band": budget, "personal_rating": rating,
                    "notes": notes, "website_override": website,
                    "opening_hours_override": hours, "image_url_override": image_url,
                }])
                st.session_state.overrides = normalize_overrides(pd.concat([old_df, new], ignore_index=True))
                st.session_state.places = apply_overrides(st.session_state.places)
                st.success("Saved for this session. Export the CSV below to keep a copy.")
                st.rerun()

    st.divider()
    st.markdown("#### Back up your corrections")
    export_df = normalize_overrides(st.session_state.overrides)
    st.download_button("⬇ Export corrections CSV", export_df.to_csv(index=False).encode("utf-8"),
                       file_name="lunch_roulette_corrections.csv", mime="text/csv", use_container_width=True)
    st.caption("Upload this CSV from the sidebar next time. Streamlit session data may reset after a restart.")

with st.expander("Data sources, limitations and privacy"):
    st.write("Restaurant discovery uses OpenStreetMap community data via Overpass. Office/building lookup uses OneMap Search. Search services are public and can occasionally be busy.")
    st.write("Photos prefer image URLs present in OpenStreetMap tags or ones you add yourself. If none exists, the app may search Wikimedia Commons for a possible restaurant-name match on the first few cards, then use a cached illustrative cuisine photo when available. Commons matches can be imperfect; illustrative images are labelled and are not claimed to depict the restaurant. Photo source links and available attribution/licence metadata appear in Details. The app does not scrape Google Maps.")
    st.write("Ratings and review counts from Google Maps are not included in this free-only version. We do not scrape Google Maps. Price bands shown on cards are personal estimates entered by you; public map data rarely includes reliable meal prices. Unknown prices are labelled rather than guessed.")
    st.write("Your typed location is sent to OneMap to find coordinates. The app does not request your phone's GPS.")
    st.markdown("[OpenStreetMap attribution](https://www.openstreetmap.org/copyright) · [OneMap API terms](https://www.onemap.gov.sg/legal/apitermsofservice.html) · [Google Places API policies](https://developers.google.com/maps/documentation/places/web-service/policies)")
